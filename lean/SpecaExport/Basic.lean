import Lean.Util.CollectAxioms
import Lean.Data.Json
import Lean.Meta
import Lean.DeclarationRange
import Lean.Structure
import Lean.DocString
-- NOTE: this module is *project-agnostic* — it imports no formalization.
-- Which project's modules are loaded (and which namespace counts as
-- "project-local") is decided by the workspace entry point: `lean/Main.lean`
-- for gasper-lean4, `lean-ethtotal/Main.lean` for eth-total-supply-safety.
-- Both pass a `ProjectConfig` (below) into `classifyAll`/`render`.

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
- `referenced_defs_expanded` -- recursively pretty-printed *definitions* of the
                           gasper-local constants used in the statement
                           (structure fields, inductive constructors, def
                           signature+body), so the LLM sees the structure a
                           theorem operates on, not just its name (A3+,
                           issue #16). Bounded: breadth-first to depth
                           `expansionMaxDepth` (2), at most `expansionMaxTotal`
                           (24) definitions, deduped; mathlib/Lean-core
                           constants and compiler-generated auxiliaries are
                           never expanded.
- `doc_string`          -- the declaration's docstring (`findDocString?`);
                           `""` when the theorem has none — empty, never
                           fabricated (A7+, issue #17)

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

/-- Which formalization is being exported.

The exporter itself is project-agnostic; everything project-specific is in this
record, supplied by the workspace entry point:

* `nsPrefix` — the namespace that counts as *project-local*. Only constants
  under it are reported in `referenced_constants` / `proof_constants` and only
  they are ever expanded (`referenced_defs_expanded`); mathlib and Lean core
  are never expanded.
* `projectName` — the `project` field of the health report.
* `modelAssumptionHeads` / `modelAssumptionPrefixes` — rule 3 of the A2
  heuristic: `Prop` hypotheses whose head predicate is a fixed world/model
  assumption are *depend-allowed*. This list is project knowledge, so an empty
  list is the honest default: with no entries, every `Prop` hypothesis is
  must-establish and nothing is silently excused from the audit. -/
structure ProjectConfig where
  nsPrefix                : Name
  projectName             : String
  modelAssumptionHeads    : List String := []
  modelAssumptionPrefixes : List String := []
  deriving Inhabited

/-- gasper-lean4 (`GasperBeaconChain.*`). The model assumptions are the
honest-majority / vote-honesty and block-existence / height-bound modeling
hypotheses; see the module docstring, rule 3. Provisional list, tuned with the
gasper maintainers, not hard-coded semantics. -/
def gasperConfig : ProjectConfig where
  nsPrefix := `GasperBeaconChain
  projectName := "GasperBeaconChain"
  modelAssumptionHeads := ["two_thirds_good", "good_votes", "target_height_bound"]
  modelAssumptionPrefixes := ["blocks_exist"]

/-- eth-total-supply-safety (`EthTotal.*`).

No model-assumption list: the formalization has no honest-majority-style world
assumptions. Its `Prop` hypotheses are ledger-shape and accounting facts
(`Distinct l`, support-coverage, `L'.bal a ≤ L.bal a`, `L'.live = L.live`, …)
that a client implementation must actually establish, so every one of them is
must-establish. The non-`Prop` binders (`L L' : Ledger A`, `l : List A`, the
universe/type parameters) stay depend-allowed under rule 2. -/
def ethTotalConfig : ProjectConfig where
  nsPrefix := `EthTotal
  projectName := "EthTotal"

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

/-- One recursively-expanded gasper-local definition (A3+, issue #16). -/
structure ExpandedDef where
  name : String
  kind : String  -- "structure" | "inductive" | "def" | "theorem" | "axiom" |
                 -- "opaque" | "constructor" | "recursor" | "quotient"
  pp   : String  -- pretty-printed definition (fields / constructors / body)
  deriving Inhabited

private def ExpandedDef.toJson (d : ExpandedDef) : Json :=
  Json.mkObj [
    ("name", Json.str d.name),
    ("kind", Json.str d.kind),
    ("pp",   Json.str d.pp)
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
  referencedDefsExpanded : Array ExpandedDef  -- A3+ (issue #16)
  docString           : String        -- A7+ (issue #17); "" if absent
  exportError         : String        -- "" unless enrichment itself failed
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

/-- Is `n` a declaration of the exported project itself (as opposed to mathlib
or Lean core)? -/
private def isProjectLocal (cfg : ProjectConfig) (n : Name) : Bool :=
  Name.isPrefixOf cfg.nsPrefix n

private def dedup (xs : Array Name) : Array Name :=
  xs.foldl (fun acc n => if acc.contains n then acc else acc.push n) #[]

/-! ## A3+ (issue #16) — recursive expansion of gasper-local definitions

For each gasper-local constant a theorem's statement uses, export its
*definition* (structure fields / inductive constructors / def signature+body),
then recurse over the gasper-local constants that definition uses. The
recursion is honestly bounded and the bounds are stated here, in code:
breadth-first, `expansionMaxDepth` levels from the statement's constants, at
most `expansionMaxTotal` definitions total, deduped. Mathlib/Lean-core
constants are never expanded (`isGasperLocal` gate), nor are
compiler-generated auxiliaries. -/

/-- Maximum recursion depth for `referenced_defs_expanded` (level 1 = the
constants in the statement itself). -/
def expansionMaxDepth : Nat := 2

/-- Maximum total number of expanded definitions per theorem. -/
def expansionMaxTotal : Nat := 24

/-- Cap on one expanded definition's pretty-printed text; longer text is
truncated with an explicit marker (never silently). -/
def expansionPpMaxLen : Nat := 4000

private def truncatePp (s : String) : String :=
  if s.length ≤ expansionPpMaxLen then s
  else String.mk (s.toList.take expansionPpMaxLen) ++ "\n-- [truncated by speca-export: pp longer than cap]"

/-- Compiler-generated auxiliary declarations we never expand: recursors and
cases/brec machinery, noConfusion, structure constructors (`mk` — the
structure itself is expanded instead), sizeOf, equation/match auxiliaries and
internal (`_`-prefixed) names. -/
private def isAuxiliaryDecl (n : Name) : Bool :=
  let last := match n with
    | .str _ s => s
    | _        => ""
  n.isInternal ||
  last == "rec" || last == "recOn" || last == "casesOn" || last == "brecOn" ||
  last == "below" || last == "ibelow" || last == "ndrec" || last == "mk" ||
  last == "noConfusion" || last == "noConfusionType" || last == "sizeOf" ||
  last == "eq_def" || last.startsWith "match_" || last.startsWith "proof_" ||
  (last.startsWith "eq_" && (last.drop 3).isNat)

/-- Pretty-print one definition: `(kind, pp, constants used by the definition)`.
Structures list their fields (via the projection signatures), inductives their
constructors, defs their signature and body. -/
private def expandOne (env : Environment) (n : Name) :
    Meta.MetaM (String × String × Array Name) := do
  match env.find? n with
  | none => return ("unknown", "", #[])
  | some ci =>
    match ci with
    | .inductInfo iv => do
      let header ← Meta.ppExpr iv.type
      if isStructure env n then
        let mut s := s!"structure {n} : {header}"
        let mut used : Array Name := iv.type.getUsedConstants
        for f in getStructureFields env n do
          match getProjFnForField? env n f with
          | some proj =>
            match env.find? proj with
            | some pci => do
              let t ← Meta.ppExpr pci.type
              s := s ++ s!"\n  {f} : {t}"
              used := used ++ pci.type.getUsedConstants
            | none => pure ()
          | none => pure ()
        return ("structure", truncatePp s, used)
      else
        let mut s := s!"inductive {n} : {header}"
        let mut used : Array Name := iv.type.getUsedConstants
        for c in iv.ctors do
          match env.find? c with
          | some cci => do
            let t ← Meta.ppExpr cci.type
            s := s ++ s!"\n  | {c} : {t}"
            used := used ++ cci.type.getUsedConstants
          | none => pure ()
        return ("inductive", truncatePp s, used)
    | .defnInfo dv => do
      let t ← Meta.ppExpr dv.type
      let v ← Meta.ppExpr dv.value
      return ("def", truncatePp s!"def {n} : {t} :=\n  {v}",
              dv.type.getUsedConstants ++ dv.value.getUsedConstants)
    | .thmInfo tv => do
      let t ← Meta.ppExpr tv.type
      return ("theorem", truncatePp s!"theorem {n} : {t}", tv.type.getUsedConstants)
    | .axiomInfo av => do
      let t ← Meta.ppExpr av.type
      return ("axiom", truncatePp s!"axiom {n} : {t}", av.type.getUsedConstants)
    | .opaqueInfo ov => do
      let t ← Meta.ppExpr ov.type
      return ("opaque", truncatePp s!"opaque {n} : {t}", ov.type.getUsedConstants)
    | .ctorInfo cv => do
      let t ← Meta.ppExpr cv.type
      return ("constructor", truncatePp s!"{n} : {t}", cv.type.getUsedConstants)
    | .recInfo rv => do
      let t ← Meta.ppExpr rv.type
      return ("recursor", truncatePp s!"{n} : {t}", rv.type.getUsedConstants)
    | .quotInfo qv => do
      let t ← Meta.ppExpr qv.type
      return ("quotient", truncatePp s!"{n} : {t}", qv.type.getUsedConstants)

/-- Breadth-first expansion of the project-local definitions reachable from
`roots` (the statement's referenced constants). Bounded by `expansionMaxDepth`
levels and `expansionMaxTotal` total, deduped; only non-auxiliary declarations
under `cfg.nsPrefix` are expanded. -/
def expandReferencedDefs (cfg : ProjectConfig) (env : Environment) (roots : Array Name) :
    Meta.MetaM (Array ExpandedDef) := do
  let mut out : Array ExpandedDef := #[]
  let mut seen : Array Name := #[]
  let mut frontier : Array Name := #[]
  for r in roots do
    if isProjectLocal cfg r && !isAuxiliaryDecl r && !seen.contains r then
      seen := seen.push r
      frontier := frontier.push r
  for _ in [0:expansionMaxDepth] do
    let mut next : Array Name := #[]
    for n in frontier do
      if out.size < expansionMaxTotal then
        let (kind, pp, used) ← expandOne env n
        if !pp.isEmpty then
          out := out.push { name := toString n, kind := kind, pp := pp }
          for u in dedup used do
            if isProjectLocal cfg u && !isAuxiliaryDecl u && !seen.contains u then
              seen := seen.push u
              next := next.push u
    frontier := next
  return out

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

/-- Is this head predicate one of the project's fixed world/model assumptions
(see the module docstring, rule 3)? The list lives in `ProjectConfig`; a
project that declares none has every `Prop` hypothesis must-establish. -/
private def isModelAssumptionHead (cfg : ProjectConfig) (n : Name) : Bool :=
  let last := match n with
    | .str _ s => s
    | _        => toString n
  cfg.modelAssumptionHeads.contains last ||
    cfg.modelAssumptionPrefixes.any (fun p => last.startsWith p)

/-- A2 classification. See the module docstring for the documented heuristic. -/
private def classifyHyp (cfg : ProjectConfig) (bi : BinderInfo) (isPropHyp : Bool)
    (head? : Option Name) : String :=
  if bi.isInstImplicit then "depend-allowed"
  else if !isPropHyp then "depend-allowed"
  else match head? with
    | some h => if isModelAssumptionHead cfg h then "depend-allowed" else "must-establish"
    | none   => "must-establish"

private def declModuleName? (env : Environment) (n : Name) : Option Name :=
  match env.getModuleIdxFor? n with
  | some idx => env.header.moduleNames[idx]?
  | none => none

/-- Classify one target theorem name with enriched metadata (A1-A7). -/
def classify (cfg : ProjectConfig) (env : Environment) (target : Name) : CoreM TheoremHealth := do
  if !env.contains target then
    return {
      name := toString target, resolved := false, leanStatus := "unknown",
      sorryFree := false, choiceFree := false, nativeFree := false, «module» := "",
      statement := "", conclusion := "", hypotheses := #[],
      referencedConstants := #[], gasperAxioms := #[],
      proofProvenance := "unknown", proofCode := "", proofConstants := #[],
      proofSource := "", declStartLine := 0, declEndLine := 0,
      referencedDefsExpanded := #[], docString := "", exportError := ""
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
  -- A4: project-local axioms (filter out Lean builtins)
  let gasperAx := (ax.filter fun a => !isBuiltinAxiom a).map toString
  -- A3: project-local constants referenced by the type
  let refConstNames := dedup (type.getUsedConstants.filter (isProjectLocal cfg))
  let refConsts := refConstNames.map toString
  -- B3 feed: project-local constants referenced by the proof term
  let proofConsts := match value? with
    | some v => (dedup (v.getUsedConstants.filter (isProjectLocal cfg))).map toString
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
  -- A7+ (issue #17): the declaration's docstring; "" (never fabricated) when absent
  let docStr := (← findDocString? env target).getD ""
  -- A1, A2, A7: pretty-printing and telescope require MetaM
  let (stmt, concl, hyps, proofCode, expandedDefs) ← Meta.MetaM.run' do
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
        let cls := classifyHyp cfg ldecl.binderInfo isPropHyp head?
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
    -- A3+ (issue #16): recursively expand the project-local definitions the
    -- statement references (bounded; see expansionMaxDepth/expansionMaxTotal)
    let expandedDefs ← expandReferencedDefs cfg env refConstNames
    pure (stmt, concl, hyps, proofCode, expandedDefs)
  return {
    name := toString target, resolved := true, leanStatus := status,
    sorryFree := !hasSorry, choiceFree := !hasChoice, nativeFree := !hasNative,
    «module» := mod, statement := stmt, conclusion := concl, hypotheses := hyps,
    referencedConstants := refConsts, gasperAxioms := gasperAx,
    proofProvenance := provenance, proofCode := proofCode,
    proofConstants := proofConsts, proofSource := "",
    declStartLine := startLine, declEndLine := endLine,
    referencedDefsExpanded := expandedDefs, docString := docStr,
    exportError := ""
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
    ("referenced_defs_expanded",
      Json.arr (h.referencedDefsExpanded.map ExpandedDef.toJson)),
    -- `project_axioms` is the current name; `gasper_axioms` is kept as an
    -- alias so an older Python driver reading the gasper key still works.
    ("project_axioms",       Json.arr (h.gasperAxioms.map Json.str)),
    ("gasper_axioms",        Json.arr (h.gasperAxioms.map Json.str)),
    ("proof_provenance",     Json.str h.proofProvenance),
    ("proof_code",           Json.str h.proofCode),
    ("proof_constants",      Json.arr (h.proofConstants.map Json.str)),
    ("proof_source",         Json.str h.proofSource),
    ("doc_string",           Json.str h.docString),
    ("export_error",         Json.str h.exportError),
    ("decl_start_line",      Json.num h.declStartLine),
    ("decl_end_line",        Json.num h.declEndLine)
  ]

/-- Classify one target, degrading honestly if the *enrichment* blows up.

Pretty-printing and the telescope run the elaborator, so a pathological
statement can exhaust heartbeats or fail even though the theorem itself is
fine. Losing the whole export to one such theorem would be worse than useless,
and silently dropping it would misreport coverage. So the failure is caught and
recorded: `lean_status` degrades to `unknown` (never `proved` — we did not
complete the check) and `export_error` carries the reason. `sorry_free` is
reported from `collectAxioms` when that part succeeded, and is `false` when it
did not. -/
def classifyOne (cfg : ProjectConfig) (env : Environment) (target : Name) :
    CoreM TheoremHealth := do
  try
    classify cfg env target
  catch e =>
    let msg ← (do pure (← e.toMessageData.toString)) <|> pure "unrenderable exception"
    -- the axiom check is cheap and independent of pretty-printing; try it alone
    -- so a pp failure does not also cost us the sorry-freedom fact
    let axOk ← (do
      let ax ← collectAxioms target
      pure (some (!ax.contains ``sorryAx))) <|> pure none
    return {
      name := toString target, resolved := env.contains target,
      leanStatus := "unknown",
      sorryFree := axOk.getD false, choiceFree := false, nativeFree := false,
      «module» := "", statement := "", conclusion := "", hypotheses := #[],
      referencedConstants := #[], gasperAxioms := #[],
      proofProvenance := "unknown", proofCode := "", proofConstants := #[],
      proofSource := "", declStartLine := 0, declEndLine := 0,
      referencedDefsExpanded := #[], docString := "",
      exportError := msg
    }

/-- Classify every target theorem name. -/
def classifyAll (cfg : ProjectConfig) (env : Environment) (targets : List Name) :
    CoreM (Array TheoremHealth) := do
  let mut arr : Array TheoremHealth := #[]
  for t in targets do
    arr := arr.push (← classifyOne cfg env t)
  return arr

/-- Render the full health report. -/
def render (cfg : ProjectConfig) (records : Array TheoremHealth) : Json :=
  Json.mkObj [
    ("project", Json.str cfg.projectName),
    ("plugin",  Json.str "speca-lean4-plugin"),
    ("theorems", Json.arr (records.map TheoremHealth.toJson))
  ]

/-- Classify a list of target theorem names and render the full health report.
(Kept for API compatibility; `Main` uses `classifyAll` + `render` so it can
attach the verbatim proof source between the two.) -/
def report (cfg : ProjectConfig) (env : Environment) (targets : List Name) : CoreM Json := do
  return render cfg (← classifyAll cfg env targets)

end SpecaExport
