# speca-lean4-plugin

External, version-pinned plugin for [SPECA](https://github.com/NyxFoundation/speca).
It implements the `lean` property-generation method behind the provider seam
landed in [speca#87](https://github.com/NyxFoundation/speca/pull/94): it turns the
formally-verified Casper FFG theorems in
[`NyxFoundation/gasper-lean4`](https://github.com/NyxFoundation/gasper-lean4)
into SPECA `01e` security properties.

> Status: **M-lean-provenance workstreams A + B** (issues #3, #4; epic #2), on
> top of the M0-M3 Core-retargeted baseline. Per the gasper-lean4 maintainer,
> ~70-80% of the proved substance lives in `GasperBeaconChain.Core.*`
> (Theories + Lemmas), not the thin, still-growing `Executable` application
> layer, so the target set is Core-centric (18 Core theorems + 7 Executable
> decidable-checker counterparts = 25 theorems). The Lean->plugin boundary now
> carries the real proof content (statement, hypothesis telescope, conclusion,
> referenced constants, gasper-local axioms, proof provenance, verbatim proof
> source), and each theorem lowers to one `01e` property **per must-establish
> precondition** (54 properties from the 25 theorems on the sample fixture;
> the real count comes from CI's live export). CI imports both `Core.All` and
> `Executable.All`, runs the exporter end-to-end, and certifies every target
> `lean_status: proved` (sorry-free, choice-free, native-free) from real
> `collectAxioms` output.

## Why a plugin (not vendored into speca)

Per speca#87/#88 the Lean/`lake` toolchain stays out of core `speca`. `speca`
references this repo as an officially-certified, version-pinned plugin; its
`lean` provider invokes the CLI below across the seam.

## Architecture — two sides, clean boundary

```
gasper-lean4 (proved theorems)
        │
        ▼
lean/  ── lake exe speca-export ──►  theorem-health JSON   (Stage A+B: Lean-only)
        │   collectAxioms per target theorem → lean_status: proved | unknown
        ▼
src/speca_lean4/  ── speca-lean4 emit-01e ──►  01e_PARTIAL JSON   (Stage C: Python)
        │   theorem_map.json (§3 mapping)  +  BUG_BOUNTY_SCOPE.json  +  01b subgraphs
        ▼
speca  (02c → 03 → 04 audit)  ──►  #92 Kurtosis reproduction
```

- **Lean side (`lean/`)** does only the part that needs Lean: resolve each target
  theorem, collect the axioms its proof depends on (the same mechanism as
  gasper-lean4's `#mr_audit_json`), classify it `proved` (no `sorry`) or
  `unknown`, and extract the proof content (statement, hypothesis telescope
  with depend-allowed/must-establish tags, conclusion, referenced constants,
  proof term + verbatim source). Nothing about `01e` lives here.
- **Python driver (`src/speca_lean4/`)** owns the lowering semantics (B1-B5
  below), scope resolution, and `covers` matching. `theorem_map.json` is the
  **tuning overlay** — severity calibration, covers hints, scope, labels,
  shards — **editable without recompiling Lean**; the statement/hypothesis
  content itself comes from the Lean export, not from the map.

## CLI contract (what speca's `lean` provider calls)

```bash
speca-lean4 emit-01e \
    --scope   outputs/BUG_BOUNTY_SCOPE.json \
    --map     theorem_map.json \                # optional; defaults to repo root
    --subgraphs 'outputs/01b_PARTIAL_*.json' \  # optional; for covers resolution
    --gasper-ref <git-sha> \                    # optional; pins gasper-lean4
    ( --health-json health.json | --run-lean )  \
    --out     outputs/01e_PARTIAL_lean.json
```

Proof-health source (Stage B) is one of:
- `--health-json` — a precomputed `lake exe speca-export` output (CI produces it).
- `--run-lean` — run `lake exe speca-export` now (needs the Lean toolchain).
- neither — every property is emitted `lean_status=unknown` (with a warning);
  useful for a dry mapping check without Lean.

Output is exactly the `01e` property schema. Lean-specific data is **additive
only**, never mutating a core field — per speca#88's contract: `lean_status`,
`lean_artifact`, `kurtosis_test`, `label`, `lean_statement`,
`lean_hypotheses`, `lean_must_establish`, `lean_referenced_defs`,
`lean_axioms`, `lean_proof_provenance`, `lean_proof_code`,
`lean_precondition`, `lean_conclusion`, `lean_type_consistency`,
`lean_proof_source`.

## The enriched Lean -> plugin boundary (issue #3, workstream A)

`lake exe speca-export` emits one record per target theorem. Beyond the proof
health flags (`lean_status`, `sorry_free`, `choice_free`, `native_free`), each
record carries:

| field | source | item |
|---|---|---|
| `statement` | `Meta.ppExpr` of `ConstantInfo.type` | A1 |
| `hypotheses` | `Meta.forallTelescope`; per binder: `name`, `type` (pp), `head` (head constant), `class` | A2 |
| `conclusion` | pp of the telescope body — the Q the theorem guarantees | A2/B2 |
| `referenced_constants` | `Expr.getUsedConstants` on the type, filtered to `GasperBeaconChain.*` | A3 |
| `gasper_axioms` | `collectAxioms` minus Lean builtins (`sorryAx`, `Classical.choice`, `propext`, `Quot.sound`, `trustCompiler`, native compute) | A4 |
| `proof_provenance` | `"automated"` if the proof term references decision-procedure markers (`Decidable.decide`, `ofReduceBool/Nat`, `of_decide_eq_true`, `Aesop.*`, `Omega.*`), else `"hand-written"`; `"unknown"` if no value | A5 |
| `proof_code` | pp of `ConstantInfo.value?` (`pp.proofs true`) | A7 fallback |
| `proof_constants` | gasper-local `getUsedConstants` of the proof term — the proof-DAG edges | B3 feed |
| `proof_source` | **verbatim declaration source** (term/tactic code + comments), sliced from the lake package checkout via `findDeclarationRanges?`; `""` if unavailable | A7 |

### The depend-allowed vs must-establish heuristic (A2)

Documented in `lean/SpecaExport/Basic.lean`; provisional and expected to be
tuned with the gasper maintainers:

1. instance-implicit binders -> **depend-allowed** (typeclass plumbing);
2. non-`Prop` binders -> **depend-allowed** (model parameters: `τ`, `stake`,
   `vset`, `parent`, `genesis`, `st`, ...);
3. `Prop` hypotheses whose head predicate is a fixed world/model assumption
   (`two_thirds_good`, `good_votes`, `blocks_exist_*`, `target_height_bound`)
   -> **depend-allowed**;
4. every other `Prop` hypothesis -> **must-establish**: a computed/structural
   fact (`k_finalized ...`, `justified ...`, `quorum_2 ...`, height
   inequalities, ...) the implementation must preserve for the theorem's
   guarantee to transfer.

## Lowering semantics (issue #4, workstream B)

- **B1 — decomposition.** A theorem lowers to N properties, one per
  must-establish hypothesis (`<base-id>-me<i>`), NOT one per theorem.
  Depend-allowed hypotheses are context, never invariants. Theorems with no
  must-establish hypothesis (the Iff-shaped decidable checkers) lower 1:1.
  Per the MTG principle the must-establish set grows with implementation
  sophistication — 54 properties from 25 theorems on the sample fixture.
- **B2 — neutral audit result.** Each assertion reads: `implementation must
  preserve [P]; if so, <theorem> guarantees [Q]` with P and Q pretty-printed
  from Lean — an investigation result, not a good/bad verdict.
- **B3 — proof-DAG severity.** Top-level conclusions keep the theorem_map
  severity; a lemma inherits the maximum severity of the target theorems whose
  proofs (transitively) depend on it, via `proof_constants`. Upward-only —
  nothing is downgraded, and map severities were not relabeled.
- **B5 — type-consistency gate.** Each lowered precondition's head constant
  must be among the theorem's referenced constants; verdict `ok`/`mismatch`/
  `unchecked` in `lean_type_consistency`. Mismatches are warned at emit time
  and fail the CI end-to-end step.

Honesty invariants are unchanged: `sorry` -> `unknown`, unresolved target ->
`unknown` + CI failure, severities never tuned against the benchmark
distribution.

## Precision harness (M2, impl plan section 4)

```bash
# restore the granularity reference (426-file benchmark release)
gh release download bench-rq2a-20260508-speca --repo NyxFoundation/speca
tar --zstd -xf bench-rq2a-20260508-speca.tar.zst   # -> speca/01e_*.json (16 files)

speca-lean4 emit-01e --scope scope.json --health-json health.json \
    --out outputs/01e_PARTIAL_lean.json \
    --out-dir outputs/01e_lean/            # sharded: 01e_PARTIAL_<shard>.json

speca-lean4 verify-precision \
    --ours     outputs/01e_PARTIAL_lean.json \
    --ours-dir outputs/01e_lean/ \          # per-shard props/file granularity
    --benchmark-dir speca \
    --out precision_report.json
```

Measures granularity vs the benchmark corpus (props/file and assertion-length
z-scores, severity KL divergence, vocabulary conformance) and recall vs the
consensus-domain findings in `critical_high_findings.md`. The recall reference
is the curated, reviewable judgment table [`data/findings_map.json`](data/findings_map.json)
— every consensus-layer finding is listed with an explicit in/out-of-domain
flag and a full/partial/none coverage judgment, so the denominator is
transparent.

Post-decomposition (fixture-calibrated): the six protocol-area shards carry
9 / 10 / 8 / 10 / 8 / 9 properties (safety-accountable, safety-cases,
safety-bound-witness, finality-justification, finality-quorum,
finality-liveness) — all within the benchmark 1-sigma props/file band
(11.62 +/- 3.72). Real CI counts come from the live export (the `lean` job
uploads `health.json` + the emitted `01e` as an artifact); shards are
re-tunable in `theorem_map.json` without touching Lean or Python. The
historical M0-M3 table below predates the B1 decomposition (25 x 1:1
properties):

| metric | Core sharded (M3) | Core single-file | prior (7 props) | benchmark |
|---|---|---|---|---|
| schema validity | 100% | 100% | 100% | — |
| vocabulary conformance | 100% | 100% | 100% | — |
| properties per file | **12.5 ± 0.71** (safety 12 z=+0.10, finality 13 z=+0.37; both in 1-sigma) | 25 (z = +3.6) | 7 (z = −1.24) | 11.62 ± 3.72 |
| assertion length | mean z = −0.2 | mean z = −0.2 | mean z = −0.49 | 93.55 ± 14.62 chars |
| severity KL(ours‖bench) | 0.6004 nats | 0.6004 nats | 0.3015 nats | CRITICAL/HIGH/MEDIUM = 95/81/10 |
| recall (strict / lenient) | **0.333** / 0.667 | 0.333 / 0.667 | 0.0 / 0.667 | 3 in-domain of 14 consensus-layer findings |

Honest reading. The Core retarget captures the substantive Core theorems and
**raised strict recall 0.0 → 0.333**: the Core `SlashableBound` trio pins exact
validator-set weight arithmetic, giving full coverage of the Electra
effective-balance finding (`GHSA-wm9c-xvqq-5c28`) that the Executable-only set
could only cover partially. M3 then fixed granularity by **structure, not
relabeling** — `emit-01e --out-dir` shards the 25 properties into two coherent
protocol-area files (`safety` 12, `finality` 13), each landing within the
benchmark's 1-sigma props/file band (single-file emit is kept for speca's
provider call). The severity KL is deliberately unchanged: the
justification/quorum lemmas are honestly `MEDIUM` and were not relabeled to game
the metric — a formal-methods-derived set simply has a different, flatter
severity profile than the CRITICAL/HIGH-heavy benchmark, which we report rather
than fake. Most consensus-layer findings (OOM/DoS, LMD-GHOST, BLS internals,
eth1 ops) remain out of the FFG formal remit by construction.

## Lean exporter directly

```bash
cd lean
lake exe speca-export --targets targets.txt   # newline-delimited theorem names
# → proof-health JSON on stdout
```

## Develop

```bash
# Python driver + mapping (no Lean needed)
pip install -e '.[dev]'
pytest -q

# Lean exporter (needs elan/lake; toolchain pinned in lean/lean-toolchain)
cd lean && lake build
```

## What is proved (from gasper-lean4)

The substantive results — the primary targets — are the **Core** theorems
(`GasperBeaconChain.Core.*`, in Theories/ and Lemmas/). Note the whole Core
layer shares the flat `GasperBeaconChain.Core` namespace; `Theories/` and
`Lemmas/` are file paths, not namespace segments.

| Core theorem | 01e property | role |
|---|---|---|
| `k_safety'` | conflicting k-finalized blocks ⇒ slashable ⅔ intersection | headline k-accountable safety |
| `finalization_fork_means_same_finalization_fork_one` | 1-fork = same-height k-fork at k=1 | fork-condition bridge |
| `no_k_finalized_justified_same_height` | no justified block at a finalized height (no slashing) | height uniqueness |
| `k_slash_surround_case_general` | surround of a finalized block ⇒ slashable | AS surround case |
| `k_non_equal_height_case` | unequal-height conflicting finalization ⇒ slashable | AS unequal-height case |
| `slashable_bound` | slashable intersection meets churn-adjusted weight bound | quantitative AS |
| `quorum_intersection_weight_lower` | ⅔-quorum overlap ≥ combined weight − ⅓ thresholds | inclusion-exclusion |
| `validator_intersection_lower_bound` | validator-set overlap ≥ churn-adjusted expression | weight arithmetic |
| `no_two_justified_same_height` | no two distinct justified blocks at one height (no slashing) | same-height safety |
| `two_justified_same_height_slashed` | same-height justification ⇒ slashable | same-height witness |
| `finalized_means_justified_child` | finalized ⇒ justified child at next height | justification bookkeeping |
| `k_finalized_means_justified` | k-finalized ⇒ justified | justification bookkeeping |
| `finalized_means_one_finalized` | finalized ⇔ 1-finalized | definition bridge |
| `quorum_2_upclosed` | superset of a ⅔-quorum is a ⅔-quorum | quorum monotonicity |
| `quorum_2_nonempty_of_threshold_pos` | positive threshold ⇒ non-empty quorum | quorum non-emptiness |
| `plausible_liveness_construct_extension` | honest ⅔ can always extend + finalize without new slashing | plausible liveness (out of bounty scope) |
| `plausible_liveness_from_coq_blocks_exist` | same, under the Coq block-existence hypothesis | plausible liveness (out of scope) |
| `no_new_slashed_two_link_extension` | the two-link extension introduces no new slashing | liveness support (out of scope) |

The **Executable** layer (`GasperBeaconChain.Executable.*`) is thin and still
growing; its theorems are the **decidable/computable Bool checkers** for the
Core results, and are mapped as such (S1/S2 slashing checkers,
accountable-safety witnesses, the decidable quorum/justification/liveness
predicates).

The full theorem → implementation-invariant lowering (and the STRIDE class per
property) lives in [`theorem_map.json`](theorem_map.json).

## Related

- Seam: [speca#87](https://github.com/NyxFoundation/speca/issues/87) (PR #94, merged)
- This work: [speca#88](https://github.com/NyxFoundation/speca/issues/88)
- Downstream repro: [speca#92](https://github.com/NyxFoundation/speca/issues/92) →
  [`kurtosis-harness`](https://github.com/NyxFoundation/kurtosis-harness)
