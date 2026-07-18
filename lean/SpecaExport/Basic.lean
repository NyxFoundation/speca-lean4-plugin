import Lean.Util.CollectAxioms
import Lean.Data.Json
import Lean.Meta
import Lean.DeclarationRange
-- The substantive proved results (~70-80% of gasper-lean4) live in
-- `GasperBeaconChain.Core.*` (Theories/Lemmas): the top-level accountable
-- safety (`k_safety'`), the slashable bound, plausible liveness, and the
-- justification/quorum lemmas. `Executable.*` is the thin, still-growing
-- application layer that exposes decidable Bool checkers on top of Core. We
-- import BOTH so every Core and Executable target resolves; the gasper root
-- module `GasperBeaconChain` only reaches `Core.All` and never `Executable`.
import GasperBeaconChain.Core.All
import GasperBeaconChain.Executable.All

/-!
Proof-health export for the SPECA Lean4 plugin.

For each *targeted* theorem name we resolve it in the environment, collect the
axioms its proof depends on (`collectAxioms`), and classify it into a
`lean_status` that the Python driver copies into the `01e` property record:

* `proved`   -- the declaration exists, is a real proof, and its proof does not
               depend on `sorryAx`.
* `unknown`  -- the declaration depends on `sorryAx` (proof is incomplete), or
               the name cannot be resolved in the environment.

We deliberately do NOT collapse `Classical.choice` into `unknown`: gasper-lean4
is constructive (choice-free) by design, so we surface a `choiceFree` flag for
auditing but keep `proved` status as long as there is no `sorry`. `counterexample`
is not represented yet -- gasper's theorems are proofs, not refutations.

Enrichment fields (workstream A):
- `statement`           -- pretty-printed theorem type (A1)
- `conclusion`          -- pretty-printed body of the forall-telescope (the Q
                           that the theorem guarantees once the hypotheses hold)
- `hypotheses`          -- telescope decomposition with depend-allowed /
                           must-establish classification and the head constant
                           of each hypothesis type (A2, feeds B1/B5)
- `referenced_constants`-- gasper-local constants used in the type (A3)
- `gasper_axioms`       -- non-builtin axioms the proof depends on (A4)
- `proof_provenance`    -- "automated" | "hand-written" | "unknown" (A5)
- `proof_code`          -- pretty-printed proof term (A7 fallback)
- `proof_constants`     -- gasper-local constants used by the proof term
                           (feeds the Python-side proof-DAG severity, B3)
- `decl_start_line` / `decl_end_line` -- source range of the declaration, so
                           the driver side can slice the verbatim proof source
                           out of the gasper checkout (A7)

## The depend-allowed vs must-establish heuristic (A2)

Each telescope binder is tagged with how an implementation audit should treat
it. The heuristic (explicitly provisional; it will be tuned with the gasper
maintainers) is:

1. instance-implicit binders (`[DecidableEq V]`, `[Fintype V]`, ...) are
   **depend-allowed**: they are typeclass plumbing, not audit content.
2. non-`Prop` binders (the model parameters: `Validator`/`Hash` universes,
   `τ : Threshold`, `stake`, `vset`, `parent`, `genesis`, `st : State ...`)
   are **depend-allowed**: they fix the protocol model the theorem speaks
   about; an implementation instantiates them, it does not establish them.
3. `Prop` hypotheses whose head predicate is a *fixed world/model assumption*
   are **depend-allowed**. Concretely: honest-majority and vote-honesty
   assumptions (`two_thirds_good`, `good_votes`) and block-existence /
   height-bound modeling assumptions (`blocks_exist_high_over*`,
   `target_height_bound`). These describe the environment, not the client.
4. every other `Prop` hypothesis is **must-establish**: it asserts a computed
   or structural fact about the state (`k_finalized ...`, `justified ...`,
   `quorum_2 ...`, `not_ancestor ...`, `¬ q_intersection_slashed ...`,
   inequalities between computed heights, ...) that the implementation must
   preserve for the theorem's guarantee to transfer to it.

The head predicate is found by stripping `∀` binders and one layer of `Not`,
then taking the application head constant.
-/

namespace SpecaExport

open Lean

/-- Per-hypothesis classification record. -/
structure HypothesisInfo where
  name    : String
  type    : String
  head    : String  -- fully-qualified head constant of the type ("" if none)
  «class» : String  -- "depend-allowed" | "must-establish"
  deriving Inhabited

private def HypothesisInfo.toJson (h : HypothesisInfo) : Json :=
  Json.mkObj [
    ("name",  Json.str h.name),
    ("type",  Json.str h.type),
    ("head",  Json.str h.head),
    ("class", Json.str h.«class»)
  ]

