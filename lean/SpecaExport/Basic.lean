import Lean.Util.CollectAxioms
import Lean.Data.Json
import Lean.Meta
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
- `hypotheses`          -- telescope decomposition with depend-allowed / must-establish (A2)
- `referenced_constants`-- constants used in the type expression (A3)
- `gasper_axioms`       -- non-builtin axioms the proof depends on (A4)
- `proof_provenance`    -- "automated" | "hand-written" | "unknown" (A5)
- `proof_code`          -- pretty-printed proof term (A7)
-/

namespace SpecaExport

open Lean

/-- Per-hypothesis classification record. -/
structure HypothesisInfo where
  name    : String
  type    : String
  «class» : String  -- "depend-allowed" | "must-establish"
  deriving Inhabited

private def HypothesisInfo.toJson (h : HypothesisInfo) : Json :=
  Json.mkObj [
    ("name",  Json.str h.name),
    ("type",  Json.str h.type),
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
  hypotheses          : Array HypothesisInfo
  referencedConstants : Array String
  gasperAxioms        : Array String
  proofProvenance     : String        -- "automated" | "hand-written" | "unknown"
  proofCode           : String        -- pretty-printed proof term
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

/-- Constants whose presence in a proof term indicates decision-procedure automation. -/
private def isAutomationConstant (n : Name) : Bool :=
  n == ``Decidable.decide ||
  n == ``decide ||
  n == `Bool.decide ||
  n == `native_decide ||
  nameContains n "ofReduceBool" ||
  nameContains n "ofReduceNat"

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
      statement := "", hypotheses := #[], referencedConstants := #[],
      gasperAxioms := #[], proofProvenance := "unknown", proofCode := ""
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
  -- A3: referenced constants from the type
  let refConsts := type.getUsedConstants.map toString
  -- A5: proof provenance (pure check on proof-term constants)
  let provenance := match value? with
    | some v =>
      if v.getUsedConstants.any isAutomationConstant then "automated" else "hand-written"
    | none => "unknown"
  -- A1, A2, A7: pretty-printing and telescope require MetaM
  let (stmt, hyps, proofCode) ← Meta.MetaM.run' do
    -- A1: pretty-print the statement (type)
    let stmtFmt ← Meta.ppExpr type
    let stmt := toString stmtFmt
    -- A2: hypothesis telescope
    let hyps ← Meta.forallTelescope type fun fvars _body => do
      let mut result : Array HypothesisInfo := #[]
      for fvar in fvars do
        let ldecl ← fvar.fvarId!.getDecl
        let hypName := ldecl.userName.toString
        let hypTypeFmt ← Meta.ppExpr ldecl.type
        let hypType := toString hypTypeFmt
        let cls ←
          if ldecl.binderInfo.isInstImplicit then
            pure "depend-allowed"
          else if ← Meta.isProp ldecl.type then
            pure "must-establish"
          else
            pure "depend-allowed"
        result := result.push { name := hypName, type := hypType, «class» := cls }
      return result
    -- A7: pretty-print the proof value
    let proofCode ← match value? with
      | some v => do
        let fmt ← Meta.ppExpr v
        pure (toString fmt)
      | none => pure ""
    pure (stmt, hyps, proofCode)
  return {
    name := toString target, resolved := true, leanStatus := status,
    sorryFree := !hasSorry, choiceFree := !hasChoice, nativeFree := !hasNative,
    «module» := mod, statement := stmt, hypotheses := hyps,
    referencedConstants := refConsts, gasperAxioms := gasperAx,
    proofProvenance := provenance, proofCode := proofCode
  }

private def TheoremHealth.toJson (h : TheoremHealth) : Json :=
  Json.mkObj [
    ("name",                Json.str h.name),
    ("resolved",            Json.bool h.resolved),
    ("lean_status",         Json.str h.leanStatus),
    ("sorry_free",          Json.bool h.sorryFree),
    ("choice_free",         Json.bool h.choiceFree),
    ("native_free",         Json.bool h.nativeFree),
    ("module",              Json.str h.«module»),
    ("statement",           Json.str h.statement),
    ("hypotheses",          Json.arr (h.hypotheses.map HypothesisInfo.toJson)),
    ("referenced_constants", Json.arr (h.referencedConstants.map Json.str)),
    ("gasper_axioms",       Json.arr (h.gasperAxioms.map Json.str)),
    ("proof_provenance",    Json.str h.proofProvenance),
    ("proof_code",          Json.str h.proofCode)
  ]

/-- Classify a list of target theorem names and render the full health report. -/
def report (env : Environment) (targets : List Name) : CoreM Json := do
  let mut arr : Array Json := #[]
  for t in targets do
    let h ← classify env t
    arr := arr.push h.toJson
  return Json.mkObj [
    ("project", Json.str "GasperBeaconChain"),
    ("plugin",  Json.str "speca-lean4-plugin"),
    ("theorems", Json.arr arr)
  ]

end SpecaExport
