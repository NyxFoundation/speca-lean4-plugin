import SpecaExport.Driver
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
`speca-export` entry point for the **gasper-lean4** workspace.

    lake exe speca-export --targets <file> [--output <file>]

Everything but the project choice lives in `SpecaExport.Driver`; see that
module for the CLI contract and the A7/A7+ source-slicing behaviour. The
sibling `lean-ethtotal/Main.lean` is the same two lines for
eth-total-supply-safety.
-/

open SpecaExport

unsafe def main (args : List String) : IO Unit :=
  driverMain gasperConfig #[`GasperBeaconChain.Core.All, `GasperBeaconChain.Executable.All] args
