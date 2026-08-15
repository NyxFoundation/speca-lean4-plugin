# EthVuln track — ethereum-vuln-dataset Critical/High → `01e`

The plugin's third formalization target (M2 Track C / c-1, speca#146),
alongside gasper-lean4 (consensus) and eth-total-supply-safety (execution).
Where those two lower *proved* theorems, this track lowers **statements**: for
every `severity_estimated ∈ {Critical, High}` entry of
[`NyxFoundation/ethereum-vuln-dataset`](https://github.com/NyxFoundation/ethereum-vuln-dataset)
(66 entries at the pinned `ethvuln_ref`, CRITICAL 3 / HIGH 63), the invariant
that bug broke is formalized as a Lean 4 proposition, placed in this repo, and
registered so the exporter and the `01e` emitter treat it exactly like any
other theorem — including reporting, honestly, that it is **not proved yet**.

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
| theorem → `01e` map (66 `PROP-lean-ethvuln-*`) | `theorem_map_ethvuln.json` |
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
   The 66 entries are `sorry` stubs, span both layers, and 11 of their labels
   (`p2p`, `rpc`, `crypto`, `sync`, `txpool`, `engine-api`, `validator`,
   `build-ci`, `other`, `beacon-chain:execution-payload`,
   `beacon-chain:sync-committee`) have no pyspec / execution-specs anchor at
   all. Bending those tests would weaken the gasper guarantees; inventing
   anchors would fabricate them. So — exactly as the EthTotal track did — the
   entries live in `theorem_map_ethvuln.json` with a contract of their own.

## Proof status — what is and is not claimed

**Every one of the 66 theorems is currently a `sorry` stub.** The statements
type-check (`lake build` passes with `declaration uses 'sorry'` warnings);
the proofs are out of scope for c-1 and are recorded as such in every
docstring and in each `Props/*` module comment.

The map deliberately carries **no proof-status field**. Status comes from one
place only, the exporter, which reports a `sorryAx`-dependent declaration as
`lean_status: "unknown"`, `sorry_free: false`. `emit-01e` copies that verbatim
into every emitted property. The CI steps and `tests/test_ethvuln.py` assert
the *pairing* (`proved` ⇔ `sorry_free`) and that the emitted status equals the
exporter's — never a particular value — so the day a proof lands the same
command reports it `proved` with no change to the map, the CI or the tests,
and nothing today reads as more than it is.

What the track *does* deliver is the type: "what this bug broke", fixed as a
Lean proposition that a later proving phase (or the c-2 / #147 backbone) can
attach to.

## Spec anchoring

Labels are ethereum-vuln-dataset labels. Those with a row in
`data/anchor_map.json` (consensus) or `data/anchor_map_execution.json`
(execution) resolve to a `spec_reference` and a table-derived `covers`, the
same way the other two tracks do; the 11 unanchored labels above emit **no
`spec_reference`** (and `covers` falls back to the map's `covers_hint`), and
the map's `note` names them. Nothing is pointed at a document that does not
describe it.

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

Emitted today: 131 properties from 66 theorems (130 must-establish
decompositions — every `Prop` hypothesis is must-establish under
`ethVulnConfig`'s honest default, no model-assumption list — plus one
undecomposed entry), all `lean_status: unknown`.

CI (`.github/workflows/ci.yml`): the `lean` job exports the track's health
with `speca-export-ethvuln` (gate: every target resolved, `proved` ⇔
`sorry_free`, expanded defs are `EthVulnFormalProps.*`) and emits the 01e
from it; the `python` job emits from the versioned fixture health and checks
the status is copied, not upgraded; the cold `run-lean-e2e` job runs
`emit-01e --map theorem_map_ethvuln.json --run-lean` so the map-selected
executable path is exercised end to end.
