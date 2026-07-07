import Lake
open Lake DSL

/-!
`speca-lean4-plugin` — Lean side.

A thin lake workspace that depends on `NyxFoundation/gasper-lean4` and exposes a
single executable, `speca-export`, which certifies the proof health of the
target theorems (via `collectAxioms`, the same mechanism gasper-lean4's own
`#mr_audit_json` uses) and emits a machine-readable *theorem-health JSON*.

The health JSON is the Lean-dependent artifact. The theorem -> `01e` property
mapping and scope resolution live in the Python driver (`src/speca_lean4/`),
so the mapping table can be tuned to match the fusaka `01e` benchmark without
recompiling Lean. See ../README.md for the full CLI contract.

Pin note: gasper-lean4 is pinned by git rev at build time via `--gasper-ref`
(the Python driver rewrites the `require` rev before `lake build` in CI, or the
rev is committed to `lake-manifest.json`). The default branch is `main`.
-/

package «SpecaLean4Plugin» where
  -- keep the option set minimal; we only need CollectAxioms + Json
  leanOptions := #[
    ⟨`autoImplicit, false⟩,
    ⟨`relaxedAutoImplicit, false⟩
  ]

-- gasper-lean4 provides the proved Casper FFG theorems we export.
-- Rev is pinned in lake-manifest.json; override with --gasper-ref in CI.
require GasperBeaconChain from git
  "https://github.com/NyxFoundation/gasper-lean4.git" @ "main"

@[default_target]
lean_lib «SpecaExport» where

@[default_target]
lean_exe «speca-export» where
  root := `Main
