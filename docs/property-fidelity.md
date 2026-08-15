# Property fidelity — why the generated checklist drifts from the proofs

Diagnosis and remediation plan for the gap between what the Lean export knows
and what the generated `CHK-*` checklist actually says. Written after the
`20260812-ethtotal` cross-client run (0 confirmed findings; its funnel reports
584 total pairs, 241 structurally-cannot-implement, 40 unlocatable, and 261
entered audit) and re-checked against the `20260723-gasper` run.

**The historical finding in one sentence:** on the legacy EthTotal path, the
property generator never saw a proof — it received the theorem's *last name
component* and nothing else from Lean — and the judge that scored the result
had no separate fidelity gate that would notice. The proof-aware path described
below is now implemented and exercised on the 45 EthTotal candidates.

The local measurements are reproducible; §6 lists the commands. Cross-client
measurements additionally require the pinned audit-repo artifacts named in §5.

The follow-up design for preserving stronger lemma consequences in the
auditor-facing artifact is documented in
[`docs/lean-to-security-property.md`](lean-to-security-property.md). The key
change is a root-centred `audit_packet` backed by the transitive theorem/lemma
closure, rather than a root conclusion plus one selected obligation.

The current EthTotal artifact has 45 such packets over 390 emitted 01e
properties. The packets cover 571 project-local theorem/lemma records in
total; one root has no local theorem/lemma record and is intentionally
represented as root-only. All 45 packets passed the structural and closure
coverage gates. The dataset-indexed few-shot improvement round raised the
logged pre-fidelity judge mean from 3.036 to 3.778; the final repaired packet
scored 3.467 against the 2.169 reference mean.

The full 01e now attaches packets to all 390 properties, including the 345
legacy theorem-backed properties. For those legacy roots, the packet is a
conservative Lean-export transcription (root conclusion plus every local
closure conclusion); it is intentionally not an LLM interpretation. The
parallel full-set wording loop is available in
`tools/run-improve-ethtotal.sh`, while the recorded completed few-shot run
covers the 45 CHK properties.

---

## 1. Where the chain breaks

```
3333 (EthTotal) / 25 (gasper) theorems
        │  lake exe speca-export
        ▼
health.json          statement · conclusion · hypotheses(must-establish)
                     referenced_defs_expanded · proof_source · doc_string
        │
        │  ✓ canonical evidence record reaches generation and improvement
        ▼
theorem_map*.json    labels (from the theorem's FILE) · severity · covers_hint
        │  tools/generate-properties.py  → build_generate_prompt()
        ▼
CHK-*                LLM input = evidence id/hash + root obligations/conclusion
                                 + transitive theorem/lemma closure
                                 + bounded referenced defs/proof source
        │  closure-aware fidelity → audit_packet
        │  speca-lean4 improve ×N → build_improve_prompt()
        ▼                         (text · assertion only; packet is fixed)
CHK-* sharpened
        │  speca-lean4 emit-01e          → mapping.build_property()
        ▼
01e_PARTIAL_*.json   ★ Lean fields + evidence/fidelity provenance are retained
                       in the emitted item
```

### Current implementation (2026-08-14)

`tools/generate-properties.py --health-json lean-ethtotal/health.json` now
builds a canonical evidence payload from the live export, including the fully
qualified theorem, all root `must-establish` obligations, the transitive local
theorem/lemma closure, referenced definitions, proof source, and a SHA-256
hash. The model generates one root-centred `audit_packet` with supporting facts
and derived implementation obligations. The historical label/defect join
remains candidate-selection context only; it is not treated as proof evidence.

`tools/refine-property-fidelity.py` is a separate closure-aware `claude -p`
gate. It sees the same root-plus-closure evidence, rejects unsupported
client-specific additions and weak lemma projections, and can repair both the
packet and its short text/assertion. The quality loop then mutates only the
short text/assertion, so it cannot erase the proof frontier. The final 01e
retains the packet, closure, reviewer verdict, reason, and model command.