/-- Per-theorem health record emitted to JSON. -/
structure TheoremHealth where
  name                : String
  resolved            : Bool
  leanStatus          : String        -- "proved" | "unknown"
  sorryFree           : Bool
  choiceFree          : Bool
  nativeFree          : Bool
  «module»            : String        -- source module, "" if unknown
  statement           : String        -- pretty-printed type
  conclusion          : String        -- pretty-printed telescope body (Q)
  hypotheses          : Array HypothesisInfo
  referencedConstants : Array String  -- gasper-local constants in the type
  gasperAxioms        : Array String
  proofProvenance     : String        -- "automated" | "hand-written" | "unknown"
  proofCode           : String        -- pretty-printed proof term
  proofConstants      : Array String  -- gasper-local constants in the proof
  proofSource         : String        -- verbatim source slice (filled in IO)
  declStartLine       : Nat           -- 0 if unknown
  declEndLine         : Nat           -- 0 if unknown
  deriving Inhabited

private def isNativeComputeAxiom (n : Name) : Bool :=
  match (toString n).splitOn "._native." with
  | [_] => false
  | _   => true

/-- Check whether `sub` occurs as a substring of the string representation of `n`. -/
private def nameContains (n : Name) (sub : String) : Bool :=
  match (toString n).splitOn sub with
  | [_] => false
  | _   => true

/-- Axioms that are Lean builtins, not gasper-specific. -/
private def isBuiltinAxiom (n : Name) : Bool :=
  n == ``sorryAx ||
  n == ``Classical.choice ||
  n == ``Lean.trustCompiler ||
  n == ``propext ||
  n == ``Quot.sound ||
  isNativeComputeAxiom n

/-- Constants whose presence in a proof term indicates tactic automation
(decision procedures / proof search) rather than a hand-written proof.
Best-effort (A5): `decide`-style kernel reduction, `omega`-generated
arithmetic certificates, and aesop-generated auxiliary lemmas leave these
markers; a plain `simp`/term proof does not, and is reported "hand-written". -/
private def isAutomationConstant (n : Name) : Bool :=
  n == ``Decidable.decide ||
  n == ``decide ||
  n == `Bool.decide ||
  n == `native_decide ||
  nameContains n "ofReduceBool" ||
  nameContains n "ofReduceNat" ||
  nameContains n "of_decide_eq_true" ||
  nameContains n "Aesop" ||
  nameContains n "Omega"

