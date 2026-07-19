# Pipeline — end-to-end execution flow and artifact locations

Consolidated reference for what runs, in what order, and where every artifact
lands. Paths are derived from the code (`src/speca_lean4/cli.py`,
`src/speca_lean4/kurtosis.py`, `lean/Main.lean`) and the CI workflow
(`.github/workflows/ci.yml`), not from convention.

## Execution flow

```
theorem_map.json ─────────┐ (target list; tuning overlay)
                          ▼
[1] lake exe speca-export --targets targets.txt          (lean/, Lean toolchain)
        │  one record per theorem: lean_status, statement, hypotheses,
        │  conclusion, referenced_constants, referenced_defs_expanded (#16),
        │  gasper_axioms, proof_provenance, proof_code, proof_constants,
        │  proof_source (docstring-widened, #17), doc_string (#17)
        ▼
    health.json  (stdout redirect; CI writes lean/health.json)
        ▼
[2] speca-lean4 emit-01e --scope ... --health-json health.json
        │  Stage C lowering (B1-B5): one property per must-establish
        │  hypothesis; severity DAG; type-consistency gate; C5 anchors
        ├──►  --out      01e_PARTIAL_lean.json     (single file, speca provider call)
        └──►  --out-dir  01e_lean/01e_PARTIAL_<shard>.json   (per-shard granularity)
        ▼
[3] speca-lean4 emit-kurtosis --scope ... --health-json ... --fixtures-dir ...
        │  E1 checker/witness link + E3 fixture scaffolds + E6 evidence seeds
        ├──►  <fixtures-dir>/<label>/<property_id>/devnet.scaffold.json
        ├──►  <fixtures-dir>/<label>/<property_id>/assertion.scaffold.json
        └──►  --out 01e_kurtosis.json  (01e with checker/witness/kurtosis_test)
        ▼
[4] speca-lean4 verify-recall --ours 01e_PARTIAL_lean.json --strict
        └──►  recall_report.json       (D6 label-grounded recall; CI gate)
[5] speca-lean4 verify-precision --ours ... --ours-dir ... --benchmark-dir ...
        └──►  precision_report.json    (granularity vs bench-rq2a-20260508-speca)
```

Step [1] needs the Lean toolchain and runs in CI only (see
`docs/lean-toolchain.md`); `emit-01e`/`emit-kurtosis` accept `--run-lean` to
invoke it inline (targets written to a tempfile), or `--health-json` for the
precomputed CI artifact. With neither, every property is honestly
`lean_status=unknown`. Steps [2]-[5] are pure Python.

## Artifact locations

Output paths are caller-chosen flags; this table lists the flag, the name CI
uses, and the conventional name the README examples use.

| artifact | produced by | path (CI) | path (convention) |
|---|---|---|---|
| targets list | CI heredoc from `theorem_map.json` (or tempfile via `--run-lean`) | `lean/targets.txt` | `lean/targets.txt` |
| proof-health JSON | `lake exe speca-export --targets ... > health.json` (stdout) | `lean/health.json` | `lean/health.json` |
| 01e single file | `speca-lean4 emit-01e --out` | `01e_lean.json` | `outputs/01e_PARTIAL_lean.json` |
| 01e shards | `speca-lean4 emit-01e --out-dir` (one `01e_PARTIAL_<shard>.json` per `theorem_map` shard) | `01e_lean_shards/01e_PARTIAL_<shard>.json` | `outputs/01e_lean/01e_PARTIAL_<shard>.json` |
| kurtosis devnet scaffold | `speca-lean4 emit-kurtosis --fixtures-dir` | — (not run in CI) | `outputs/kurtosis/<label>/<property_id>/devnet.scaffold.json` |
| kurtosis assertion scaffold | same; its path is recorded in the property's `kurtosis_test` | — | `outputs/kurtosis/<label>/<property_id>/assertion.scaffold.json` |
| 01e with checker/witness | `speca-lean4 emit-kurtosis --out` | — | `outputs/01e_kurtosis.json` |
| recall report | `speca-lean4 verify-recall --out` | `recall_report.json` | `recall_report.json` |
| precision report | `speca-lean4 verify-precision --out` | — | `precision_report.json` |
| CI artifact bundle | `actions/upload-artifact`, name `lean-health-and-01e`, 30-day retention | `lean/health.json` + `01e_lean.json` + `01e_lean_shards/` + `recall_report.json` | — |

`<label>` in fixture paths is the filesystem-safe dataset label
(`kurtosis.safe_label`: `:` replaced by `--`, e.g.
`beacon-chain--slashing`); `<shard>` comes from each theorem_map entry's
`shard` key (`misc` when omitted).

Data inputs (all versioned in-repo):

| input | role |
|---|---|
| `theorem_map.json` | target theorems + tuning overlay (severity, covers hints, labels, shards) |
| `data/anchor_map.json` | C3/C4 def -> spec-symbol -> client-code alignment (feeds `spec_reference`/`covers`) |
| `data/checker_map.json` | E1 theorem -> Executable checker / correctness / witness |
| `data/evidence_seeds.json` | E6 label-matched ethereum-vuln-dataset excerpts for fixtures |
| `data/ethereum_vulns.csv` (+ `.meta.json`) | vendored dataset slice — the recall denominator source, revision pinned |
| `data/label_match_rules.json` | D1 structural domain filter + per-(label, root_cause) coverage rules |
| `data/recall_gaps.json` | D2 gap triage (`new_target` / `out_of_model`) |
| `data/findings_map.json` | DEPRECATED prose recall table, reported as `recall_prose_deprecated` only |
| `tests/fixtures/bug_bounty_scope.sample.json` | sample `BUG_BOUNTY_SCOPE.json` (real one comes from the speca run) |
| `tests/fixtures/theorem_health.sample.json` | sample exporter output for Lean-free tests |

The precision benchmark corpus is not vendored: restore it with
`gh release download bench-rq2a-20260508-speca --repo NyxFoundation/speca` and
extract to a directory passed as `--benchmark-dir`.

## Honesty bounds carried through the pipeline

- `referenced_defs_expanded` (#16) is bounded in `lean/SpecaExport/Basic.lean`
  and the caps are code, not prose: depth 2, 24 definitions per theorem,
  4000-char pp cap with an explicit truncation marker; only
  `GasperBeaconChain.*` is ever expanded.
- `doc_string` (#17) is `""` when the declaration has no docstring, and the
  Python side then drops the `lean_doc_string` key — absence is never papered
  over.
- `lean_status` can only degrade downstream (unresolved -> `unknown`), never
  upgrade; kurtosis fixtures are explicit scaffolds with `verdict: null`.
