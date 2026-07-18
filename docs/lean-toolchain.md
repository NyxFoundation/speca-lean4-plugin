# Local Lean toolchain vs CI-only validation (H2 evaluation)

Status: evaluation (issue #10, H2). Today all Lean validation is **CI-only**:
the `lean` job in `.github/workflows/ci.yml` installs elan, restores the
mathlib olean cache, builds `lean/` against gasper-lean4, runs
`lake exe speca-export` on the 25 targets, and gates the end-to-end emit.
No developer machine on this project currently has elan/lake installed.

## What CI-only costs us

- **Iteration latency.** Any change under `lean/` (e.g. tuning the
  depend-allowed/must-establish heuristic in `SpecaExport/Basic.lean`) is
  validated only by a push. A warm-cache CI round trip is minutes; a cold
  cache (toolchain bump, lakefile change invalidating the `lake-*` key,
  mathlib cache miss) is tens of minutes. Debugging an elaboration error
  through CI logs multiplies that per attempt.
- **No local `--run-lean`.** The CLI's `--run-lean` path (`cmd_emit_01e` ->
  `lake exe speca-export`) is untestable locally; we rely on
  `--health-json` with the checked-in fixture, which can drift from what the
  exporter really emits until CI regenerates it.
- **Blind edits.** Lean changes are written without a typechecker. The A/B
  workstreams shipped this way, but each exporter change carried CI-roundtrip
  risk.

## What CI-only saves us

- **Setup cost ~0.** No elan install, no multi-GB mathlib artifacts on
  developer machines, no per-OS toolchain issues (this project is developed
  on Windows; elan and the mathlib cache do support Windows, but the Linux CI
  runner is the environment that actually certifies).
- **Single source of truth.** `lean_status: proved` is only ever produced by
  the CI environment that speca's certification references — a local build
  can never be mistaken for the certifying one.
- **The Python driver never needs Lean.** All of Stage C (mapping, anchoring,
  precision, honesty tests) runs on fixtures; that is by design and stays
  true either way.

## Local setup, if/when adopted

Pinned by `lean/lean-toolchain` (currently `leanprover/lean4:v4.31.0`):

```bash
# 1. elan (toolchain manager; installs the pinned toolchain on demand)
curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y
# Windows: winget install elan (or the elan-init.ps1 from the elan releases)

# 2. resolve gasper-lean4 + transitive deps (mathlib) per lake-manifest.json
cd lean && lake update

# 3. fetch prebuilt mathlib oleans (avoids a multi-hour local mathlib build)
lake exe cache get

# 4. build gasper-lean4 + the exporter
lake build

# 5. run the exporter exactly as CI does
lake exe speca-export --targets targets.txt > health.json
```

Expected footprint: roughly 4-6 GB under `lean/.lake` (mathlib oleans
dominate); first setup tens of minutes network-bound, incremental
`lake build` of `SpecaExport` alone seconds-to-minutes. Numbers are estimates
from mathlib-ecosystem experience, not measured here — measuring them is the
first step of adoption.

## Cost/benefit summary

| | CI-only (today) | local elan/lake |
|---|---|---|
| setup | none | one-time install + 4-6 GB + cache fetch |
| Lean edit feedback | one CI round trip per attempt | seconds-to-minutes locally |
| `--run-lean` path | untested locally | testable |
| certification | CI is the single certifier | unchanged (CI still certifies) |
| maintenance | none | toolchain bumps mirrored locally |

## Recommendation

Stay CI-only **while `lean/` is quiescent** — since the A/B workstreams
landed, changes concentrate in the Python driver, data tables, and docs,
none of which need Lean. Adopt a local toolchain when any of these triggers
fires:

1. active work on `SpecaExport/Basic.lean` (e.g. tuning the A2
   depend-allowed/must-establish heuristic with the gasper maintainers);
2. implementing the `@[speca_spec]` consumption (C1/C2,
   `docs/spec-annotation.md`) — attribute plumbing is not writable blind;
3. a growing target set making exporter changes frequent enough that CI
   round trips dominate (rule of thumb: more than ~3 Lean-edit round trips
   in a week);
4. a toolchain/mathlib bump that breaks CI and needs interactive debugging.

Adoption is per-developer and reversible; nothing in the repo layout changes
(the `lean/` workspace already builds locally by design), so this is a
when-not-if decision gated on actual Lean churn.
