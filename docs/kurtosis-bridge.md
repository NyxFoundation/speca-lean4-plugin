# Kurtosis bridge: Core invariant to runnable devnet assertion (issue #7)

How a formally-proved `01e` property becomes a reproducible devnet check, and
the handoff contract to speca#92's `KurtosisVerificationBackend`
(`NyxFoundation/kurtosis-harness`).

This document is the **design** for workstream E. The parts that are
implementable today (E1 checker links, E3 fixture scaffolds, E6 evidence seeds)
are built and tested; the parts that need a running devnet and the backend
(E2, E5) are **blocked on speca#92** and are specified here, not built. No code
in this repo brings up a devnet or claims a reproduction verdict.

## Why Executable is the bridge

gasper-lean4 has two layers. **Core** holds the substantive proofs (accountable
safety, the slashable bound, plausible liveness) as classical existence
statements — `∃` a slashable quorum intersection, `∃` a finalizing extension.
An existence proof is not something you can point a devnet at.

The **Executable** layer is the reproduction bridge: it holds the *decidable
Bool checkers* and *constructive witnesses* that turn those existence claims
into computations.

- **Decidable checkers** — `slashedB`, `justifiedB`, `notSlashedB`,
  `goodQuorumAtB`, `qIntersectionWitnessB` — are total Bool functions over a
  concrete `State`, each proved equivalent to its Core predicate by an
  `..._iff` theorem (`slashed_double_vote_iff_bex`,
  `slashed_surround_vote_iff_bex`, `justifiedB_iff`, `notSlashedB_iff`,
  `goodQuorumAtB_iff`, `q_intersection_slashed_iff_exists_witness`). A checker
  is what a devnet assertion *evaluates* against observed chain state.
- **Constructive witnesses** — `accountable_safety_witnessB`,
  `k_accountable_safety_witnessB`, and the Core
  `plausible_liveness_construct_extension` — don't just decide a predicate,
  they *build a concrete scenario*: the slashable intersection for a given
  fork, or the two-link vote batches that extend and finalize. A witness is
  what *generates the devnet scenario* to drive.

`data/checker_map.json` (E1) records, per theorem, its checkers, the
`..._iff` correctness theorems, and its witness (when one exists). Theorems
with no Executable counterpart — the pure-arithmetic bound theorems
(`slashable_bound`, `quorum_intersection_weight_lower`,
`validator_intersection_lower_bound`) and the definitional bridges
(`finalized_means_one_finalized`, `quorum_2_upclosed`,
`quorum_2_nonempty_of_threshold_pos`) — are honestly absent, and their
properties keep `kurtosis_test = null`.

## The transform: invariant to assertion

A property carries a Core invariant of the shape *"implementation must preserve
[P]; if so, `<theorem>` guarantees [Q]"* (the B1/B2 lowering). The bridge turns
that into a runnable assertion in four steps:

1. **Decide P and Q.** P and Q are Core predicates; the checker map names the
   decidable checker for each (`justifiedB` decides `justified`, `slashedB`
   decides the S1/S2 slashing predicate, `qIntersectionWitnessB` decides
   `q_intersection_slashed`). The `..._iff` theorem certifies the checker
   equals the predicate, so evaluating the checker on observed state is
   evaluating the invariant — no re-interpretation.
2. **Build the scenario.** For a witness-backed property, the constructive
   witness supplies the concrete world (the fork with a slashable intersection,
   the honest two-link extension) that the invariant is *about*. That world is
   the seed for the devnet scenario: which validators equivocate/surround-vote,
   which checkpoints get justified, at what heights.
3. **Map state to observables.** A devnet exposes chain state via the Beacon
   API / Engine API and logs. The transform pins the mapping from the Lean
   `State` fields the checker reads (attestations, targets/sources, justified
   checkpoints, validator weights) to the client-observable equivalents. This
   mapping is per-attack-surface and lives in `kurtosis-harness`, not here.
4. **Assert.** The runnable assertion is: *drive the scenario, observe state,
   evaluate the checker; the client is consistent with the proof iff the
   checker's verdict on observed state matches the invariant's claim.* A client
   that finalizes the fork without the slashable attribution, or accepts an
   equivocation the S1 checker flags, diverges observably.

`emit-kurtosis` (E3) writes this as a **scaffold** per checker-linked property:

```
outputs/kurtosis/<label>/<property_id>/
  devnet.scaffold.json      # placeholder: participants / network_params / scenario = null
  assertion.scaffold.json   # checker refs, the invariant assertion, evidence seeds, handoff record
```

The scaffold is explicitly not runnable (`"scaffold": true`, verdict `null`).
It names the real proved checker and carries everything the backend needs to
fill in — but bringing up the devnet and evaluating the checker is E2/E5.

## Evidence seeds (E6): what the reproduction targets

