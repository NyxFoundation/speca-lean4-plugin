# Gasper causal projection

`emit-projected-01e` is the production path for deriving implementation audit
obligations from Gasper theorems. It complements the legacy `emit-01e` output:

- `emit-01e` exposes theorem statements and `must-establish` decomposition.
- `emit-projected-01e` emits reviewed, implementation-facing CL or EL
  obligations with an explicit causal chain.

## Why a separate projection exists

The theorem exporter classifies logical hypotheses as `must-establish` or
`depend-allowed`. That distinction is useful inside the Gasper model, but
cross-layer obligations often live in model inputs such as `HashParent`,
`stake`, validator membership, or the eligible block DAG. Treating every
`depend-allowed` input as irrelevant to implementation auditing loses the
CL-to-EL contract.

The reviewed `data/projection_map.json` therefore adds an ownership dimension:

```text
Lean theorem
  -> owned model input or precondition
  -> CL-local or CL/EL boundary obligation
  -> implementation surface
  -> matching historical failure evidence
```

Dataset evidence is matched only after this chain selects an obligation.
Prevalence never decides whether a theorem applies.

## Usage

```bash
speca-lean4 emit-projected-01e \
  --scope BUG_BOUNTY_SCOPE.json \
  --health-json theorem_health.json \
  --target-layer both \
  --vulns-csv data/ethereum_vulns_high.csv \
  --out outputs/01e_PARTIAL_gasper_projected.json
```

Use the full pinned `ethereum-vuln-dataset` CSV when available. The matcher
retains `source_platform`, fix/introduced commits, source URL, and changed
files; the compact vendored high-severity slice supplies only class-level
evidence.

## Honesty and completeness gates

- CL implementation properties descending directly from proved theorems use
  `descends-from-proved`.
- EL properties remain
  `descends-from-proved-via-unproved-bridge` until a Lean refinement theorem
  establishes the Engine API/Gasper bridge.
- Every target theorem must be applicable to at least one obligation or have a
  reviewed `not_applicable` reason.
- An unclassified theorem or stale exclusion makes the CLI exit non-zero.
- Each emitted property carries `source_theorems`, `owned_inputs`,
  `causal_chain`, `spec_references`, `implementation_surfaces`,
  `dataset_query`, and `dataset_evidence`.

`tools/generate-properties.py` now uses the same projection map by default.
Its LLM can rewrite the reviewed obligation into concise `text` and
`assertion`, but cannot select theorem applicability. The former
label-prevalence algorithm is available only through
`--legacy-label-pairing`.

## Next proof step

Add a plugin-side Lean module that defines an `EngineContract`,
`EngineTrace.refinesGasperDAG`, and composition theorems such as
`k_safety_under_engine_contract`. Once those resolve without `sorry`, change
the corresponding projection-map `bridge_status` from `specified-unproved` to
`proved`; no Python-side status override is allowed.
