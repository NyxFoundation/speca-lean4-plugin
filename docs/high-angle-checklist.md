# gasper 01e — high-angle checklist (stage ②)

Status: **first draft for review** (speca#88 stage ②). The CHK-* properties
below are LLM-synthesized: the coordinating session wrote them by folding the
`ethereum-vuln-dataset` failure evidence into the proved gasper-lean4 theorems.
They are not mechanically derived from Lean and carry no proof-level guarantee
of their own — each *descends from* a proved theorem (recorded per item and in
`theorem_map.json` as `lowering: "verbatim"` entries) and is anchored to a real
client bug from the dataset (`x_dataset_evidence`). This distinction is
structural, not just prose: a CHK-* property emits
`lean_status: descends-from-proved` (in general `descends-from-<parent
status>`), never plain `proved` — downstream consumers can tell a Lean-verified
mechanical lowering from a hand-written checklist item by the structured field
alone.

How this is built: **Lean gives the invariant that must hold; the dataset gives
how real clients actually broke that class; the checklist item is the
implementation invariant sharpened to catch the real failure mode.** A
mechanical 1:1 restatement of `k_safety'` ("equivocation must be slashable") is
not auditable against code — clients don't fail by disagreeing with the
theorem, they fail in the *arithmetic and bookkeeping* underneath it. Each item
below names the gasper theorem it descends from and the `ethereum-vuln-dataset`
entry that shows the concrete break.

Cross-cutting pattern from the dataset: on the consensus layer, the dominant
Critical/High class is **integer / type-width arithmetic** (overflow,
underflow, signed coercion, float-for-uint64) that makes one client compute a
different result and split consensus. So every quantity a gasper theorem
quantifies over (weights, epochs, indices, counts) is a checklist target on its
arithmetic, not just its logic.

---

## A. Accountable safety — `accountable_safety_witnessB` / `k_safety'`

Proved: two conflicting k-finalized checkpoints ⇒ the ⅔ quorum intersection has
provably violated S1 or S2.

Dataset failure modes:

- **[Lighthouse] LMD-GHOST fork-choice timing attack** (`consensus-specs#2101`,
  ISSUE#1773): attestation-broadcast timing biases which block fork-choice
  converges on.
- **[Lighthouse] fork-choice block-tree filter recursion** DoS.
- **[blst / Finalized #25]** signature-verification bug reachable through
  network-supplied signed consensus data.

Checklist:

- **CHK-AS-01** Fork-choice convergence must not depend on attestation
  *arrival timing* relative to slot boundaries in a way that lets an attacker
  steer it toward a second justifiable head. (If it can, the "two conflicting
  checkpoints" antecedent of `k_safety'` becomes reachable without the
  intersection being attributable.) Audit: the fork-choice weight update path —
  is attestation eligibility gated only by slot/epoch validity, or also by
  wall-clock arrival?
- **CHK-AS-02** Every attestation that enters fork-choice weight must have
  passed signature verification with a current BLS library, and a verification
  failure must reject the attestation, never default-accept it.
  (blst / Finalized #25.)
- **CHK-AS-03** The block-tree / candidate-filter traversal must be bounded
  (no per-block unbounded recursion), so an attacker cannot stall the node into
  missing the slashable-intersection detection window.

## B. Slashable bound & quorum weight — `slashable_bound` / `quorum_intersection_weight_lower` / `validator_intersection_lower_bound`

Proved: the forced-slashed intersection has strictly positive weight,
`wt(qL ∩ qR) ≥ max(wt(vL)−a−e, wt(vR)−a−e) − f⅓(...)`, accounting for
activation/exit churn.

Dataset failure modes:

- **[Lighthouse] attestation `validator_index` not capped before use** →
  integer overflow.
- **[Lighthouse] Eth1 deposit-count underflow** during block processing
  (crafted deposit count).
- **effective-balance / attesting-balance arithmetic** (Electra churn) — the
  weights `wt(...)`, `a` (activations), `e` (exits) are exactly these
  quantities.

Checklist:

- **CHK-QW-01** Every term in the ⅔-threshold and the slashable-weight bound
  (attesting balance, effective balance, total active balance, activation/exit
  churn) must be computed in exact uint64 with explicit overflow/underflow
  handling. A miscomputed weight makes the node disagree on whether the ⅔
  threshold was met — i.e. it justifies/finalizes on a different quorum than
  the spec, breaking the antecedent bookkeeping of `slashable_bound`. Audit:
  the balance-accumulation loops and the deposit-count delta.
- **CHK-QW-02** `validator_index` (and any index read from a network message)
  must be bounds-checked against the active set *before* being used to index
  balances or committees; an out-of-range or overflowing index must reject the
  message, not wrap. (Lighthouse validator_index.)
- **CHK-QW-03** Churn accounting (`a`, `e`: activations/exits per epoch) must
  match the spec's churn-limit formula exactly; an off-by-one or wrong-cap here
  shifts the lower bound the theorem relies on.

## C. Slashing conditions — `slashed_double_vote_iff_bex` (S1) / `slashed_surround_vote_iff_bex` (S2)

Proved: equivocation (two targets, same target epoch) and surround voting are
each slashable, and the boolean checker (`slashedB`) decides them.

Dataset failure modes:

- **[Lodestar] uint64 slashing values as JS `number`** (CWE-190):
  `AttesterSlashing`/`ProposerSlashing` with a value above 2^53 accepted by
  some clients, rejected by others → consensus split (fixed v0.36.0).
- **[Lighthouse] slasher LMDB cursor-reuse memory corruption** — the S1/S2
  detection store itself.

Checklist:

- **CHK-SL-01** All attestation-data fields that S1/S2 compare (source epoch,
  target epoch, target root, validator index) must be exact uint64 / 32-byte
  roots — never a lossy numeric type. A value above 2^53 must be represented
  and compared exactly, or the client silently fails to detect a slashing that
  the theorem says exists, and disagrees with peers on validity. (Lodestar.)
  Audit: the type of every field on the attester/proposer-slashing path from
  decode to comparison.
- **CHK-SL-02** The S1 check must flag *exactly* "same target epoch, distinct
  target" (not same-slot, not same-source) — the theorem's `iff` is precise; a
  weaker predicate misses real equivocations, a stronger one falsely slashes
  honest validators. Audit: the equality/inequality set used in the double-vote
  predicate.
- **CHK-SL-03** The S2 surround predicate must implement strict containment of
  source–target spans in both directions (`s1<s2 ∧ t2<t1`); audit the boundary
  conditions (equal endpoints must not count as surround).
- **CHK-SL-04** The slashing-detection datastore must return owned/copied
  values, not references into a cursor buffer that a later delete invalidates.
  (Lighthouse slasher.) A corrupted read here means a missed or fabricated
  slashing.

## D. Justification & finality — `justified_iff_bounded` / `finalized_means_justified_child` / `k_finalized_means_justified`

Proved: a checkpoint is justified iff a bounded chain of ⅔-supermajority links
reaches it; finalization implies justification of the child.

Dataset failure modes:

- **[Lighthouse] Eth1 deposit / block-processing underflow.**
- **[Electra] sync-committee / epoch-processing** path could stall finality.
- **[Lighthouse] attestation reprocess-queue memory leak / re-propagation
  loop** — stalls the participation input to justification.

Checklist:

- **CHK-JF-01** Justification-status computation must terminate and must match
  the bounded-supermajority-link characterization: no unbounded recursion over
  the checkpoint ancestry, and the "bounded" height-gap must be enforced (an
  off-by-one lets a non-supermajority-linked checkpoint be treated as
  justified). Audit: the ancestor walk and the supermajority-link count.
- **CHK-JF-02** Per-epoch processing (participation flags, justification bits,
  finality update) must complete within the slot budget under maximal churn; a
  step that can stall (Electra sync-committee) breaks plausible liveness of
  finality even with an honest supermajority. Audit: unbounded work per
  validator in epoch processing.
- **CHK-JF-03** The justification bitfield / checkpoint arithmetic must not
  under/overflow (deposit count, epoch numbers), since a wrong count silently
  changes which checkpoint is justified. (Lighthouse deposit underflow.)
- **CHK-JF-04** The attestation ingest queue that feeds justification must
  evict entries deterministically (not "only when the last attestation times
  out"), or an attacker starves the participation input while consuming
  memory. (Lighthouse reprocess-queue.)

## E. Plausible liveness — `two_thirds_good_iff_forall_exists_goodQuorum` / `plausible_liveness_construct_extension`

Proved: with ≥⅔ unslashed/honest stake, a good quorum exists at each step and
the chain can always extend without new slashing.

Dataset failure modes: the DoS class above (unbounded libp2p streams / OOM,
decompression bombs, recursion) — these break the "the underlying chain keeps
producing blocks" precondition.

Checklist (out of bug-bounty *safety* scope, but in scope for liveness):

- **CHK-LV-01** No unbounded resource (libp2p streams, reprocess queue,
  decompression expansion, per-block recursion) on a network-reachable path may
  grow without a cap, since exhausting it stalls block production and voids the
  liveness precondition. Audit the caps on each network-facing allocation.

---

## Why this beats the 1:1 export

The mechanical `emit-01e` lowering produces one property per theorem (or per
must-establish precondition), with zero dataset input. This checklist descends
the same theorems but multiplies each into the *arithmetic, bounds, type-width,
termination, and resource* invariants that are the actual failure surface — and
each item is anchored to a real client bug that broke exactly that surface.
That is what the LLM-in-the-loop stage ② is for: the theorem says what must
hold, the dataset says where it breaks, and the property targets the break.

## How it lands in the plugin

Each CHK-* item is a `theorem_map.json` entry with:

- `property_id` = the CHK id; `theorem` = the descending proved theorem (must
  already be in the non-checklist target set);
- `lowering: "verbatim"` — emitted 1:1 with the hand-written text/assertion,
  never decomposed per must-establish hypothesis (the decomposition describes
  the theorem's statement, not the audit item) and never rewritten into the B2
  shape;
- `lean_status` = `descends-from-<parent status>` (normally
  `descends-from-proved`; `descends-from-unknown` if the parent is
  unresolved) — the hand-written text is not Lean-verified, so it never
  claims plain `proved`; the parent theorem's status stays readable in the
  same passthrough-surviving field (honesty invariant 5,
  `tests/test_honesty.py`);
- `label` / `covers` = the consensus-specs area from the dataset label
  vocabulary (`docs/label_design.md`), anchored in `data/anchor_map.json`;
- `severity` = the cited bug's real impact, per entry (a sibling property of
  the same theorem never raises it — see `mapping._dependent_push`);
- `x_dataset_evidence` = the dataset entry showing the concrete break;
- `shard: "checklist-high-angle"` (one `01e_PARTIAL` file, 15 properties,
  within the benchmark 1-sigma band).

Next: run these through `02c → 03 → 04` on one client (subscription-auth
`claude` CLI, no API key) and post the findings to speca#88.
