import SpecaExport.Basic
import SpecaExport.Driver
-- ethereum-vuln-dataset track (M2 Track C / c-1, speca#146): Critical/High
-- vulnerability invariants formalized as Lean theorems (named implementation
-- obligations => named-predicate conclusions; the shallow implications are
-- proved, which the exporter reports as lean_status=proved). Registered in
-- theorem_map_ethvuln.json as PROP-lean-ethvuln-* and exported by
-- `lake exe speca-export-ethvuln` (entry point MainEthVuln.lean) -- NOT by
-- the gasper `speca-export`.
import SpecaExport.EthVuln
