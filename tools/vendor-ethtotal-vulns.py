#!/usr/bin/env python3
"""Vendor the EthTotal-domain critical/high slice of ethereum-vuln-dataset.

The stage-2 improve/generate loop needs *teaching material*: real client defect
classes at bug-bounty severity, in the domain the checklist is about. The
existing `data/ethereum_vulns_high.csv` is the whole EL+CL surface (176 rows),
which is right for the Gasper FFG checklist but dilutes an EthTotal run with
consensus-only classes (attestation, sync-committee, fork-choice) that a supply
-accounting invariant has nothing to say about.

So this cuts the same 176-row critical/high population down to the labels that
can move, mis-record or double-count value — the surfaces EthTotal's ledger and
supply theorems actually speak to. The filter is STRUCTURAL (label membership
only, no per-finding prose judgment), so the slice is reproducible from the
pinned revision.

Severity uses the dataset's `severity_estimated` column, not the advisory
`severity` column — same choice (and same reason) as
`data/ethereum_vulns_high.meta.json`: it is the EF-bug-bounty-aligned,
network-scale-impact column.

Usage:
    git clone --depth 1 https://github.com/NyxFoundation/ethereum-vuln-dataset /tmp/evd
    python3 tools/vendor-ethtotal-vulns.py --dataset /tmp/evd
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

_ROOT = Path(__file__).resolve().parents[1]

# Value-bearing state surfaces (execution layer): where balances, gas/fee burn,
# and account lifecycle are computed and persisted.
_EL_LABELS = [
    "state-trie",        # account balance / storage persistence
    "transactions",      # value transfer, nonce, sender debit
    "evm",               # CALL/CREATE value semantics
    "opcodes",           # SELFDESTRUCT, CALL-family, balance opcodes
    "gas",               # gas accounting -> fee burn / refunds
    "precompiles",       # value-forwarding precompile paths
    "database",          # state persistence / reorg-time rollback
    "block-processing",  # block-level reward, fee and withdrawal application
]
# Supply-affecting consensus surfaces: issuance and exit of value on the CL
# side. Kept in the criteria because they mint/burn supply even though the
# dataset's critical/high population currently has no rows there — the slice is
# defined by domain, not by what happens to be populated.
_CL_LABELS = [
    "beacon-chain:withdrawal",
    "beacon-chain:deposit",
    "beacon-chain:rewards-and-penalties",
    "beacon-chain:effective-balance-updates",
    "beacon-chain:exit-consolidation",
    "deposit-contract",
]

_COLUMNS = ["id", "severity", "label", "root_cause", "attack_path", "title"]
_TITLE_MAX = 70  # matches data/ethereum_vulns_high.csv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="ethereum-vuln-dataset checkout")
    ap.add_argument("--out", default=str(_ROOT / "data" / "ethtotal_vulns_high.csv"))
    args = ap.parse_args()

    ds = Path(args.dataset)
    src = ds / "data" / "ethereum_vulns.preview.csv"
    rows = list(csv.DictReader(src.open(encoding="utf-8-sig")))
    rev = subprocess.run(["git", "-C", str(ds), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()

    domain = set(_EL_LABELS) | set(_CL_LABELS)
    kept = []
    for i, r in enumerate(rows):
        if r.get("severity_estimated") not in ("Critical", "High"):
            continue
        if r.get("label") not in domain:
            continue
        kept.append({
            # the preview CSV carries no id column; the row index at the pinned
            # revision is the stable, reproducible key (same scheme as
            # data/ethereum_vulns_high.csv's evd-NNN)
            "id": f"evd-p{i:04d}",
            "severity": r["severity_estimated"],
            "label": r["label"],
            "root_cause": r["root_cause"],
            "attack_path": r["attack_path"],
            "title": r["title"][:_TITLE_MAX],
        })

    out = Path(args.out)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        w.writeheader()
        w.writerows(kept)

    from collections import Counter
    by_label = dict(Counter(r["label"] for r in kept).most_common())
    meta = {
        "source": "NyxFoundation/ethereum-vuln-dataset",
        "source_file": "data/ethereum_vulns.preview.csv",
        "source_revision": rev,
        "vendored_by": "tools/vendor-ethtotal-vulns.py",
        "severity_column": "severity_estimated",
        "severity_model": (
            "Ethereum Foundation bug-bounty severity — network-scale impact reachable "
            "REMOTELY by a single message/transaction; see "
            "data/ethereum_vulns_high.meta.json for the full definition. This is the "
            "bounty-aligned column, NOT the advisory/CVSS `severity` column."
        ),
        "filter": {
            "severity_estimated_in": ["Critical", "High"],
            "label_in": _EL_LABELS + _CL_LABELS,
            "note": (
                "STRUCTURAL slice: label membership only, no per-finding prose judgment. "
                "Labels are the value-bearing state surfaces an EthTotal supply/ledger "
                "invariant can be violated through — where balances, gas/fee burn and "
                "account lifecycle are computed and persisted (EL), plus the CL surfaces "
                "that mint or retire supply."
            ),
        },
        "row_count": len(kept),
        "rows_by_label": by_label,
        "columns": _COLUMNS,
        "purpose": (
            "Teaching material for the EthTotal stage-2 generate/improve loop "
            "(tools/run-improve-ethtotal.sh). improve/generate read only the class "
            "fields (severity/label/root_cause); title/attack_path are carried for "
            "traceability but never enter the prompt (speca#143 safeguard)."
        ),
        "not_an_eval_denominator": (
            "This slice is INPUT to self-improvement, never a benchmark the checklist "
            "is scored against — the #88 correction: the checklist is judged on audit "
            "quality against the solodit reference bar, not on reproducing dataset bugs."
        ),
    }
    Path(str(out).replace(".csv", ".meta.json")).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(kept)} rows -> {out}")
    print(f"  by label: {by_label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
