import Lean.Util.CollectAxioms
import Lean.Data.Json
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

* `proved`   — the declaration exists, is a real proof, and its proof does not
               depend on `sorryAx`.
* `unknown`  — the declaration depends on `sorryAx` (proof is incomplete), or
               the name cannot be resolved in the environment.

We deliberately do NOT collapse `Classical.choice` into `unknown`: gasper-lean4
is constructive (choice-free) by design, so we surface a `choiceFree` flag for
auditing but keep `proved` status as long as there is no `sorry`. `counterexample`
is not represented yet — gasper's theorems are proofs, not refutations.

This mirrors `GasperBeaconChain.Audit.Meta.AuditJson`; we only narrow the scope
from "all audited decls" to "the explicit target list" the plugin cares about.
-/

namespace SpecaExport

open Lean

/-- Per-theorem health record emitted to JSON. -/
structure TheoremHealth where
  name        : String
  resolved    : Bool
  leanStatus  : String        -- "proved" | "unknown"
  sorryFree   : Bool
  choiceFree  : Bool
  nativeFree  : Bool
  «module»    : String        -- source module, "" if unknown
  deriving Inhabited

private def isNativeComputeAxiom (n : Name) : Bool :=
  match (toString n).splitOn "._native." with
  | [_] => false
  | _   => true

private def declModuleName? (env : Environment) (n : Name) : Option Name :=
  match env.getModuleIdxFor? n with
  | some idx => env.header.moduleNames[idx]?
  | none => none

/-- Classify one target theorem name. -/
def classify (env : Environment) (target : Name) : CoreM TheoremHealth := do
  if !env.contains target then
    return {
      name := toString target, resolved := false, leanStatus := "unknown",
      sorryFree := false, choiceFree := false, nativeFree := false, «module» := ""
    }
  let ax ← collectAxioms target
  let hasSorry  := ax.contains ``sorryAx
  let hasChoice := ax.contains ``Classical.choice
  let hasNative := ax.contains ``Lean.trustCompiler || ax.any isNativeComputeAxiom
  let status := if hasSorry then "unknown" else "proved"
  let mod := match declModuleName? env target with
    | some m => toString m
    | none => ""
  return {
    name := toString target, resolved := true, leanStatus := status,
    sorryFree := !hasSorry, choiceFree := !hasChoice, nativeFree := !hasNative,
    «module» := mod
  }

private def TheoremHealth.toJson (h : TheoremHealth) : Json :=
  Json.mkObj [
    ("name",       Json.str h.name),
    ("resolved",   Json.bool h.resolved),
    ("lean_status", Json.str h.leanStatus),
    ("sorry_free", Json.bool h.sorryFree),
    ("choice_free", Json.bool h.choiceFree),
    ("native_free", Json.bool h.nativeFree),
    ("module",     Json.str h.«module»)
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