/-- Is `n` a declaration of the gasper-lean4 project itself? -/
private def isGasperLocal (n : Name) : Bool :=
  Name.isPrefixOf `GasperBeaconChain n

private def dedup (xs : Array Name) : Array Name :=
  xs.foldl (fun acc n => if acc.contains n then acc else acc.push n) #[]

/-- Head predicate of a hypothesis type: strip `∀` binders and one layer of
`Not`, then take the application head constant. -/
private partial def headConst? (e : Expr) : Option Name :=
  match e with
  | .mdata _ b       => headConst? b
  | .forallE _ _ b _ => headConst? b
  | _ =>
    match e.getAppFn with
    | .const n _ =>
      if n == ``Not then
        match e.getAppArgs[0]? with
        | some a => headConst? a
        | none   => some n
      else some n
    | _ => none

/-- Fixed world/model assumptions (see the module docstring, rule 3).
Provisional list; tuned with the gasper maintainers, not hard-coded semantics. -/
private def modelAssumptionLastComponents : List String := [
  "two_thirds_good",
  "good_votes",
  "target_height_bound"
]

private def isModelAssumptionHead (n : Name) : Bool :=
  let last := match n with
    | .str _ s => s
    | _        => toString n
  modelAssumptionLastComponents.contains last || last.startsWith "blocks_exist"

/-- A2 classification. See the module docstring for the documented heuristic. -/
private def classifyHyp (bi : BinderInfo) (isPropHyp : Bool) (head? : Option Name) : String :=
  if bi.isInstImplicit then "depend-allowed"
  else if !isPropHyp then "depend-allowed"
  else match head? with
    | some h => if isModelAssumptionHead h then "depend-allowed" else "must-establish"
    | none   => "must-establish"

private def declModuleName? (env : Environment) (n : Name) : Option Name :=
  match env.getModuleIdxFor? n with
  | some idx => env.header.moduleNames[idx]?
  | none => none

/-- Classify one target theorem name with enriched metadata (A1-A7). -/
def classify (env : Environment) (target : Name) : CoreM TheoremHealth := do
  if !env.contains target then
    return {
      name := toString target, resolved := false, leanStatus := "unknown",
      sorryFree := false, choiceFree := false, nativeFree := false, «module» := "",
      statement := "", conclusion := "", hypotheses := #[],
      referencedConstants := #[], gasperAxioms := #[],
      proofProvenance := "unknown", proofCode := "", proofConstants := #[],
      proofSource := "", declStartLine := 0, declEndLine := 0
    }
  let ax ← collectAxioms target
  let hasSorry  := ax.contains ``sorryAx
  let hasChoice := ax.contains ``Classical.choice
  let hasNative := ax.contains ``Lean.trustCompiler || ax.any isNativeComputeAxiom
  let status := if hasSorry then "unknown" else "proved"
  let mod := match declModuleName? env target with
    | some m => toString m
    | none => ""
  -- Retrieve declaration info for enrichment
  let ci := (env.find? target).get!
  let type := ci.type
  let value? : Option Expr := match ci with
    | .thmInfo tv    => some tv.value
    | .defnInfo dv   => some dv.value
    | .opaqueInfo ov => some ov.value
    | _              => none
  -- A4: gasper-local axioms (filter out Lean builtins)
  let gasperAx := (ax.filter fun a => !isBuiltinAxiom a).map toString
  -- A3: gasper-local constants referenced by the type
  let refConsts := (dedup (type.getUsedConstants.filter isGasperLocal)).map toString
  -- B3 feed: gasper-local constants referenced by the proof term
  let proofConsts := match value? with
    | some v => (dedup (v.getUsedConstants.filter isGasperLocal)).map toString
    | none   => #[]
  -- A5: proof provenance (pure check on proof-term constants)
  let provenance := match value? with
    | some v =>
      if v.getUsedConstants.any isAutomationConstant then "automated" else "hand-written"
    | none => "unknown"
  -- A7: source range of the declaration (the driver slices the verbatim text)
  let (startLine, endLine) ← do
    match ← findDeclarationRanges? target with
    | some rs => pure (rs.range.pos.line, rs.range.endPos.line)
    | none    => pure (0, 0)
  -- A1, A2, A7: pretty-printing and telescope require MetaM
  let (stmt, concl, hyps, proofCode) ← Meta.MetaM.run' do
    -- A1: pretty-print the statement (type)
    let stmtFmt ← Meta.ppExpr type
    let stmt := toString stmtFmt
    -- A2: hypothesis telescope, and the conclusion = the telescope body
    let (hyps, concl) ← Meta.forallTelescope type fun fvars body => do
      let mut result : Array HypothesisInfo := #[]
      for fvar in fvars do
        let ldecl ← fvar.fvarId!.getDecl
        let hypName := ldecl.userName.toString
        let hypTypeFmt ← Meta.ppExpr ldecl.type
        let hypType := toString hypTypeFmt
        let head? := headConst? ldecl.type
        let isPropHyp ← Meta.isProp ldecl.type
        let cls := classifyHyp ldecl.binderInfo isPropHyp head?
        let headStr := match head? with
          | some h => toString h
          | none   => ""
        result := result.push {
          name := hypName, type := hypType, head := headStr, «class» := cls
        }
      let conclFmt ← Meta.ppExpr body
      pure (result, toString conclFmt)
    -- A7 fallback: pretty-print the proof value
    let proofCode ← match value? with
      | some v => do
        let fmt ← Meta.ppExpr v
        pure (toString fmt)
      | none => pure ""
    pure (stmt, concl, hyps, proofCode)
  return {
    name := toString target, resolved := true, leanStatus := status,
    sorryFree := !hasSorry, choiceFree := !hasChoice, nativeFree := !hasNative,
    «module» := mod, statement := stmt, conclusion := concl, hypotheses := hyps,
    referencedConstants := refConsts, gasperAxioms := gasperAx,
    proofProvenance := provenance, proofCode := proofCode,
    proofConstants := proofConsts, proofSource := "",
    declStartLine := startLine, declEndLine := endLine
  }

private def TheoremHealth.toJson (h : TheoremHealth) : Json :=
  Json.mkObj [
    ("name",                 Json.str h.name),
    ("resolved",             Json.bool h.resolved),
    ("lean_status",          Json.str h.leanStatus),
    ("sorry_free",           Json.bool h.sorryFree),
    ("choice_free",          Json.bool h.choiceFree),
    ("native_free",          Json.bool h.nativeFree),
    ("module",               Json.str h.«module»),
    ("statement",            Json.str h.statement),
    ("conclusion",           Json.str h.conclusion),
    ("hypotheses",           Json.arr (h.hypotheses.map HypothesisInfo.toJson)),
    ("referenced_constants", Json.arr (h.referencedConstants.map Json.str)),
    ("gasper_axioms",        Json.arr (h.gasperAxioms.map Json.str)),
    ("proof_provenance",     Json.str h.proofProvenance),
    ("proof_code",           Json.str h.proofCode),
    ("proof_constants",      Json.arr (h.proofConstants.map Json.str)),
    ("proof_source",         Json.str h.proofSource),
    ("decl_start_line",      Json.num h.declStartLine),
    ("decl_end_line",        Json.num h.declEndLine)
  ]

/-- Classify every target theorem name. -/
def classifyAll (env : Environment) (targets : List Name) : CoreM (Array TheoremHealth) := do
  let mut arr : Array TheoremHealth := #[]
  for t in targets do
    arr := arr.push (← classify env t)
  return arr

/-- Render the full health report. -/
def render (records : Array TheoremHealth) : Json :=
  Json.mkObj [
    ("project", Json.str "GasperBeaconChain"),
    ("plugin",  Json.str "speca-lean4-plugin"),
    ("theorems", Json.arr (records.map TheoremHealth.toJson))
  ]

/-- Classify a list of target theorem names and render the full health report.
(Kept for API compatibility; `Main` uses `classifyAll` + `render` so it can
attach the verbatim proof source between the two.) -/
def report (env : Environment) (targets : List Name) : CoreM Json := do
  return render (← classifyAll env targets)

end SpecaExport
