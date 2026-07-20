# speca-lean4-plugin

External, version-pinned plugin for [SPECA](https://github.com/NyxFoundation/speca).
It implements the `lean` property-generation method behind the provider seam
landed in [speca#87](https://github.com/NyxFoundation/speca/pull/94): it turns the
formally-verified Casper FFG theorems in
[`NyxFoundation/gasper-lean4`](https://github.com/NyxFoundation/gasper-lean4)
into SPECA `01e` security properties.

> Status: **M-lean-provenance workstreams A + B + D** (issues #3, #4, #6; epic #2), on
> top of the M0-M3 Core-retargeted baseline. Per the gasper-lean4 maintainer,
> ~70-80% of the proved substance lives in `GasperBeaconChain.Core.*`
> (Theories + Lemmas), not the thin, still-growing `Executable` application
> layer, so the target set is Core-centric (18 Core theorems + 7 Executable
> decidable-checker counterparts = 25 theorems). The Lean->plugin boundary now
> carries the real proof content (statement, hypothesis telescope, conclusion,
> referenced constants, gasper-local axioms, proof provenance, verbatim proof
> source), and each theorem lowers to one `01e` property **per must-establish
> precondition**. First live CI export (2026-07-18): 53 must-establish
> hypotheses across the 25 theorems -> **61 properties**, verbatim proof
> source extracted for all 25, zero gasper-local axioms, zero
> type-consistency mismatches. CI imports both `Core.All` and
> `Executable.All`, runs the exporter end-to-end, and certifies every target
> `lean_status: proved` (sorry-free, choice-free, native-free) from real
> `collectAxioms` output.
>
> **Stage ② checklist overlay** (speca#88 stage 2): on top of the mechanical
> lowering, `theorem_map.json` carries 15 `CHK-*` entries — LLM-synthesized
> implementation invariants (first draft, under review) that descend from the
> same proved theorems but target the arithmetic / type-width / bounds /
> termination / resource failure surface documented by real client bugs in
> [`ethereum-vuln-dataset`](https://github.com/NyxFoundation/ethereum-vuln-dataset)
> (cited per entry). They lower `verbatim` (never decomposed per
> must-establish hypothesis) into their own `checklist-high-angle` shard.
> Design: [`docs/high-angle-checklist.md`](docs/high-angle-checklist.md).

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
`lean_referenced_defs_expanded`, `lean_axioms`, `lean_proof_provenance`,
`lean_proof_code`, `lean_precondition`, `lean_conclusion`,
`lean_type_consistency`, `lean_proof_source`, `lean_doc_string`,
`spec_reference`.

The end-to-end execution flow and every artifact location are consolidated in
[`docs/pipeline.md`](docs/pipeline.md).

`label` follows the ethereum-vuln-dataset controlled vocabulary
(consensus-specs section names, `docs/label_design.md`), and `spec_reference`
+ the `covers` fallback derive mechanically from it (C5): each label maps to
its consensus-specs doc anchor and primary pyspec `process_*` symbol — no
prose judgment.

Spec/code anchoring (issue #5, workstream C) is table-driven:
[`data/anchor_map.json`](data/anchor_map.json) is the def -> spec-symbol ->
client-code-symbol alignment table (C3) that `spec_reference`/`covers` are
derived from (C4, via `src/speca_lean4/anchors.py`). The client-code column is
best-effort and honest: rows are `verified-<date>` (confirmed by code search)
or explicitly `todo`, never fabricated. Declaration-site annotations
(`@[speca_spec]`, C1/C2) are blocked on gasper-lean4 maintainer coordination
(issue #9 G2); the proposed convention is documented in
[`docs/spec-annotation.md`](docs/spec-annotation.md). Hygiene (issue #10): the
honesty invariants are pinned by explicit tests (`tests/test_honesty.py`, H1),
and the local-Lean-toolchain question is evaluated in
[`docs/lean-toolchain.md`](docs/lean-toolchain.md) (H2 — staying CI-only until
`lean/` churn justifies local elan/lake).

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
| `proof_source` | **verbatim declaration source** (term/tactic code + comments), sliced from the lake package checkout via `findDeclarationRanges?`; since A7+ the slice is widened upward over the **contiguous leading comment block** (docstring + adjacent `--` comments), so the proof and its documentation travel as one pair; `""` if unavailable | A7 / A7+ (#17) |
| `referenced_defs_expanded` | recursively pretty-printed **definitions** of the gasper-local constants the statement references — structure fields (projection signatures), inductive constructors, def signature+body — as `[{name, kind, pp}]`. Honestly bounded, with the caps stated in code (`lean/SpecaExport/Basic.lean`): breadth-first to **depth 2**, at most **24 definitions** per theorem, 4000-char pp cap with an explicit truncation marker, deduped; mathlib/Lean-core constants and compiler-generated auxiliaries are never expanded | A3+ (#16) |
| `doc_string` | the declaration's docstring via `findDocString?`; `""` when the theorem has none — empty, never fabricated | A7+ (#17) |

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

## Kurtosis bridge (issue #7, workstream E)

The Executable layer is the reproduction bridge to speca#92
([`kurtosis-harness`](https://github.com/NyxFoundation/kurtosis-harness)): its
decidable Bool checkers (`slashedB`, `justifiedB`, `notSlashedB`,
`goodQuorumAtB`, `qIntersectionWitnessB`) and constructive witnesses
(`accountable_safety_witnessB`, `k_accountable_safety_witnessB`,
`plausible_liveness_construct_extension`) turn an existence-shaped Core proof
into something a devnet can evaluate.

```bash
speca-lean4 emit-kurtosis \
    --scope tests/fixtures/bug_bounty_scope.sample.json \
    --health-json lean/health.json \
    --fixtures-dir outputs/kurtosis \        # <label>/<property_id>/{devnet,assertion}.scaffold.json
    --out outputs/01e_kurtosis.json          # 01e with checker/witness/kurtosis_test populated
```

- **E1** [`data/checker_map.json`](data/checker_map.json) links each theorem to
  its Executable checker(s), the proved `..._iff` correctness theorems, and its
  witness (when one exists); the emitted property surfaces `checker` / `witness`.
- **E3** one `kurtosis_test` fixture **SCAFFOLD** per checker-linked property
  (devnet placeholder + assertion stub referencing the checker). Fixtures are
  clearly scaffolds (`"scaffold": true`, verdict null) — **not** runnable.
- **E6** [`data/evidence_seeds.json`](data/evidence_seeds.json) attaches
  label-matched ethereum-vuln-dataset findings (`pre_fix_code` / `files_changed`
  excerpts) as implementation-linked evidence seeding the reproduction target.
- **E2 / E5** (devnet bring-up + `KurtosisVerificationBackend` handoff) are
  **blocked on speca#92** and designed — not built — in
  [`docs/kurtosis-bridge.md`](docs/kurtosis-bridge.md).

Honesty: `kurtosis_test` / `checker` / `witness` are non-null **only** where a
real Executable checker exists; the pure-arithmetic bound and definitional Core
theorems are honestly `null`.

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
z-scores, severity KL divergence, vocabulary conformance) and **label-grounded
recall** vs the dataset's structured `label` vocabulary (workstream D, issue
#6). The prose judgment table `data/findings_map.json` is **deprecated** (its
strict/lenient numbers are still reported as `recall_prose_deprecated` for
continuity); recall is now computed from three reviewable data files:

- [`data/ethereum_vulns.csv`](data/ethereum_vulns.csv) — vendored
  consensus-domain slice of `ethereum-vuln-dataset` (revision pinned in
  [`data/ethereum_vulns.meta.json`](data/ethereum_vulns.meta.json)): all 37
  rows whose `label` is one of the three consensus-specs areas the FFG target
  set maps to. Vendored unfiltered beyond the label so the denominator
  derivation stays reproducible.
- [`data/label_match_rules.json`](data/label_match_rules.json) — (a) the
  STRUCTURAL in-domain filter (D1, `v1-narrow`, grown gradually): label +
  root_cause + attack_path + severity, no per-finding prose. Current
  denominator: **9 in-domain findings** of the 37 slice rows. (b) coverage
  rules per `(label, root_cause)` cell, each naming the base property ids
  that catch the class and a rationale; unlisted cells count uncovered.
- [`data/recall_gaps.json`](data/recall_gaps.json) — the D2 gap loop: every
  uncovered in-domain finding triaged `new_target` (which
  precondition/theorem WOULD catch it — a concrete growth target) or
  `out_of_model` (honestly outside the FFG remit).

```bash
# label recall alone needs no benchmark corpus — CI runs it against the real
# emitted 01e right after emit-01e:
speca-lean4 verify-recall --ours outputs/01e_PARTIAL_lean.json --strict
```

Honesty guards, all evaluated against the REAL emitted 01e: a rule's
`covered_by` id must actually be emitted (base id or a B1 `-me<i>`
refinement) with the same label, else the finding counts uncovered;
`--strict` fails CI on untriaged uncovered findings, stale gap entries, or
rules naming non-emitted properties. Current numbers (domain `v1-narrow`):
label recall **0.556** (5 of 9 covered; gaps: 2 `new_target` — the
exact-arithmetic / bounded-representation preconditions the slashing-overflow
class needs — and 2 honestly `out_of_model`: slashing-protection DB and REST
API surfaces). The deprecated prose table's strict recall was 0.333 on a
denominator of 3; the numbers are not directly comparable — the label-grounded
denominator is structural, larger, and grows deliberately.

Post-decomposition, from the live CI export (2026-07-18, 61 properties): the
six protocol-area shards carry 9 / 10 / 13 / 10 / 8 / 11 properties
(safety-accountable, safety-cases, safety-bound-witness,
finality-justification, finality-quorum, finality-liveness) — all within the
benchmark 1-sigma props/file band (11.62 +/- 3.72). The `lean` job uploads
`health.json` + the emitted `01e` as a CI artifact; shards are re-tunable in
`theorem_map.json` without touching Lean or Python. Real severity
distribution after B3 DAG derivation: CRITICAL 12 / HIGH 30 / MEDIUM 19.
Known cosmetic limitation: conclusions/hypotheses pretty-print with default
exporter options, so some arithmetic renders applied-instance style
(`instLENat.le ...`) rather than infix notation; faithful, just verbose. The
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
