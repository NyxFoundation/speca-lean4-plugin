#!/usr/bin/env python3
"""Build the execution-layer anchor table from a pinned execution-specs checkout.

`data/anchor_map.json` anchors the gasper (consensus) labels to
consensus-specs pyspec symbols. The EthTotal track is execution-layer, so its
labels have no entry there and its properties emitted with `spec_reference`
absent — honest, but it left the auditor to locate the surface themselves,
which was the one place the EthTotal checklist measured weaker than the gasper
one.

This produces the counterpart table against
[`ethereum/execution-specs`](https://github.com/ethereum/execution-specs) (EELS).

Two things are deliberately separated:

- **judgment** — which spec surface a dataset label corresponds to. That is the
  `_LABEL_SURFACES` table below, and it is mine to defend.
- **fact** — whether the named symbol actually exists. That is not asserted: it
  is resolved by locating the definition in the checkout, and a symbol that
  cannot be located is a hard error, never a silently dropped row. Every
  emitted row therefore carries `file`, `line` and the revision they were
  verified at.

Per-property rows go one step further: a property is anchored to the surface
whose symbol literally appears in its own text or assertion (recorded as
`matched_in_text`), falling back to the label's primary surface otherwise. So
"this check is about `selfdestruct`" is evidence from the property itself
rather than an inherited label default.

Usage:
    git clone --depth 1 https://github.com/ethereum/execution-specs /tmp/execution-specs
    python3 tools/build-el-anchor-map.py --specs /tmp/execution-specs
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# The fork whose modules are anchored. EELS keeps one module tree per fork;
# anchoring to a named fork (rather than "latest") keeps the reference stable
# and reviewable.
_FORK = "prague"

# --- judgment: dataset label -> execution-specs surface ----------------------
# `primary` is the symbol `spec_reference` / `covers` resolve to; `surfaces`
# are the other symbols an auditor of that label works in, and are what
# per-property matching picks from. `_MODULES` maps a short module key to its
# path under the checkout so the fork appears in exactly one place.
_MODULES = {
    "state_tracker": "src/ethereum/forks/{fork}/state_tracker.py",
    "fork": "src/ethereum/forks/{fork}/fork.py",
    "transactions": "src/ethereum/forks/{fork}/transactions.py",
    "interpreter": "src/ethereum/forks/{fork}/vm/interpreter.py",
    "gas": "src/ethereum/forks/{fork}/vm/gas.py",
    "system": "src/ethereum/forks/{fork}/vm/instructions/system.py",
    "storage": "src/ethereum/forks/{fork}/vm/instructions/storage.py",
    "environment": "src/ethereum/forks/{fork}/vm/instructions/environment.py",
    "precompiles": "src/ethereum/forks/{fork}/vm/precompiled_contracts/mapping.py",
    "trie": "src/ethereum/merkle_patricia_trie.py",
    "state": "src/ethereum/state.py",
}

_LABEL_SURFACES: dict[str, dict] = {
    "state-trie": {
        "primary": ("state_tracker", "set_account_balance"),
        "surfaces": [
            ("state_tracker", "set_account"),
            ("state_tracker", "get_account"),
            ("state_tracker", "extract_block_diff"),
            ("state", "compute_state_root"),
            ("trie", "trie_set"),
        ],
        "why": "account balance persistence and the state root computed from it — "
               "the surface a supply/balance reconciliation invariant lives on",
    },
    "transactions": {
        "primary": ("fork", "process_transaction"),
        "surfaces": [
            ("state_tracker", "move_ether"),
            ("fork", "check_transaction"),
            ("transactions", "calculate_intrinsic_cost"),
            ("state_tracker", "increment_nonce"),
        ],
        "why": "value transfer and sender debit: where an overdraft, a stale read or a "
               "self-transfer would create value",
    },
    "gas": {
        "primary": ("fork", "process_transaction"),
        "surfaces": [
            ("gas", "charge_gas"),
            ("transactions", "calculate_intrinsic_cost"),
            ("fork", "check_transaction"),
            ("fork", "calculate_base_fee_per_gas"),
        ],
        "why": "the prepay -> refund/priority-fee/base-fee-burn settlement; the fee "
               "split itself is performed inside process_transaction",
    },
    "evm": {
        "primary": ("interpreter", "process_message"),
        "surfaces": [
            ("interpreter", "process_message_call"),
            ("interpreter", "process_create_message"),
            ("state_tracker", "move_ether"),
        ],
        "why": "CALL/CREATE value semantics, executed through the message-processing path",
    },
    "opcodes": {
        "primary": ("system", "selfdestruct"),
        "surfaces": [
            ("storage", "sstore"),
            ("storage", "sload"),
            ("environment", "balance"),
            ("state_tracker", "destroy_account"),
            ("state_tracker", "account_exists_and_is_empty"),
        ],
        "why": "account lifecycle at the opcode level: SELFDESTRUCT, storage writes and "
               "the empty-account predicate",
    },
    "database": {
        "primary": ("state_tracker", "incorporate_tx_into_block"),
        "surfaces": [
            ("state_tracker", "copy_tx_state"),
            ("state_tracker", "restore_tx_state"),
            ("state_tracker", "extract_block_diff"),
        ],
        "why": "the journal/commit/rollback path — where a record is made durable, and "
               "where an ordering or revert defect corrupts the audit trail",
    },
    "block-processing": {
        "primary": ("fork", "apply_body"),
        "surfaces": [
            ("fork", "state_transition"),
            ("fork", "process_withdrawals"),
            ("fork", "make_receipt"),
            ("state_tracker", "create_ether"),
        ],
        "why": "block-level application of rewards, fees and withdrawals — the mint/burn "
               "attribution surface",
    },
    "precompiles": {
        "primary": ("precompiles", "PRE_COMPILED_CONTRACTS"),
        "surfaces": [("interpreter", "process_message_call")],
        "why": "the precompile dispatch table; value-forwarding precompile paths enter here",
    },
    "beacon-chain:withdrawal": {
        "primary": ("fork", "process_withdrawals"),
        "surfaces": [("state_tracker", "create_ether"), ("state_tracker", "set_account_balance")],
        "why": "NOTE: the dataset label is the consensus-side name, but the properties it "
               "carries here are about the EXECUTION-layer credit of a withdrawal, so the "
               "anchored surface is the EL one. Recorded explicitly rather than silently.",
    },
}

# Indented matches are class members (e.g. `State.compute_state_root`), which
# are just as legitimate an anchor as a module-level function — the kind is
# recorded so the table says which it is rather than blurring them.
# Symbols that are also ordinary English words. Matching a property's text
# against these bare would anchor "…proves balance >= burn amount…" to the
# BALANCE opcode, which is wrong. They only count in OPCODE form (`BALANCE`);
# a qualified `post_state.balance(a)` in an assertion is pseudo-code for the
# balance field, not a reference to the opcode, so that does not count either.
_AMBIGUOUS = {"balance", "root", "mapping", "state", "storage"}

_DEF_RE = "^(?P<indent>\\s*)(?:async\\s+)?def\\s+{sym}\\b"
_ASSIGN_RE = "^(?P<indent>\\s*){sym}\\s*[:=]"


def locate(specs: Path, module_key: str, symbol: str) -> tuple[str, int, str]:
    """(path, line, kind) of a symbol's definition — or a hard error."""
    rel = _MODULES[module_key].format(fork=_FORK)
    path = specs / rel
    if not path.is_file():
        raise SystemExit(f"execution-specs: no such module {rel}")
    text = path.read_text(encoding="utf-8").split("\n")
    pat_def = re.compile(_DEF_RE.format(sym=re.escape(symbol)))
    pat_assign = re.compile(_ASSIGN_RE.format(sym=re.escape(symbol)))
    for i, line in enumerate(text, 1):
        m = pat_def.match(line) or pat_assign.match(line)
        if m:
            return rel, i, ("method" if m.group("indent") else "function")
    raise SystemExit(f"execution-specs: {symbol} not defined in {rel} — refusing to emit an unverified anchor")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", required=True, help="ethereum/execution-specs checkout")
    ap.add_argument("--map", default=str(_ROOT / "theorem_map_ethtotal.json"))
    ap.add_argument("--out", default=str(_ROOT / "data" / "anchor_map_execution.json"))
    args = ap.parse_args()

    specs = Path(args.specs)
    rev = subprocess.run(["git", "-C", str(specs), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()

    labels: dict[str, dict] = {}
    surface_index: dict[str, list[dict]] = {}
    for label, cfg in _LABEL_SURFACES.items():
        pk, ps = cfg["primary"]
        prel, pline, pkind = locate(specs, pk, ps)
        surfaces = []
        for k, s in cfg["surfaces"]:
            rel, line, kind = locate(specs, k, s)
            surfaces.append({"symbol": s, "file": rel, "line": line, "kind": kind})
        labels[label] = {
            "spec_doc": prel,
            "spec_symbol": ps,
            "spec_symbol_line": pline,
            "spec_symbol_kind": pkind,
            "why": cfg["why"],
            "surfaces": surfaces,
        }
        surface_index[label] = [{"symbol": ps, "file": prel, "line": pline, "kind": pkind}] + surfaces

    # per-property rows: prefer the surface the property itself names
    tmap = json.loads(Path(args.map).read_text(encoding="utf-8"))
    defs = []
    matched = 0
    for e in tmap["properties"]:
        label = e["label"]
        cands = surface_index.get(label)
        if not cands:
            raise SystemExit(f"{e['property_id']}: label {label!r} has no execution-specs surface")
        hay = f"{e.get('text','')} {e.get('assertion','')}"

        def names(sym: str) -> bool:
            if sym.lower() in _AMBIGUOUS:
                return bool(re.search(rf"\b{sym.upper()}\b", hay))
            return bool(re.search(rf"\b{re.escape(sym)}\b", hay))

        hit = next((c for c in cands[1:] if names(c["symbol"])), None)
        if hit is None and names(cands[0]["symbol"]):
            hit = cands[0]
        chosen = hit or cands[0]
        matched += hit is not None
        defs.append({
            "property_id": e["property_id"],
            "theorem": e["theorem"],
            "label": label,
            "spec_symbol": chosen["symbol"],
            "spec_reference": f"execution-specs:{chosen['file']}#{chosen['symbol']}",
            "matched_in_text": hit is not None,
        })

    out = {
        "version": 1,
        "generated_by": "tools/build-el-anchor-map.py",
        "spec_source": "ethereum/execution-specs",
        "spec_revision": rev,
        "spec_fork": _FORK,
        "reference_prefix": "execution-specs",
        "note": (
            "Execution-layer counterpart of data/anchor_map.json. That table anchors the "
            "consensus labels to consensus-specs pyspec symbols; this one anchors the "
            "value-bearing execution labels used by the EthTotal track to EELS symbols. "
            "Which surface a label corresponds to is reviewed judgment (see each row's "
            "`why`); whether the symbol EXISTS is not asserted — every row was resolved by "
            "locating the definition in the pinned checkout, and the file/line recorded. "
            "Regenerate after an execution-specs bump: a symbol that moved or was renamed "
            "fails the build rather than silently anchoring to nothing. Anchors are "
            "fork-scoped (see spec_fork); a different fork means regenerating, not editing."
        ),
        "labels": labels,
        "defs": defs,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_sym = sum(1 + len(v["surfaces"]) for v in labels.values())
    print(f"{len(labels)} labels / {n_sym} verified symbols @ {rev[:12]} ({_FORK}) -> {args.out}")
    print(f"  per-property rows: {len(defs)}, of which {matched} anchored to a symbol named in the property itself")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