`data/evidence_seeds.json` attaches, per fixture, the label-matched findings
from `NyxFoundation/ethereum-vuln-dataset` whose `pre_fix_code` /
`files_changed` pin a real implementation site in the same FFG semantics the
property proves. Examples: nimbus PR#461 (justification-bits shift overflow),
lighthouse PR#5037 (equivocation-via-RPC — exactly the S1 predicate `slashedB`
decides), nimbus PR#2392 (uint64→int64 slashing overflow), lighthouse PR#9106 /
lodestar PR#3045 (`total_effective_balance` / unsafe-number weight bugs). These
are the concrete pre-fix code the reproduction should target: the scenario the
witness builds should exercise the code path the seed's diff touched, so a
reproduction on the *pre-fix* commit is expected to trip the checker and the
*post-fix* commit is the negative control. Full hunks stay in the dataset; the
fixture mirrors a capped excerpt plus the `fix_commit` and `files_changed`
pointer.

## E2 (BLOCKED on speca#92): devnet scenario generation

**Design, not built.** Given a witness-backed fixture, the backend generates a
Kurtosis devnet scenario:

- **Topology** from the witness: the number of validators and their stake come
  from the quorum the witness constructs; the equivocating/surround-voting set
  are the validators the witness places in the slashable intersection.
- **Network params** seeded so the target checkpoints reach the heights the
  invariant references (`k`-finalization depth, the source/target epochs of the
  surround pair).
- **Scenario driving** via `kurtosis-harness`'s attack-surface drivers (the
  `AttackSurface` enum: `engine-api`, `block-import`, `p2p-gossip`, …). For an
  FFG property the surface is typically `block-import` / `p2p-gossip` — craft
  the attestations/blocks that realize the witness scenario.
- **Negative control** (the harness's `NegativeControl`): run the same scenario
  against the fixed commit (the E6 seed's `fix_commit`) or with the guard
  enabled; the checker must flip from tripped to clean.

This needs a running Kurtosis devnet and the harness's drivers, which live in
`kurtosis-harness` behind speca#92's backend seam. This repo deliberately
vendors none of it — matching the speca#87/#88 plugin boundary (Lean/`lake` and
Kurtosis machinery stay out of core and out of each other's repos).

Note the shape gap the backend bridges: this repo's fixture is FFG/consensus
semantics-shaped (checker + witness + invariant), while `kurtosis-harness`'s
current `FindingSpec` schema is resource-exhaustion-shaped (`ResourceSignal`
rss/cpu/restart, `Threshold` on RSS). Consensus-divergence findings need a
*state-consistency* signal (does the checker's verdict on observed state match
the proof's claim) rather than a resource threshold. Adding that signal type to
the harness schema is part of the speca#92 backend work; the scaffold's
`assertion` + `checker` fields are the inputs it will consume.

## E5 (BLOCKED on speca#92): handoff to `KurtosisVerificationBackend`

**Design, not built.** The backend runs strictly *after* the `04` gates on
filtered confirmed findings (per speca#92). For a property that already ships a
`kurtosis_test`, the backend reuses the fixture instead of regenerating (the
speca#92 review checklist requires this). Each run produces exactly the record
the scaffold pre-shapes under `assertion.scaffold.json → handoff`:

```json
{
  "property_id": "PROP-lean-safety-core-001-me1",
  "verdict":     "reproduced | not-reproduced | error",
  "harness":     "NyxFoundation/kurtosis-harness",
  "artifact_path": "…/reports/<client>/poc/<property_id>/",
  "logs_path":     "…/logs/<run-id>.log"
}
```

The scaffold emits this with `verdict: null` and `artifact_path` / `logs_path`
null — nothing has run. The backend:

1. loads the fixture, reads `checker` + `assertion` + `evidence_seeds`;
2. generates (E2) or reuses the devnet scenario, brings up the pinned client;
3. drives the scenario, captures observed state + logs;
4. evaluates the checker against observed state, sets `verdict` accordingly
   (evidence-backed: `artifact_path` and `logs_path` must be present, per the
   speca#92 checklist — a verdict without evidence is rejected);
5. checks fix status against the target's latest commit and flags
   `reproduced && unfixed` as disclosure-pending.

The verdict vocabulary (`reproduced | not-reproduced | error`) is speca#92's;
this repo's honesty rule maps a scaffold to none of them — `verdict: null`
means "not yet run", never "not reproducible".

## Honesty summary

- Fixtures are scaffolds (`"scaffold": true`); no devnet is brought up here and
  no verdict is asserted.
- `kurtosis_test` / `checker` / `witness` are non-null **only** where a real,
  proved Executable checker exists — 43 of 54 sample properties; the other 11
  (pure-arithmetic bound and definitional theorems) are honestly null.
- All checker/witness names are verified against gasper-lean4's
  `GasperBeaconChain/Executable/*.lean`; `data/checker_map.json` cites the
  `..._iff` correctness theorem for each.
- Evidence seeds reference the ethereum-vuln-dataset; full pre/post-fix code
  stays in the dataset, only a capped excerpt is mirrored.
- E2 and E5 are design-only pending speca#92 and `kurtosis-harness`.