During that wording step, `ethereum_vuln*.csv` is used as dataset-indexed
few-shot teaching material. It selects safe defensive style cards by
`label`/`root_cause` (weak wording → concrete wording); raw incident titles,
attack paths, clients, and functions are not passed to the model. The cards
raise specificity without becoming semantic evidence.

On the pre-fix path, Lean enrichment was *decoration on the output*, not
*input to the derivation*. `mapping.py:309-335` attached it after the model
decision; the current path feeds the canonical record upstream as described
above.

---

## 2. Evidence

### 2.1 Historical baseline: the generator never saw the proof

`tools/generate-properties.py:170-202`:

```python
def build_generate_prompt(c: dict) -> str:
    thm = c["theorem"].split(".")[-1]          # ← the ONLY Lean-derived input
    hints = ", ".join(c["covers_hint"][:6]) or "the relevant handlers"
```

What that produces (EthTotal, CHK-GEN-04):

| | |
|---|---|
| theorem `stale_credit_supply_gap` | `N.supply + M.bal s = M.supply + (b+T)` → `N'.supply + M.bal s = M.supply + ((b+R)+T)` → `N.supply + R = N'.supply` (one `add_right_cancel`) |
| generated text | "Verify the batch state-update path re-reads each account's balance from the live journal at the moment of the credit/debit …" |

The item is an expansion of the *name*. The proof is a Nat cancellation lemma
and says nothing about journals or batches. `build_improve_prompt`
(`judge.py:368-407`) has the same blind spot, so four sharpening rounds can
only move the item further from the theorem.

### 2.2 The judge has no fidelity axis

`judge.py:63-69` — `specificity`, `implementation_readiness`, `generality`,
`actionability`, `granularity`. All five score the prose. None asks whether the
item still corresponds to the theorem it claims to descend from. The EthTotal
loop went 4.209 → 4.591 over four rounds; the distance from the proof was never
measured, in either direction.

### 2.3 The exporter's environment degrades the pretty-printer

`Driver.lean:163` builds the environment with `importModules`. In that
environment `Meta.ppExpr` loses every notation unexpander. A/B experiment on
the same declaration, same process:

```
[A elaboration env]     ∀ … (ha : a ∈ L.live) (v : ℕ), v ≠ 0 → (… + v …) ≠ 0
[B importModules env]   ∀ … (ha : List.instMembership.mem L.live a) (v : Nat),
                          Ne v 0 → Ne (… instHAdd.hAdd … ) 0
```

