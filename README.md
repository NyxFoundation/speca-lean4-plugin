# speca-lean4-plugin

External, version-pinned plugin for [SPECA](https://github.com/NyxFoundation/speca).
It implements the `lean` property-generation method behind the provider seam
landed in [speca#87](https://github.com/NyxFoundation/speca/pull/94): it turns the
formally-verified Casper FFG theorems in
[`NyxFoundation/gasper-lean4`](https://github.com/NyxFoundation/gasper-lean4)
into SPECA `01e` security properties.

> Status: **M2 baseline** (see the impl plan). CI builds gasper-lean4 and runs
> the exporter end-to-end: all mapped theorems resolve and certify
> `lean_status: proved` (sorry-free, choice-free, native-free) from real
> `collectAxioms` output. The precision harness (`verify-precision`) measures
> granularity against `bench-rq2a-20260508-speca` and recall against
> `ethereum-vuln-dataset`; closing the gaps it reports is M3.

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
  theorem and collect the axioms its proof depends on (the same mechanism as
  gasper-lean4's `#mr_audit_json`), classifying it `proved` (no `sorry`) or
  `unknown`. Emits a small health JSON. Nothing about `01e` lives here.
- **Python driver (`src/speca_lean4/`)** owns the theorem → `01e` mapping, scope
  resolution, and `covers` matching. This is where granularity is tuned to the
  fusaka benchmark — **editable without recompiling Lean** (`theorem_map.json`).

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
only** (`lean_status`, `lean_artifact`, `kurtosis_test`), never mutating a core
field — per speca#88's contract.

## Precision harness (M2, impl plan section 4)

```bash
# restore the granularity reference (426-file benchmark release)
gh release download bench-rq2a-20260508-speca --repo NyxFoundation/speca
tar --zstd -xf bench-rq2a-20260508-speca.tar.zst   # -> speca/01e_*.json (16 files)

speca-lean4 verify-precision \
    --ours outputs/01e_PARTIAL_lean.json \
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

Baseline (2026-07-07, 7 properties):

| metric | value | benchmark |
|---|---|---|
| schema validity | 100% | — |
| vocabulary conformance | 100% | type/severity/classification/exploitability/entry_points vocab |
| properties per file | 7 (z = -1.24) | 11.62 +/- 3.72 |
| assertion length | mean z = -0.49; 100% within 1-sigma | 93.55 +/- 14.62 chars |
| severity KL(ours‖bench) | 0.3015 nats | CRITICAL/HIGH/MEDIUM = 95/81/10 |
| recall (strict / lenient) | 0.0 / 0.667 | 3 in-domain of 14 consensus-layer findings |

Honest reading: gasper-lean4 proves protocol-level FFG safety, while the
findings corpus is implementation-level bugs — most consensus-layer findings
(OOM/DoS, LMD-GHOST fork choice, BLS internals, eth1 ops) are out of the FFG
formal remit, and of the 3 in-domain findings the current invariants cover 2
only partially. Raising strict recall means lowering theorems further toward
implementation invariants (M3), not relabeling.

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

| theorem | 01e property | Casper condition |
|---|---|---|
| `slashed_double_vote_iff_bex` | equivocation must be slashable | S1 |
| `slashed_surround_vote_iff_bex` | surround voting must be slashable | S2 |
| `accountable_safety_witnessB` | conflicting finalization ⇒ slashable ⅔ intersection | accountable safety |
| `k_accountable_safety_witnessB` | k-finalized accountable safety under validator churn | k-accountable safety |
| `q_intersection_slashed_iff_exists_witness` | slashable intersection has positive weight | quorum bound |
| `justified_iff_bounded` | justification = bounded supermajority-link chain | justification |
| `two_thirds_good_iff_forall_exists_goodQuorum` | honest ⅔ can always extend | plausible liveness (out of bounty scope) |

The full theorem → implementation-invariant lowering lives in
[`theorem_map.json`](theorem_map.json).

## Related

- Seam: [speca#87](https://github.com/NyxFoundation/speca/issues/87) (PR #94, merged)
- This work: [speca#88](https://github.com/NyxFoundation/speca/issues/88)
- Downstream repro: [speca#92](https://github.com/NyxFoundation/speca/issues/92) →
  [`kurtosis-harness`](https://github.com/NyxFoundation/kurtosis-harness)
