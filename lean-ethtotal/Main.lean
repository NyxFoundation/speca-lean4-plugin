import SpecaExport.Driver
-- `EthTotal` is the canonical root of eth-total-supply-safety: the primitive
-- definitions (`AtomicDef.*`), the derivation and Ethereum-concept lemma
-- layers (`Lemmata.Derives.*`, `Lemmata.EthConcepts.*`), the main theorems
-- (`Theorem.*`) and the repo's own axiom audit (`EthTotal.Audit`).
-- `EthTotal.Extentions.Audit` is a second root: it imports all 65
-- `Extentions/*` modules (the audit-context results), which the canonical root
-- deliberately does not. Import BOTH so every target resolves.
import EthTotal
import EthTotal.Extentions.Audit

/-!
`speca-export` entry point for the **eth-total-supply-safety** workspace.

    lake exe speca-export --targets <file> --output <file> \
        --src-root ../external/eth-total-supply-safety

Everything but the project choice lives in `SpecaExport.Driver`; see that
module for the CLI contract and the A7/A7+ source-slicing behaviour.
`--src-root` is needed here (and not in the gasper workspace) because
`EthTotal` is a *path* dependency: its `.lean` sources live in the submodule
checkout, not under `.lake/packages/`.
-/

open SpecaExport

unsafe def main (args : List String) : IO Unit :=
  driverMain ethTotalConfig #[`EthTotal, `EthTotal.Extentions.Audit] args
