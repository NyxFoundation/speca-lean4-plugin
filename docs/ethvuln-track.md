# EthVuln track — ethereum-vuln-dataset Critical/High → `01e`

The plugin's third formalization target (M2 Track C / c-1, speca#146),
alongside gasper-lean4 (consensus) and eth-total-supply-safety (execution).
For every `severity_estimated ∈ {Critical, High}` entry of
[`NyxFoundation/ethereum-vuln-dataset`](https://github.com/NyxFoundation/ethereum-vuln-dataset)
(66 entries at the pinned `ethvuln_ref`, CRITICAL 3 / HIGH 63), the invariant
that bug broke is formalized as a Lean 4 theorem of the shape *named
implementation obligations (must-establish hypotheses) ⇒ named-predicate
conclusion (the guaranteed invariant)*, placed in this repo, and registered so
the exporter and the `01e` emitter treat it exactly like any other theorem.
Since the PR #24 review revision the shallow implications are **proved**
(`sorry`-free); the audit content lives, by design, in the hypotheses that an
implementation must establish.

Nothing about the gasper or EthTotal tracks changed: `theorem_map.json`,
`lean/Main.lean` and the gasper export are byte-for-byte what they were.

## Layout

| piece | path |
|---|---|
| shared definitions (`Handler`, `ValidatedBy`, `ResourceModel`, …) — the only place concept definitions live | `lean/SpecaExport/EthVuln/Common.lean` |
| one file per invariant class, one theorem per entry (66) | `lean/SpecaExport/EthVuln/Props/*.lean` |
| root module (imports `Common` + every `Props/*`) | `lean/SpecaExport/EthVuln.lean` |
| package root registration (so `lake build` builds the track) | `lean/SpecaExport.lean` — `import SpecaExport.EthVuln` |
| exporter entry point (`ethVulnConfig`, runtime root `SpecaExport.EthVuln`) | `lean/MainEthVuln.lean` → `lake exe speca-export-ethvuln` |
| theorem → `01e` map (66 `PROP-lean-ethvuln-*`, per-entry `x_spec_anchor` + `audit_packet`) | `theorem_map_ethvuln.json` |
| deterministic packet/anchor regeneration (no LLM) | `tools/ethvuln-build-packets.py` |
| per-entry spec-anchor curation (consumed by the tool above) | `data/ethvuln_spec_anchors.json` |
| versioned exporter output (real `speca-export-ethvuln` run) | `tests/fixtures/theorem_health.ethvuln.sample.json` |
| sample full-node scope (both layers) | `tests/fixtures/bug_bounty_scope.ethvuln.sample.json` |
| honesty invariants | `tests/test_ethvuln.py` |

Theorem names are `EthVulnFormalProps.entry_<sanitized dataset id>_<primary
class>` — the namespace is the generating package's
(`banr1/eth-vuln-formal-props`, private), only the module path changed on
placement, so fully-qualified names match its `theorem_map` generator. Each
docstring records the entry id, the informal statement of the broken
invariant, the dataset `root_cause`, every class the entry was assigned, and
— for the 18 entries formalized at class level (undisclosed security releases,
spec/feature PRs) — the abstraction taken and why.

Class breakdown (primary class = `shard`): availability-robustness 15,
resource-bounds 14, spec-equivalence 13, arithmetic-safety 9, memory-safety 4,
input-validation 4, crypto-auth-integrity 4, state-integrity 2,
serialization-fidelity 1. By layer (`bug_bounty_area`): execution 43,
consensus 23.

## Why its own map and its own exporter entry point

The first placement put the 66 entries into `theorem_map.json` and changed
nothing else. That broke CI in two independent ways, and both are structural:

1. **The gasper exporter never saw the modules.** `lake build` built
   `SpecaExport.EthVuln.*` fine, but `lake exe speca-export` resolves targets
   against the environment `lean/Main.lean` loads at run time
   (`importModules` of `GasperBeaconChain.Core.All` +
   `GasperBeaconChain.Executable.All`), so every `EthVulnFormalProps.*` target
   came back `resolved: false` and the smoke gate failed. The fix is an entry
   point that imports the track at compile time *and* passes it to
   `driverMain` at run time — `lean/MainEthVuln.lean`, with `ethVulnConfig`
   (`nsPrefix = EthVulnFormalProps`) so `referenced_constants` /
   `referenced_defs_expanded` are the track's own definitions rather than
   nothing. Adding the import to `Main.lean` instead would have worked for
   resolution but would have (a) filtered every EthVuln constant out as
   non-project-local and (b) attributed the `lean_artifact` to gasper-lean4.
   `tests/test_ethvuln.py` pins this wiring.
2. **`theorem_map.json` carries a contract the entries cannot meet.** Its
   tests assert that every non-checklist entry is `proved`, that every label
   is in the consensus anchor table and every `spec_reference` is a
   `consensus-specs:` one, that `data/anchor_map.json` has one row per entry
   and `data/projection_map.json` classifies every theorem for both layers.
   The 66 entries were `sorry` stubs at first placement, span both layers,
   and 10 of their labels (`p2p`, `rpc`, `crypto`, `sync`, `txpool`,
   `engine-api`, `validator`, `build-ci`, `other`,
   `beacon-chain:sync-committee`) have no pyspec / execution-specs anchor at
   all. Bending those tests would weaken the gasper guarantees; inventing
   anchors would fabricate them. So — exactly as the EthTotal track did — the
   entries live in `theorem_map_ethvuln.json` with a contract of their own.

## The PR #24 review revision — obligations vs preconditions, and predicates
## that the vulnerable implementation cannot satisfy

The first placement drew a CHANGES_REQUESTED review with four findings; all
four are structural and all four are fixed here:

1. **Conclusion guards leaked into must-establish.** The exporter flattens
   the whole theorem type with `forallTelescope`, so a conclusion written as
   `∀ c k, k < len c → InBounds …` leaked its guard (`k < len c`, an
   access-time context condition) into the must-establish list — 29 of the
   original 130 must-establish hypotheses (~22 %) were such input/context
   premises, and B1 lowered each to a meaningless standalone "obligation".
   Fixed twice over: every conclusion is now a **single application of a
   named `Common` predicate** (`AccessesInBounds`, `SpecEquivOn`,
   `AcceptanceCarriesOver`, `AcceptsOnlyValid`, `OnAccept`,
   `PreservesInvOnTrace`, `GrantedOnlyVerified`, `MulModZeroTotal`, … — the
   guards live inside the definition; two disclosed exceptions stay closed
   guard-free forms rather than predicates: `entry_a528f48…`'s constant
   inequality `400 * 1024 ≤ implMaxProofSize` and `entry_…7pg2…`'s
   conjunction `ShiftSaturates … ∧ SarSaturates …`), and the exporter's A2
   heuristic gained rule 4: an
   anonymous (hygienic-named) `Prop` binder is classified
   `context-precondition`, never `must-establish`, and B1 never lowers it.
   `tests/test_ethvuln.py` pins both (no hygienic name in must-establish, no
   context-precondition residue at all).
2. **`ArithAgrees` was satisfiable by the vulnerable implementation.** It
   required agreement only where the mathematical result fits the width, so
   an ordinary wrapping add satisfied both the `% 2^n` hypotheses and the
   conclusion — for the overflow entries (gorilla/websocket, geth p2p, Juno)
   the theorem did not exclude the bug it formalized. It is replaced by two
   predicates with disjoint jobs: `AgreesModWidth` (full-domain exact
   modulo-`2^n` semantics, for operations whose *spec* is modular — consensus
   uint64, EVM gas words; narrowing/IEEE-754 implementations violate it
   **because the spec side is pinned to a concrete function** — `Nat.+` for
   uint64 addition and `Common.evmCallGas`, the EIP-150 63/64 model, for the
   Besu CALL-gas entries; a free spec parameter would let a narrowing
   implementation choose the spec to match itself, so no arithmetic theorem
   leaves the spec free) and
   `CheckedArith`/`AcceptedExact` (`Option`-valued checked arithmetic —
   overflow must be *detected*, a wrapping implementation cannot satisfy it).
   The EVM shift/MULMOD entries state the spec clauses themselves
   (`ShiftSaturates`, `SarSaturates`, `evmMulMod _ _ 0 = 0`) and are proved
   against the spec model.
3. **The availability theorems were tautologies.** `hTotal` (every input
   lands in ok/reject) is `NeverCrashes` restated, so 11 of 15 theorems said
   `P → P`. They are decomposed into the two concrete conditions an
   implementation actually defends — `RejectsMalformed` (malformed input is
   rejected *without state change*: parse/validation totality + rollback)
   and `TotalOnWellFormed` (well-formed input is processed totally; resource
   exhaustion and internal errors land in a defined, state-preserving
   reject) — with `NeverCrashes` derived by `Common.neverCrashes_of_split`.
   For undisclosed-advisory entries the docstrings state explicitly that
   this staging is a modeling choice over standard crash vectors, not a
   dataset fact.
4. **01e obligations lacked the EthTotal-style packet separation.** Every
   map entry now carries a deterministic `audit_packet`
   (`tools/ethvuln-build-packets.py` — no LLM, regenerated verbatim from the
   exporter health) with the review's three-way separation made explicit:
   `guarantee` = the exact Lean root conclusion, `obligations` = what the
   implementation must establish (the named must-establish hypotheses,
   exact Lean types), `preconditions` = the full class-tagged hypothesis
   list (EthTotal-compatible rendering), and `supporting_facts` =
   `FACT-ROOT` plus one exact `FACT-OB*` assertion per obligation. Packets
   carry no proof status.

A pleasant consequence of 1–3: with obligations named and conclusions folded,
every implication became shallow, so **all 66 theorems are now proved**
(`lake build` with zero `sorry` warnings; several entries additionally rest
on `Classical.choice` via the split lemmas, surfaced honestly by
`choice_free`). One honest residue: for `entry_eff1234250453226` (jsonparser
OOB read) the fix *is* the broken invariant — "every read position is
checked against the buffer" — so its implication is a definitional
unfolding; the audit content is the must-establish obligation itself, and
the docstring says so. Similarly, the three spec-clause entries (the Besu
shifts and geth MULMOD) carry no must-establish hypothesis at all: the Lean
theorem certifies the spec clause on the `Common` model, and the
implementation obligation is exactly the emitted property's assertion
("the client's operation satisfies this clause"), bound to code in 02c.

## Proof status — what is and is not claimed

The map deliberately carries **no proof-status field**. Status comes from one
place only, the exporter: `lean_status: "proved"` / `sorry_free: true` for a
certified declaration, `"unknown"` / `false` for a `sorryAx`-dependent one.
`emit-01e` copies that verbatim into every emitted property. The CI steps and
`tests/test_ethvuln.py` assert the *pairing* (`proved` ⇔ `sorry_free`) and
that the emitted status equals the exporter's — never a particular value — so
a regression to `sorry` would be reported just as honestly as today's
`proved`. Note what `proved` certifies: the *implication* from the named
implementation obligations to the named invariant. Whether a real client
establishes those obligations is exactly the 02c audit question, and the
must-establish properties are its work items.

## Spec anchoring

Two layers, both honest:

- **Label-level (emitted).** Labels with a row in `data/anchor_map.json`
  (consensus — now including `beacon-chain:execution-payload`) or
  `data/anchor_map_execution.json` (execution) resolve to a `spec_reference`
  and a table-derived `covers`, the same way the other two tracks do; the 10
  unanchored labels emit **no `spec_reference`** (and `covers` falls back to
  the map's `covers_hint`), and the map's `note` names them. Nothing is
  pointed at a document that does not describe it.
- **Per-entry (map, PR #24 review).** Every entry carries `x_spec_anchor`:
  a `consensus-specs:specs/…` / `execution-specs:src/ethereum/…` section
  (plus `x_spec_symbol`) when the broken invariant is genuinely
  protocol-semantics — 20 of 66 — or an explicit `N/A — <category>: <reason>`
  (dependency-library, networking-devp2p, rpc-api, client-internal,
  undisclosed) for the 46 out-of-spec surfaces, which are implementation
  safety, not spec conformance. Anchors are curated per entry (they can
  disagree with the coarse label where the label is wrong — e.g. the
  Lighthouse Electra effective-balance entry is labeled
  `beacon-chain:sync-committee` but anchored to
  `process_effective_balance_updates`), and `tests/test_ethvuln.py` enforces
  the field's presence and format.

## Pipeline

```sh
# health (from lean/; --src-root . gives the A7 verbatim proof_source slices,
# because these .lean files are this package's own, not a dependency's)
cd lean && lake build
python3 - <<'PY' > targets_ethvuln.txt
import json
m = json.load(open("../theorem_map_ethvuln.json"))
print("\n".join(dict.fromkeys(e["theorem"] for e in m["properties"])))
PY
lake exe speca-export-ethvuln --targets targets_ethvuln.txt \
  --output health_ethvuln.json --src-root .

# map enrichment (audit packets + per-entry spec anchors; deterministic,
# idempotent — rerun after any statement/health change)
python3 tools/ethvuln-build-packets.py \
  --map theorem_map_ethvuln.json \
  --health tests/fixtures/theorem_health.ethvuln.sample.json \
  --anchors data/ethvuln_spec_anchors.json

# 01e (from the repo root)
speca-lean4 emit-01e \
  --map theorem_map_ethvuln.json \
  --scope tests/fixtures/bug_bounty_scope.ethvuln.sample.json \
  --health-json lean/health_ethvuln.json \
  --out 01e_ethvuln.json --out-dir 01e_ethvuln_shards
# or let the CLI run the exporter (the map's `lean_exe` selects
# speca-export-ethvuln; `x_src_roots` supplies --src-root):
speca-lean4 emit-01e --map theorem_map_ethvuln.json \
  --scope tests/fixtures/bug_bounty_scope.ethvuln.sample.json --run-lean \
  --out 01e_ethvuln.json
```

Emitted today: 118 properties from 66 theorems (115 must-establish
decompositions — every *named* `Prop` hypothesis is must-establish under
`ethVulnConfig`'s honest default, no model-assumption list — plus 3
undecomposed entries whose theorems are hypothesis-free spec clauses), all
`lean_status: proved`, every one carrying its `audit_packet`.

CI (`.github/workflows/ci.yml`): the `lean` job exports the track's health
with `speca-export-ethvuln` (gate: every target resolved, `proved` ⇔
`sorry_free`, expanded defs are `EthVulnFormalProps.*`) and emits the 01e
from it; the `python` job emits from the versioned fixture health and checks
the status is copied, not upgraded; the cold `run-lean-e2e` job runs
`emit-01e --map theorem_map_ethvuln.json --run-lean` so the map-selected
executable path is exercised end to end.
