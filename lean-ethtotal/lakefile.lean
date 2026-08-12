import Lake
open Lake DSL

/-!
`speca-lean4-plugin` — Lean side for **eth-total-supply-safety**.

The second exporter workspace. It is the `lean/` workspace's twin: same
`SpecaExport` sources (shared verbatim via `srcDir := "../lean"`, no fork), a
different formalization and a different `ProjectConfig`.

Why a separate workspace rather than one lake package with two `require`s:
the two formalizations pin *different Lean toolchains* — gasper-lean4 builds on
`leanprover/lean4:v4.31.0`, eth-total-supply-safety on
`leanprover/lean4:v4.33.0-rc1` (see the respective `lean-toolchain` files) —
so they cannot share one environment.

Dependency pins:
- `EthTotal` comes from the **submodule checkout**, not from git: the audited
  revision is whatever `external/eth-total-supply-safety` points at, so the
  submodule commit *is* the pin, and there is no way for the exported
  `lean_status` to describe a different revision than the one in the tree.
- `mathlib` is required here at the exact revision the submodule's own
  `lake-manifest.json` pins. eth-total-supply-safety asks for `master`, which
  moves; a root requirement wins over a dependency's, so this line is what
  keeps the build reproducible. Only `Mathlib.Data.Nat.Notation` is actually
  imported by the formalization (from `AtomicDef/Finitary.lean` and
  `AtomicDef/Event.lean`), so the mathlib surface built here is tiny.
-/

package «SpecaLean4PluginEthTotal» where
  -- keep the option set minimal; we only need CollectAxioms + Json
  leanOptions := #[
    ⟨`autoImplicit, false⟩,
    ⟨`relaxedAutoImplicit, false⟩
  ]

require "leanprover-community" / "mathlib" @
  git "12ab8e82f8447fa639dabe9ffeda74436b72be31"

require EthTotal from "../external/eth-total-supply-safety"

-- The exporter sources are shared with the gasper workspace, byte for byte.
lean_lib «SpecaExport» where
  srcDir := "../lean"
  roots := #[`SpecaExport.Basic, `SpecaExport.Driver]

@[default_target]
lean_exe «speca-export» where
  root := `Main