Repeating B with `Options.empty`, with `pp.proofs`, and with an explicit
`pp.notation := true` gives byte-identical output, so **the cause is the
environment, not the options**. Adding ``{module := `Lean}`` to the runtime
import list does not fix it either.

Scale, over the 3333-theorem EthTotal export:

| in `statement` | count |
|---|---:|
| `instHAdd.hAdd` (i.e. `+`) | 828 |
| `instMembership` (i.e. `∈`) | 597 |
| `Ne` (i.e. `≠`) | 445 |
| `Not (` (i.e. `¬`) | 291 |
| **`∈` / `≠` / `¬` / `+` / `::`** | **0** |
| hypothesis binders named `inst._@.…._hyg.N` | 566 |

Two things this is *not*: it is not unsoundness (3333/3333 `proved`, no
`sorryAx`, no `export_error`), and it does not affect `proof_source`, which is
a verbatim source slice and is correct in all 3333 records. It does affect
`statement`, `conclusion`, `hypotheses`, `must_establish` and
`referenced_defs_expanded` — i.e. every field a future generator would want to
read.

### 2.4 The length caps bind on the property, not on the export

Export-side truncation is negligible: 0/3333 definitions hit the 4000-char pp
cap, 8/3333 hit the 24-definition expansion cap, 3/3333 proof terms exceed 4000
chars.

`TEXT_MAX = 260` / `ASSERTION_MAX = 160` (`judge.py:83-84`) is what binds. Of
the 43 EthTotal items: mean text length **250.4**, max 260, **28 at ≥250, 38 at
≥240**. Commit `714c8f8` records that **8 candidates were lost to the cap
alone**, including `refund_tip_burn_partition_the_prepayment`,
`reported_burn_is_saturated` and `trace_net_unique`; a terser-retry recovered
9 of 11 leftovers, and `destroy_chain_supply` /
`process_transaction_destroy_phase` are still missing.

### 2.5 The vuln-dataset join carries about seven tokens

The EthTotal run used the **legacy** path (`--cover-all
--legacy-label-pairing`) — visible in the ids: a causal run would emit
`obligation_id`s, not `CHK-GEN-NN` (`generate-properties.py:312`). It had no
choice: all 12 obligations in `data/projection_map.json` are
`GasperBeaconChain.*`; **EthTotal has no causal projection map**.

The legacy rule ("most dataset-prevalent critical/high root cause for the
theorem's label") turns out to be a *function of the label alone*:

| label | defect class | items |
|---|---|---:|
| opcodes | `consensus_divergence` | 6 |
| transactions | `integer_overflow_underflow` | 6 |
| state-trie | `improper_state_update` | 10 |
| gas | `integer_overflow_underflow` | 7 |
| block-processing | `missing_bounds_check` | 7 |
| evm | `missing_bounds_check` | 5 |
| beacon-chain:withdrawal | `logic_error_invariant_violation` | 2 |

44 dataset rows contributed 7 distinct tokens across 43 properties, with zero
per-theorem variation — and the label itself comes from the theorem's *file*
(`curation.file_themes`), not its content. On the improve side the evidence
rows are reduced to `(id, severity, label, root_cause)` by the speca#143
safeguard. No concrete historical defect ever reaches a model in this pipeline.

### 2.6 What it cost, measured downstream

| signal | value |
|---|---|
| property × target pairs | 584 total; 261 entered audit; 241 structurally cannot implement; 40 unlocatable |
| **deterministic (tree-sitter) tier resolution, 7 EL targets** | **63 / 258 ≈ 24%** (geth 5/43, erigon 5/43, reth 1/43, revm 4/43, alloy-evm 0/43, nethermind 25, besu 23) |
| `spec_reference_basis: label-default` | 35 / 43 |
| distinct `reachability` values across 43 properties | 1 (blanket `true`) |
| properties demanding a component Ethereum does not have | CHK-GEN-32, CHK-GEN-43 |
| confirmed findings | 0 (5 candidates, all Informational) |

The counter-example is the fix the audit repo made by hand:
`CHK-GEN-32_derivation.md` re-derived four properties from the theorem's
`lean_must_establish` instead of its conclusion, and they resolved **100% on
the deterministic tier**. Same theorem, same code base; the difference is
whether the derivation started from an explicit proof obligation. This is
strong evidence for the direction, but resolution is a locatability signal,
not proof that the semantic projection is correct.

---

## 3. Track-specific state

### 3.1 EthTotal (`20260812-ethtotal`)

Everything in §2 applies as written. The export itself is in good shape — all
3333 theorems proved, zero non-builtin axioms, `proof_source` complete — and is
the strongest raw material either track has. It is simply not consumed.

One asymmetry worth noting: `ethTotalConfig` declares no model assumptions, so
every `Prop` hypothesis is `must-establish`. That is the honest default and it
means `lean_must_establish` is populated for **43/43** properties — the input
R2 needs is already there.

### 3.2 gasper (`20260723-gasper`) — three additional problems

**(a) The shipped 01e was emitted from the test fixture, not from Lean.**
`outputs/20260723-gasper/01e_PARTIAL_gasper.json`, compared field-by-field:

```
lean_statement    == tests/fixtures/theorem_health.sample.json : 27/27
                  == lean/health.json (live export)            :  0/27
lean_proof_source == fixture : 27/27      == live export : 0/27
```

The fixture is not a faithful mirror of the export: 0/25 statements identical,
10/25 differ in hypothesis count, 17/25 differ in their must-establish set (46
vs 53 hypotheses total), 25/25 differ in `proof_source`, 18/25 in `doc_string`.
The fixture's statements read *better* than the live ones precisely because a
human wrote them (`[DecidableEq Validator]`, not `[inst : DecidableEq
Validator]`) — they are a hand-made approximation of what Lean would say.

The cause is a defaulted argument: `tools/emit-track.sh` has
`HEALTH="${5:-tests/fixtures/theorem_health.sample.json}"`, and neither the
emitted document nor `manifest.json` records which health source was used. The
`20260725-gasper-projected` manifest *does* declare
`"proof_health_kind": "sample-fixture"` — that honesty needs to be mechanical,
not per-run discipline.

**(b) The A2 heuristic excuses 85% of the hypotheses.** Across the 25 exported
theorems, 363 binders classify as:

| class | count | rule |
|---|---:|---|
| depend-allowed | 239 | rule 2 — non-`Prop` model parameter |
| depend-allowed | 63 | rule 1 — instance-implicit |
| depend-allowed | 8 | rule 3 — `two_thirds_good`, `good_votes`, `target_height_bound`, `blocks_exist*` |
| **must-establish** | **53** | everything else |

Rules 1 and 2 are sound. But the consequence is that **8 of 25 theorems have
zero must-establish hypotheses** — `finalized_means_one_finalized`,
`slashed_double_vote_iff_bex`, `validator_intersection_lower_bound`,
`justified_iff_bounded`, `q_intersection_slashed_iff_exists_witness`,
`slashed_surround_vote_iff_bex`, `two_thirds_good_iff_forall_exists_goodQuorum`,
`finalization_fork_means_same_finalization_fork_one`. For those,
obligation-based generation has no input, and 10 of the 27 emitted properties
carry no `lean_must_establish` at all. A theorem whose hypotheses are all model
parameters transfers to an implementation only through *how the
implementation instantiates the model* — which is what
`docs/causal-projection.md` exists for, and where those eight belong rather than
in the concretizer.

**(c) `lean/targets.txt` exports 25 declarations; the checkout has ~350.**
The EthTotal workspace exports every theorem on principle ("proof status is
never inferred from a sample"). The gasper workspace does not, so the
supporting lemma layer — exactly the material a proof-chain-aware generator
would walk — is absent from `health.json` and cannot be walked even after R1.

**What gasper got right, and it is worth keeping:** its checklist is mostly
hand-curated (`CHK-AS/QW/SL/JF/LV`), and the run's only surviving in-scope
finding came from `CHK-QW-02` — a curated item. `CHK-AS-03` (curated) produced
the other reviewed candidate. **No `CHK-GEN-*` item produced a candidate in
either track.** That is the cleanest available statement of the problem: the
hand-written items, whose authors read the theorems, found things; the
generated items, whose author saw a name, did not.

---

## 4. Remediation

The target architecture is not “send the theorem text to an LLM”. It is:

```
Lean theorem + reviewed projection
        │
        ▼
canonical implementation obligation
        │
        ├── generation
        ├── improvement
        └── separate fidelity / locatability gates
```

R1 and R2 should land together, but R2 is a generation/projection change, not
a new emitter feature: `mapping.lower_entry()` already decomposes ordinary
theorem-map entries into `-me*` properties. The missing path is that
`generate-properties.py` creates `CHK-GEN-*` before that decomposition and
marks them `lowering: verbatim`.

### R1 — feed a canonical evidence record into generation and improvement

**Status: implemented.** Generation and improvement prompts now receive the
same live-health evidence payload, and its id/hash are retained in the emitted
property. The separate fidelity gate is implemented in
`tools/refine-property-fidelity.py`.

Load the health record and, where applicable, the reviewed projection before
calling the model. Pass a small, structured evidence object to both the
generator and the improve loop:

```
Evidence id            : <stable id>
Source theorem         : <fully-qualified name>
Obligation kind        : <input-precondition | state-invariant |
                          transition-preservation | model-assumption>
Precondition           : <lean_precondition>
Conclusion             : <lean_conclusion>
Owned implementation inputs: <projection.owned_inputs[*]>
Referenced objects     : <referenced_defs_expanded[*].name>
Proof source           : <optional secondary context>
```

The proof source and expanded definitions are supporting context, not the
obligation itself. This prevents a proof tactic such as arithmetic
cancellation from being mistaken for an implementation requirement.

Record the evidence id and a hash of the exact evidence payload in the output.
`x_evidence_read` alone is insufficient if the improve loop cannot read the
same payload.

Cost, measured over the 43 EthTotal properties (generation is one prompt per
property, so per-item size is what matters):

| payload | median | max |
|---|---:|---:|
| statement + must-establish | 382 ch | 2 802 ch |
| proof_source | 360 ch | 3 707 ch |
| referenced_defs_expanded | 1 470 ch | 3 495 ch |
| **bundle** | **≈ 600 tok** | **≈ 2 800 tok** |

For reference, the transitive proof DAG closure (`proof_constants`, depth ∞)
is 11 theorems median / 57 max, ≈ 1 077 tok median / 5 949 tok max of
`proof_source`. Nothing here explodes. Inline the bounded evidence record;
keep `health.json` as a lookup index if the generator wants to walk further.

Do **not** pass a bare filesystem path instead: it removes the record of what
the model saw, makes the four-attempt length retry non-deterministic, turns a
single-shot `subprocess_llm` call into an agentic loop, and — most importantly
— delegates the R2 decision back to the model, which will read the statement
and reproduce today's name expansion. A path is the right tool for one job
only: exploring the *sibling* theorems in the same file (how CHK-GEN-32's fix
actually worked). `--src-root` already exists for that.

### R2 — make the implementation obligation explicit; retain the conclusion

Per `CHK-GEN-32_derivation.md` §1, the implementation-facing unit should often
be a `must_establish` entry, with the theorem conclusion as semantic context.
However, `must-establish` is a provisional exporter heuristic, not proof that
the binder is an implementation obligation. Before generation, classify the
entry as an input precondition, state invariant, transition-preservation
obligation, or model assumption. The last category belongs in causal
projection, not concretization.

The referent table must also run before generation: an object with no referent
in the target (`Ledger.supply`) is routed to projection/review, not silently
turned into a checklist demand.

The conclusion must not be globally discarded. It remains context for an
obligation-derived item and is the primary evidence for a theorem with no
implementation obligation. This is already the intended fallback in
`lower_entry()` for no-precondition theorems.

Applicability in the proof-aware EthTotal run: all 45/45 generated properties
have a non-empty
`lean_must_establish`; gasper 17/27. The gasper remainder goes to
`emit-projected-01e` (§3.2b), not to the concretizer.

### R3 — improve pretty-printing, but do not make it the fidelity mechanism

Options are not the lever (§2.3). Candidates, in order of preference:

1. produce the export from an elaborated file (a command / `#eval` in a module
   that imports both `Lean` and the formalization — the shape gasper-lean4's
   own `#mr_audit_json` already uses), or drive it through
   `Lean.Elab.runFrontend`;
2. failing that, treat `proof_source` as authoritative and `statement` as
   advisory, and say so in the emitted document.

Either way, add a regression test for the A/B reproduction and a structured
export check that stable semantic fields are present. A lexical ban on
`instHAdd.hAdd`, `instMembership`, `._hyg`, `Ne` or `Not` is only a readability
warning: genuine inequalities and negations are valid theorem content, and
pretty-printing alone cannot establish fidelity. Prefer normalized predicate
metadata and source-backed evidence over a string-shape CI gate.

### R4 — separate benchmark quality from proof fidelity

**Status: implemented for EthTotal.** The five quality axes remain separate;
the new fidelity pass reports `faithful` / `repaired` provenance and does not
change the quality score or reference-bar distribution.

Keep the existing five axes for the blind comparison with the reference
corpus. Reference checklist items do not have Lean evidence, so a sixth
fidelity axis cannot be mixed into that distribution without breaking its
calibration.

Add a separate evidence-aware fidelity gate: does the item express a
falsifiable implementation check for the canonical obligation while retaining
the theorem conclusion as context? It should be scored only for items that
have evidence, and should not affect the reference-corpus quality score.

Use deterministic-tier resolution as a non-LLM *locatability* gate. A property
that the tier can place has a referent; that does not prove the semantic
projection is sound. Today's 24% baseline and the hand-derived 32a–d 100%
result are useful operational signals, not correctness ground truth.

### R5 — split at obligation boundaries, not character boundaries

`TEXT_MAX`/`ASSERTION_MAX` encode a benchmark *granularity* (one auditable
concern), which is right. The current generator already retries a length
failure with a terser prompt; the recorded run still shows cap rejects during
the first generation attempt. Keep the retry, but if one theorem yields
several concerns, split at the canonical obligation boundary and assign stable
evidence ids. Never split a sentence mechanically at the character cap.

### R6 — replace the label-prevalence join with reviewed projection

Build an EthTotal `projection_map.json`; the causal path already exists and is
the documented default. Do not replace the label join with a new universal
`head constant → defect class` heuristic: `Eq`, `Membership.mem`, and `LE.le`
are too broad to determine a concrete implementation failure mode. Until a
reviewed projection exists, emit no theorem-specific defect class or route the
candidate to manual review. Keep the dataset as teaching material per
speca#88; stop treating a per-label constant as theorem-specific evidence.

### R7 — make the health source impossible to get wrong (gasper)

- drop the fixture default from `tools/emit-track.sh`; require `--health-json`
  explicitly;
- record it in the emitted document and the manifest —
  `proof_health` (path), `proof_health_kind` (`live-export` | `sample-fixture`),
  the health file hash, target-list hash, exporter commit/config, and the
  export's own commit — the way the `20260725-gasper-projected` manifest
  already does partially;
- CI should fail if an artifact under `outputs/` claims `descends-from-proved`
  while carrying `proof_health_kind: sample-fixture`.

Re-emit `20260723-gasper` from `lean/health.json` once R3 lands, so its Lean
fields describe the formalization rather than a hand-written approximation of
it.

### R8 — widen gasper's export and re-examine rule 3

Move `lean/targets.txt` to the EthTotal policy (every theorem is a target;
generate it mechanically the way `tools/ethtotal-inventory.py` does) so the
lemma layer is available to walk. Separately, re-review the four rule-3 model
assumptions with the gasper maintainers: they excuse only 8 binders, so the
cost of being wrong is small, but the eight zero-must-establish theorems should
be routed to causal projection rather than left to the concretizer.

---

## 5. Acceptance criteria

### Current proof-aware run (2026-08-14)

Using `lean-ethtotal/health.json` and `claude -p`, generation produced 45
CHK-* candidates, rebuilt the 221-entry theorem map, and emitted 45 concrete
01e properties. All 45 carry `descends-from-proved`, an exact evidence hash,
and a fidelity verdict; the separate fidelity review classified 1 as faithful
and repaired 44. The quality judge remains a separate benchmark step and was
not used as a fidelity substitute in this run.

Re-run the EthTotal generation after the canonical evidence/projection path is
implemented and compare against this run:

| metric | baseline (20260812) | target |
|---|---:|---|
| deterministic-tier locatability, EL | 24% | > 60% operational target; report separately from fidelity |
| generated items with an evidence id and evidence hash | not recorded | 100% |
| properties with no referent in any target | 2 | 0 or explicitly routed to projection/review |
| `spec_reference_basis: label-default` | 35/43 | < 10 |
| items rejected only for length | 8 (historical run) | 0 after retry or obligation-level split |
| evidence-aware fidelity gate | not measured | ≥ 4 median, separately from benchmark score |
| pairs audited / total | 261/584 | report with an unambiguous funnel definition |

The cross-client funnel numbers live in the audit repo's
`02c_SUMMARY.json` / `03_SUMMARY.json`. The current summary labels must be
checked before treating `261`, `241`, and `40` as a partition; they do not sum
to `584` as presently written. The audit-repo commit and path should be pinned
when these numbers are used as acceptance evidence.

---

## 6. Reproducing the measurements

```bash
# §2.3 — the pretty-printer A/B (needs the built lean-ethtotal workspace)
cat > /tmp/pptest.lean <<'LEAN'
import Lean
import EthTotal
import EthTotal.Extentions.Audit
open Lean
def tgt : Name := `EthTotal.Ledger.destroy_guard_invalidated_by_credit
open Lean Elab Meta in
#eval show MetaM Unit from do
  let ci := ((← getEnv).find? tgt).get!
  IO.println ("[A] " ++ toString (← Meta.ppExpr ci.type))
unsafe def testB : IO Unit := do
  initSearchPath (← findSysroot); enableInitializersExecution
  let env ← importModules #[{module := `EthTotal}, {module := `EthTotal.Extentions.Audit}]
              Options.empty
  let ci := (env.find? tgt).get!
  let ctx : Core.Context := { fileName := "<t>", fileMap := FileMap.ofString "",
                              options := Options.empty.setBool `pp.proofs true, maxHeartbeats := 0 }
  let (s, _) ← (Meta.MetaM.run' (do pure (toString (← Meta.ppExpr ci.type)))).toIO ctx { env := env }
  IO.println ("[B] " ++ s)
#eval testB
LEAN
(cd lean-ethtotal && ../tools/lean-env.sh lake env lean /tmp/pptest.lean)

# §2.4 / §2.5 / R1 — property-side caps, the label→class join, payload sizes
python3 - <<'PY'
import json, statistics, collections
H = {t['name']: t for t in json.load(open('lean-ethtotal/health.json'))['theorems']}
G = json.load(open('data/ethtotal_generated_properties.json'))['properties']
print('text len mean', round(statistics.mean(len(p['text']) for p in G), 1),
      '≥250:', sum(len(p['text']) >= 250 for p in G), '/', len(G))
j = collections.defaultdict(set)
for p in G: j[p['label']].add(p['x_defect_class'])
print('label -> classes:', {k: sorted(v) for k, v in j.items()})
b = [len(H[p['theorem']]['statement'])
     + sum(len(h['type']) for h in H[p['theorem']]['hypotheses'] if h['class'] == 'must-establish')
     + len(H[p['theorem']]['proof_source'])
     + sum(len(d['pp']) for d in H[p['theorem']]['referenced_defs_expanded']) for p in G]
print('bundle chars median', statistics.median(b), 'max', max(b))
PY

# §3.2a — which health source the shipped gasper 01e actually used
python3 - <<'PY'
import json
P = json.load(open('outputs/20260723-gasper/01e_PARTIAL_gasper.json'))['properties']
live = {t['name']: t for t in json.load(open('lean/health.json'))['theorems']}
fx = {t['name']: t for t in json.load(open('tests/fixtures/theorem_health.sample.json'))['theorems']}
f = l = 0
for x in P:
    k = next(k for k in live if k.endswith('.' + x['lean_artifact'].split('#')[-1]))
    f += x.get('lean_statement') == fx[k]['statement']
    l += x.get('lean_statement') == live[k]['statement']
print(f'lean_statement == fixture: {f}/{len(P)}   == live export: {l}/{len(P)}')
PY
```

---

## See also

- `docs/pipeline.md` — the flow these changes modify, and the honesty bounds
  that must survive them
- `docs/causal-projection.md` — where model-parameter-only theorems belong
  (§3.2b, R2)
- `docs/judge-loop.md` — the loop R4 extends
- `docs/ethtotal-track.md` — the EthTotal track's own gap list
- `speca-audits-2026/outputs/20260812-ethtotal/CHK-GEN-32_derivation.md` — the
  hand-worked example R2 generalizes
