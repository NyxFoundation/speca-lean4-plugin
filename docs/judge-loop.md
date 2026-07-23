# Stage-2 quality judge + improve loop (speca#88)

Implements the eval step of the #88 confirmed direction
(https://github.com/NyxFoundation/speca/issues/88#issuecomment-5027471370):
the goal is one 01e checklist at the quality level of a professional audit
checklist — implementation-ready and general. Generation (CHK-15, plugin
PR #21) is reused as-is; this harness evaluates and improves its output.

## eval is not recall

The direction comment's 重要な訂正, load-bearing for this design: eval does
NOT ask whether the checklist reproduces the vuln dataset's specific bugs.
It asks whether the checklist reaches the same QUALITY LEVEL as the
reference corpus. Structurally:

- the judge verdict is a comparison of five-axis score distributions,
  computed by the same blind rubric over both corpora. No content matching
  against the reference or the dataset enters the verdict anywhere
  (`tests/test_judge.py` pins this: judge prompts contain no ids, no corpus
  identity, no provenance fields, no dataset rows).
- `data/ethereum_vulns.csv` is the improve step's teaching material only.
- `recall.py`'s label recall (0.556) remains a side reference number and is
  deliberately absent from the judge verdict.

## The five axes

Fixed rubric in `judge.RUBRIC`, each axis an integer 1-5 with written 1/3/5
anchors (the axis definitions are the #88 comment's, verbatim in intent):

1. `specificity` — a code-level check, not a spec restatement
2. `implementation_readiness` — targets surfaces where implementations
   actually break (arithmetic width, bounds, resources, termination)
3. `generality` — not glued to one client's historical bug
4. `actionability` — an auditor can apply it to code as written
5. `granularity` — one auditable concern, no redundant bundling

A judge response must be strict JSON with every axis present and in range;
anything else errors after one retry — never silently clamped or defaulted.

## Reference bar (calibration)

`data/solodit_checklist.csv` — 52 professional audit checklist items,
vendored byte-identical from speca `benchmarks/knowledge/solodit_checklist.csv`
(provenance, including the git blob sha, pinned in
`data/solodit_checklist.meta.json`; CI and `tests/test_judge.py` recompute
the blob sha from the vendored bytes). The corpus is DeFi-domain on purpose:
it calibrates quality level, not content.

`meets_reference_bar(ours, reference, axis_tolerance=0.25)`:

- our `overall_mean` >= the reference `overall_mean`, AND
- no axis mean falls more than `axis_tolerance` below its reference axis
  mean (one pumped axis cannot buy the verdict).

## The loop

`improve_loop(props, reference, vulns, judge_fn, improve_fn, ...)`:

1. judge every item (round 0 logged)
2. improve candidates: `overall` below the reference overall mean, or any
   axis <= `low_axis` (default 3). Each candidate's improve prompt carries
   (a) the item, (b) the judge critique + scores, (c) up to 3 vuln-dataset
   rows selected by the item's `label` (severity-ranked fallback when the
   label is outside the vendored slice)
3. deterministic guards on each rewrite: only `text`/`assertion` may change
   (identity, `lean_status`, label, severity etc. are immutable by
   construction); the merged property must pass `schema.validate_property`;
   a client/implementation name in the rewrite is rejected (generality
   lint). Rejected rewrites keep the original and are logged
4. re-judge only the changed items; append the round to the score log
5. convergence needs BOTH: the reference bar is met AND the last
   `plateau_rounds` (default 3) rounds are flat within `plateau_delta`
   (default 0.05). Bar-met-but-climbing keeps going; plateaued-below-bar
   keeps going until `max_rounds`, then stops with `converged: false` and
   `stop_reason: max_rounds_reached_without_convergence` — an unconverged or
   below-bar run is reported as such, never dressed up.

Outputs (`improve --out-dir`): `score_log.json` (per-round distributions,
bar verdicts, improvement dispositions, `history_overall_mean`) and
`improved_01e.json` (a PROPOSAL — `theorem_map.json` stays the canonical
checklist source; landing rewrites there is a reviewed, manual step).

## LLM access is injected

`judge.py` is pure logic over two injected callables
(`judge_fn`/`improve_fn`: prompt str -> response str). The repo holds no API
key and imports no LLM SDK. Bindings:

- unit tests: deterministic in-process functions (all convergence and guard
  behavior is tested without any LLM)
- default CI: `tests/fixtures/mock_llm.py` through the real `--llm-cmd`
  subprocess seam — the wiring is exercised end to end, keyless
- real runs: `.github/workflows/judge-dispatch.yml`, dispatch-only on a
  self-hosted runner with an authenticated Claude CLI (`--llm-cmd
  "claude -p"`), the same pattern as speca's 03/04 workflows. Its
  verification step checks artifact well-formedness only — it never asserts
  the bar was met.

## CLI

```bash
speca-lean4 judge --ours <01e.json> [--id-prefix CHK-] --llm-cmd "claude -p" \
    [--reference data/solodit_checklist.csv | --ref-report judge_report.json] \
    [--axis-tolerance 0.25] [--out judge_report.json] [--strict]

speca-lean4 improve --ours <01e.json> [--id-prefix CHK-] --llm-cmd "claude -p" \
    [--improve-cmd ...] [--vulns-csv data/ethereum_vulns.csv] \
    --out-dir improve_run [--max-rounds 6] [--low-axis 3] \
    [--plateau-rounds 3] [--plateau-delta 0.05] [--strict]
```

`--ref-report` reuses the reference scores from a previous judge report
(saves ~52 LLM calls per run); `--strict` makes below-bar (judge) or
non-convergence (improve) a non-zero exit.

## Cross-family judge (speca#143 self-preference check)

The judge and generator are both Claude, so a same-family judge could
self-favour. To check the "same quality level" verdict is not self-preference,
run the judge under a **non-Claude** model and confirm the ranking holds
(generated CHK-* still clears the solodit reference bar).

The harness is model-agnostic — `--llm-cmd` is any `stdin prompt -> stdout
text` command — so the only new piece is an adapter. `tools/llm-hermes.sh`
routes through the Hermes agent, which is configured here for a cross-family
provider (e.g. `custom:ollama-cloud` / kimi), tools disabled:

```bash
# self-preference check: judge CHK-15 vs solodit under a cross-family model
speca-lean4 judge --ours 01e_lean.json --id-prefix CHK- \
    --llm-cmd "bash tools/llm-hermes.sh"
# override model/provider per run (args are forwarded to hermes):
#   --llm-cmd "bash tools/llm-hermes.sh -m kimi-k2.6 --provider custom:ollama-cloud"
```

Because judge scores drift run-to-run (the judge is an LLM), report the bar as
mean ± range over a few runs, not a single number; the **ranking** (CHK above
reference) is the stable signal, the absolute gap is run-dependent.

## Improve prompt: defensive, class-only framing (speca#143)

`build_improve_prompt` feeds the improver the failure **class** only
(`severity`, `label`, `root_cause`), never a concrete incident's exploit
`title` / `attack_path`, and frames the task as a DEFENSIVE detection control.
An earlier version passed `(trigger: <attack_path>): <title>` per evidence row,
which read as offensive tasking and tripped the model's cyber safeguard,
aborting the loop (the honesty guard correctly stopped rather than emitting a
thin green). The class-only framing keeps the dataset as teaching material
while staying clearly defensive. If a model still refuses, point `--improve-cmd`
at a safeguard-exempt cross-family model (same adapter as above).

## Running it as a system

`tools/run-improve.sh [OUT_DIR] [MAX_ROUNDS]` is the reproducible entry point:
emit the CHK 01e, cross-family judge (self-preference check), then the improve
loop, using `data/ethereum_vulns_high.csv` (176 critical/high failure classes
from ethereum-vuln-dataset — the vendored consensus slice has only 3, too thin
to drive concreteness) as teaching material. Env overrides `JUDGE_CMD` /
`IMPROVE_CMD` / `VULNS_CSV`.

The loop writes `improved_01e.json` (a proposal). Persist it with
`tools/apply-improved.py improved_01e.json`, which writes the sharpened
`text`/`assertion` back into `theorem_map.json` (only those two string fields;
theorem_map round-trips exactly at `json.dumps(indent=2)`, so the commit diff is
the before/after record). Log each run in `docs/improve-log.md` with the commit
link so the actual property changes are traceable.

### Granularity backstop

A sharpened item must stay ONE auditable concern at benchmark width. The improve
prompt asks for terse, single-concern output (`TEXT_MAX` / `ASSERTION_MAX`), and
`apply_improvement` rejects any rewrite that bloats past those caps (original
kept) — "concrete" must not become an unbounded multi-check blob, which
`tests/test_mapping.py::test_assertion_granularity_matches_benchmark` also
enforces on the emitted properties.
