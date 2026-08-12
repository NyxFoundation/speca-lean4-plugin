# EthTotal track — eth-total-supply-safety → `01e`

The plugin's second formalization target, alongside gasper-lean4. Where the
gasper track lowers **consensus-layer** accountable-safety theorems, this one
lowers the **execution-layer supply and accounting** theorems of
[`NyxFoundation/eth-total-supply-safety`](https://github.com/NyxFoundation/eth-total-supply-safety)
(the `EthTotal` Lean 4 development), wired to the submodule at
`external/eth-total-supply-safety`.

Nothing about the gasper track changed: `theorem_map.json`, `lean/Main.lean`'s
target set and the emitted gasper `01e` are untouched. What was generalized is
the exporter — see [Shared exporter](#shared-exporter-what-was-generalized).

## What the formalization proves

`EthTotal` models a ledger as a finitely-supported balance function over a
distinct live-account list, with `supply = Σ bal over live`, and an event trace
carrying `minted`/`burned` totals plus the *sites* they are confined to
(`SiteConfined M B τ`). Everything is term-mode and constructive; the
repository's own audit module reports the whole development axiom-free.

The results that matter for an implementation audit fall into five families:

| family | representative theorems | what it pins down |
|---|---|---|
| supply reconciliation | `exact_supply`, `exact_supply_on`, `supply_diff_eq` | total supply reconciles exactly with the per-account deltas, independent of which covering account list is enumerated |
| mint/burn attribution | `mint_witness_of_bal_lt_on`, `burn_witness_of_bal_lt_on`, `burn_only_at`, `supply_eq_of_confined_empty` | every supply change has an explicit, *sited* mint or burn witness — no unattributed issuance |
| transaction & fee path | `process_transaction_effect`, `admission_iff_guards`, `refund_tip_burn_partition_the_prepayment`, `escrow_never_underflows` | the EIP-1559-shaped prepay → execute → refund/tip/burn settlement conserves value, and which guards are individually necessary |
| account lifecycle | `process_transaction_destroy_phase`, `no_credit_after_destroy`, `no_write_after_erase`, `a_self_destruct_burns_exactly_the_balance` | destruction burns exactly the balance; a destroyed account cannot be credited or written again |
| representation limits | `overflow_requires_mint`, `flash_loan_impossible`, `reported_burn_is_saturated`, `chain_bal_lt_of_cap` | balance bounds follow from cumulative issuance, and a saturating (monus) debit inflates supply / understates a burn |

The `Extentions/` layer (65 modules) is a library of **negative results** —
`naive_self_transfer_mints`, `xfer_overdraft_inflates`,
`stale_read_self_duplicates`, `a_zero_write_does_not_enlarge_the_support`,
`writing_the_default_is_deletion` — each one a proved statement that a
plausible implementation shortcut is wrong. Those map onto real client defect
classes more directly than the positive theorems do, which is why the curated
set draws heavily on them.

## Pipeline

```
external/eth-total-supply-safety/   (submodule; the commit IS the audited revision)
        │
        ├─[1] tools/ethtotal-inventory.py ──► data/ethtotal_inventory.json
        │        every declaration: 3886 (3333 theorems, 499 defs, 47 structures, …)
        │
        ├─[2] lean-ethtotal/  lake exe speca-export ──► lean-ethtotal/health.json
        │        ALL 3333 theorems, collectAxioms each
        │
        ├─[3] tools/ethtotal-triage.py ──► data/ethtotal_triage.json
        │        every theorem bucketed selected / represented / screened-out
        │
        ├─[4] data/ethtotal_curation.json          (REVIEWED — the human decision)
        │        themes, per-file theme assignment, 55 curated theorems with
        │        audit title, assertion, severity, dataset label
        │
        ├─[5] tools/ethtotal-build-map.py ──► theorem_map_ethtotal.json
        │        base entries (curated + derived) + the CHK-* checklist overlay
        │
        ├─[6] tools/generate-properties.py --cover-all
        │        every CRITICAL/HIGH base entry × its dataset defect class
        │        ──► data/ethtotal_generated_properties.json (CHK-* proposals)
        │
        ├─[7] tools/run-improve-ethtotal.sh
        │        judge (cross-family) → sharpen → re-judge, teaching material =
        │        data/ethtotal_vulns_high.csv ──► improve_run_ethtotal/
        │        persisted with tools/apply-improved.py, then [5] again
        │
        └─[8] tools/emit-track.sh ethtotal ──► outputs/<date>-ethtotal/
                 --concrete-only: the audit source is the CHK-* checklist
```

### [1]–[3] The lemma sweep

`ただ補題もちゃんと洗う` is the reason steps 1–3 exist rather than a hand-picked
target list. A 33k-line formalization has 3333 theorems, and 1690 of them live
in `Lemmata/` — a headline-theorem-only target set would drop exactly the layer
the maintainers say carries the substance.

- **inventory** is a lexical scan (namespace stack tracked) that records every
  declaration with its source range, verbatim signature and docstring. It makes
  no proof claim.
- **the exporter target list is the whole inventory**: all 3333 theorems are
  exported, so proof status is measured, never sampled.
- **triage** scores every theorem for audit relevance (keyword signals over the
  declaration name and statement — the formalization names its results after
  what they mean), ranks them *within each source file*, and buckets every
  single one with a reason:

  | bucket | count | meaning |
  |---|---|---|
  | `selected` | 146 | top-ranked in its file — becomes a `theorem_map` base entry |
  | `represented` | 2068 | a variant (`_on`, `_of_le`, pointwise, …) or same-theme sibling of a selected result |
  | `screened-out` | 1119 | below the audit-relevance floor: algebraic/structural helpers with no implementation surface of their own |

  All 93 theorem-bearing files are represented; none was skipped.

### [4] Curation — the reviewed layer

`data/ethtotal_curation.json` is where judgment lives, and it is deliberately
separate from everything mechanical:

- **themes** (9) fix the dataset `label`, bug-bounty area, shard, entry points
  and exploitability for a family of results.
- **file_themes** assigns each of the 93 source files to a theme.
- **curated** lists 55 theorems with a hand-written audit title, an assertion,
  and a severity calibrated on the EF bug-bounty model (network-scale impact
  reachable remotely).

Base entries that are *not* curated are emitted `MEDIUM` with a title
transcribed from the declaration name and an assertion taken verbatim from the
exported Lean conclusion. Nobody reviewed them for severity, so they do not
claim one.

### [5] Map + [6] checklist generation

`theorem_map_ethtotal.json` is a **build product** — do not hand-edit it; edit
the curation or the generated-properties file and rebuild. It carries 176 base
entries (11 CRITICAL / 34 HIGH / 131 MEDIUM) plus the CHK-* overlay.

Generation is the `--cover-all` mode: every CRITICAL/HIGH base entry with no
concrete CHK twin is concretized against the most dataset-prevalent
critical/high defect class for its label, judged blind by a **cross-family**
model (Hermes/kimi, not the generating model), and kept only above the score
floor of 3.5.

The live run (2026-08-12, gen=`claude -p`, judge=cross-family) went:

| round | candidates | kept | dropped below floor | lost to the length cap |
|---|---|---|---|---|
| 1 | 45 | 34 | 3 | 8 |
| 2 | 11 (the leftovers — `--cover-all` re-targets exactly what has no CHK twin) | 9 | 2 | 0 |

Round 1 losing 8 items *purely* to the 260-character `TEXT_MAX` cap was a real
coverage hole — `refund_tip_burn_partition_the_prepayment`,
`reported_burn_is_saturated` and `trace_net_unique` are among the most
audit-relevant results in the whole development. The retry asked for a rewrite
"<= TEXT_MAX chars", and the model kept landing 3–15 characters over. So the
retry now asks for a budget *below* the cap and tightens it each attempt
(`TEXT_MAX - 40·attempt`, floor 140). All 8 came back on the second run, at
3.6–5.0.

Two theorems still have no concrete checklist item, and that is left standing
rather than papered over: `destroy_chain_supply` (judged 3.4) and
`process_transaction_destroy_phase` (2.6) did not clear the floor. Both are
account-destruction results whose audit surface is substantially covered by
`a_self_destruct_burns_exactly_the_balance`,
`the_burn_comes_from_zeroing_not_from_the_transfer` and `no_credit_after_destroy`,
which did clear it — but the coverage is by neighbourhood, not by construction.

Result: **43 CHK-\* items** over 21 CRITICAL / 67 HIGH / 131 MEDIUM map entries.

### [7] Recursive self-improvement

Same loop as the gasper track (`docs/judge-loop.md`), with a domain-matched
corpus: `data/ethtotal_vulns_high.csv` is the ethereum-vuln-dataset
critical/high population restricted, by label alone, to the value-bearing
execution surfaces (44 rows: state-trie 14, transactions 7, gas 5, evm 5,
opcodes 5, database 4, block-processing 3, precompiles 1). The
severity column is the dataset's bounty-aligned `severity_estimated`, and the
slice criteria are recorded in `data/ethtotal_vulns_high.meta.json` against a
pinned dataset revision.

The corpus is **input to sharpening, never an eval denominator**. The verdict
is the judge's quality distribution against the solodit professional-audit
reference bar, exactly as in stage 2 of speca#88.

First live run (2026-08-12, full detail in [`improve-log.md`](improve-log.md)):

| | value |
|---|---|
| baseline, ours (n=43) | **4.284** |
| solodit reference bar (n=52) | 2.742 |
| `meets_reference_bar` | true, no axis gap — cleared *before* any sharpening |
| progression over 4 rounds | 4.209 → 4.470 → 4.572 → 4.591 |
| items sharpened | 22 of 33 candidates (16 / 5 / 1 per round) |
| convergence | `false` — the final +0.019 is flat, but the plateau rule needs 3 flat rounds and `--max-rounds 3` ended the run first |

The emitted audit source is `outputs/20260812-ethtotal/01e_PARTIAL_ethtotal.json`:
43 properties, 11 CRITICAL / 32 HIGH, every one `descends-from-proved` — the
hand-written checklist text is not itself Lean-verified, only the theorem it
descends from is.

## Shared exporter — what was generalized

`lean/SpecaExport/Basic.lean` was hardcoded to `GasperBeaconChain`: the
project-local constant filter, the imported modules, the model-assumption list
and the `project` field. It now takes a `ProjectConfig`:

```lean
structure ProjectConfig where
  nsPrefix                : Name
  projectName             : String
  modelAssumptionHeads    : List String := []
  modelAssumptionPrefixes : List String := []
```

`gasperConfig` holds exactly the previous values, so the gasper export is
unchanged (the `gasper_axioms` JSON key is kept as an alias of the new
`project_axioms`). `ethTotalConfig` declares **no** model assumptions: EthTotal
has no honest-majority-style world hypotheses, so every `Prop` hypothesis is
must-establish and nothing is excused from the audit.

The IO half moved to `lean/SpecaExport/Driver.lean`, shared by both
workspaces; each `Main.lean` is now a two-line call naming its config and its
runtime import roots. Two other exporter changes came out of running over 3333
theorems at once:

- `maxHeartbeats := 0` for the export run. The default interactive budget is
  calibrated for editing one declaration; a theorem needing more work than that
  is not a failed theorem, and timing out would silently degrade its record.
- per-theorem isolation (`classifyOne`): if enrichment itself throws, that one
  record degrades to `lean_status: unknown` with the reason in `export_error`,
  instead of losing the run — and never to `proved`, because the check did not
  complete.

Two Python hardcodes were generalized the same way: the B5 type-consistency
gate now derives the project namespace from the target theorem's own root
(`GasperBeaconChain.` / `EthTotal.`) instead of a constant, and the map's
`source`/`ref` keys are accepted alongside the legacy `gasper_source`/
`gasper_ref`.

## Two workspaces, one exporter

`lean/` and `lean-ethtotal/` exist separately because the two formalizations
pin different toolchains — `leanprover/lean4:v4.31.0` vs `v4.33.0-rc1` — so
they cannot share an environment. `lean-ethtotal/lakefile.lean` shares the
exporter sources verbatim via `srcDir := "../lean"` (no fork), takes `EthTotal`
as a **path** dependency on the submodule checkout, and pins `mathlib` to the
exact revision the submodule's own manifest pins (the submodule asks for
`master`, which moves; a root requirement wins). Only
`Mathlib.Data.Nat.Notation` is actually imported by the formalization, so the
mathlib surface built here is small.

```bash
# NixOS note: tools/lean-env.sh runs lake through `nix shell nixpkgs#elan`,
# because the ambient ~/.elan install is not usable here.
cd lean-ethtotal
../tools/lean-env.sh lake build
../tools/lean-env.sh lake exe speca-export \
    --targets targets.txt --output health.json \
    --src-root ../external/eth-total-supply-safety
```

`--src-root` is needed here and not in the gasper workspace: `EthTotal` is a
path dependency, so its `.lean` sources are in the submodule checkout rather
than under `.lake/packages/`, and A7 verbatim proof-source slicing has to be
told where to look.

## Current numbers

From the live local export (submodule `a21b9f1`, Lean 4.33.0-rc1):

| metric | value |
|---|---|
| declarations in source | 3886 (3333 theorems) |
| theorems exported | 3333 — **all** of them |
| `lean_status: proved` | 3333 / 3333 |
| non-builtin axioms | 0 (matches the repo's own `AUDIT-ALL: all axiom-free`) |
| verbatim proof source captured | 3333 / 3333 |
| must-establish hypotheses | 2702 across the target set |
| theorem_map base entries | 176 (11 CRITICAL / 34 HIGH / 131 MEDIUM) |
| base `01e` properties emitted | 345 (305 must-establish-decomposed) |
| generated `CHK-*` checklist items | 43 |

## Spec anchoring (execution-specs)

The consensus track anchors each label to a consensus-specs pyspec symbol via
`data/anchor_map.json`. EthTotal is execution-layer, so its counterpart is
[`data/anchor_map_execution.json`](../data/anchor_map_execution.json), built by
`tools/build-el-anchor-map.py` against a pinned
[`ethereum/execution-specs`](https://github.com/ethereum/execution-specs)
checkout (EELS, revision and fork recorded in the table).

Judgment and fact are kept apart. Which surface a label corresponds to is
reviewed judgment and each row states its `why`. Whether the symbol *exists* is
not asserted: the builder locates every definition in the checkout and records
`file`/`line`/`kind`, and a symbol it cannot find is a hard error rather than a
silently dropped row. So an execution-specs bump that renames or moves a symbol
fails the rebuild instead of leaving a dead anchor.

| label | primary surface |
|---|---|
| state-trie | `state_tracker.py#set_account_balance` |
| transactions | `fork.py#process_transaction` |
| gas | `fork.py#process_transaction` (settlement happens inside it) |
| evm | `vm/interpreter.py#process_message` |
| opcodes | `vm/instructions/system.py#selfdestruct` |
| database | `state_tracker.py#incorporate_tx_into_block` (journal/commit) |
| block-processing | `fork.py#apply_body` |
| precompiles | `vm/precompiled_contracts/mapping.py#PRE_COMPILED_CONTRACTS` |
| beacon-chain:withdrawal | `fork.py#process_withdrawals` |

The last row is a deliberate mismatch, recorded in the table rather than
smoothed over: the dataset label is the consensus-side name, but the properties
carrying it are about the *execution-layer* credit of a withdrawal, so that is
what they anchor to.

Per-property rows go finer: a property anchors to the surface its own text
names, recorded as `matched_in_text`, and to the label's primary surface
otherwise. Of the 43 checklist items, **8 name their surface themselves**; the
other 35 take the label default. Symbols that are also ordinary English words
(`balance`, `root`, `state`, …) only count in opcode form (`BALANCE`) — matching
"…proves balance >= burn amount…" to the BALANCE opcode was a real false
positive this rule removed.

`covers` now leads with the anchored symbol, so `covers` and `spec_reference`
name the same surface instead of disagreeing. All 43 checklist properties carry
both.

### What the `01e` itself records

The anchoring has to survive being read on its own — a `#symbol` reference is
not checkable without knowing which revision of which spec it was verified
against. So the emitted document carries the provenance, not just the
references:

```json
"spec_anchor_tables": [{
  "reference_prefix": "execution-specs",
  "spec_source": "ethereum/execution-specs",
  "spec_revision": "6e4808927cb7140f05c43890b48630afcc368d91",
  "spec_fork": "prague",
  "table": "data/anchor_map_execution.json",
  "verification": "every symbol located in the pinned checkout (file/line recorded per row)"
}]
```

Only the tables this document actually used are listed — the header describes
the document, not the repo's data directory. The gasper 01e lists its own row,
and the absence of `spec_revision` there is the honest signal that the consensus
table is dated rather than revision-pinned.

Per property, alongside `covers` and `spec_reference`:

| field | value |
|---|---|
| `spec_reference_basis` | `named-in-text` (8) — the property's own text names the symbol; `label-default` (35) — it inherits its label's primary surface |

The field is absent where no per-property anchor row exists (the consensus table
anchors by label only, and claiming `label-default` there would imply a
per-property decision nobody made).

## Honest gaps

- **Anchors are label-level for 35 of 43 checklist items.** They point at the
  right module and a real symbol, but at the label's primary surface rather than
  the exact function the item is about. `matched_in_text` says which is which,
  per row.
- **Anchors are fork-scoped.** The table is built against one named fork
  (`spec_fork`); a different fork means regenerating, not editing.
- **`covers_hint` in the curation is still unverified.** It feeds `covers` only
  when no anchor applies, and is never client-specific.
- **No recall workstream.** The gasper track has a label-grounded recall
  denominator (`data/label_match_rules.json`, `data/recall_gaps.json`); the
  EthTotal track has none yet, so `verify-recall` is not wired for it. That is
  a deliberate omission, not an oversight — the D1 structural filter has to be
  designed for the execution-layer labels first.
- **CI runs the exporter for gasper only.** The EthTotal export is reproducible
  locally with the commands above; wiring it into CI means paying for the
  mathlib restore in a second job.
