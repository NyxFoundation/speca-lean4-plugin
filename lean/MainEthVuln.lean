import SpecaExport.Driver
-- The ethereum-vuln-dataset track (M2 Track C / c-1, speca#146) lives in this
-- workspace itself: `SpecaExport.EthVuln` is the root module that imports
-- `Common` and every `Props/*` file, so importing it here (compile time, so
-- lake builds it into this executable's closure) and passing it to
-- `driverMain` (run time, so `importModules` loads its declarations into the
-- environment the exporter resolves targets against) is what makes every
-- `EthVulnFormalProps.*` target resolve. The gasper entry point `Main.lean`
-- deliberately does NOT import it: the gasper export stays byte-compatible.
import SpecaExport.EthVuln

/-!
`speca-export-ethvuln` entry point for the **ethereum-vuln-dataset** track.

    lake exe speca-export-ethvuln --targets <file> --output <file>

Same driver and CLI contract as `speca-export` (see `SpecaExport.Driver`), with
`ethVulnConfig` (`EthVulnFormalProps` is the project-local namespace, no model
assumptions) and the in-repo root module. Pass `--src-root .` (run from
`lean/`) for the A7 verbatim `proof_source` slices: the driver looks under the
given roots and `.lake/packages/*`, and these `.lean` files are this package's
own, not a dependency's.

Proof status is reported honestly, from `collectAxioms` alone: since the
PR #24 review revision the 66 shallow implications are proved, so the health
JSON says `lean_status = "proved"`, `sorry_free = true`; a regression to
`sorry` would be reported as `unknown` / `false` with no change here.
-/

open SpecaExport

unsafe def main (args : List String) : IO Unit :=
  driverMain ethVulnConfig #[`SpecaExport.EthVuln] args
