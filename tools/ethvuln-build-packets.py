#!/usr/bin/env python3
"""Enrich theorem_map_ethvuln.json with deterministic audit packets and
per-entry spec anchors (PR #24 review).

Unlike the EthTotal packet pipeline (tools/generate-audit-packets.py, an
LLM-assisted wording loop over proof closures), the ethvuln packets are
built DETERMINISTICALLY from the exporter's health JSON: the guarantee is
the exact pretty-printed Lean conclusion, the preconditions are the exact
hypothesis types with their A2 classes, and the single supporting fact is
the root conclusion. Nothing is worded by a model, so re-running the tool
on the same health JSON is idempotent byte-for-byte.

Spec anchors come from a curation file (one row per property_id):
  { "entries": { "<property_id>": {
        "anchor": "consensus-specs:specs/..." | "execution-specs:src/..." | "N/A",
        "spec_symbol": "<symbol or null>",
        "category": "...",   # N/A only
        "reason": "..."      # N/A only
  } } }
Every entry must be covered; N/A is explicit, never silent (the reviewer's
policy: protocol-semantics entries carry a consensus-/execution-specs
section or symbol; out-of-spec surfaces are marked N/A and treated as
implementation safety).

Usage:
  python3 tools/ethvuln-build-packets.py \
      --map theorem_map_ethvuln.json \
      --health tests/fixtures/theorem_health.ethvuln.sample.json \
      --anchors data/ethvuln_spec_anchors.json [--out theorem_map_ethvuln.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_ANCHOR_PREFIXES = ("consensus-specs:specs/", "execution-specs:src/ethereum/")


def build_packet(th: dict) -> dict:
    hyps = th.get("hypotheses", [])
    pres: list[str] = []
    obligations: list[dict] = []
    for h in hyps:
        cls = h.get("class")
        if cls == "must-establish":
            pres.append(f"{h.get('name', '?')}: {h.get('type', '')} (must-establish)")
            obligations.append(h)
        elif cls == "context-precondition":
            pres.append(f"{h.get('type', '')} (context-precondition)")
    conclusion = th.get("conclusion") or th.get("statement") or ""
    facts: list[dict] = [
        {
            "fact_id": "FACT-ROOT",
            "source_fact_ids": ["ROOT"],
            "claim": f"Root conclusion: {conclusion}",
            "check": (
                "Check the exact root relation on every implementation "
                "path covered by the property."
            ),
            "expected": conclusion,
            "flag_if": (
                "The implementation produces any result that violates the "
                "exact root relation or its stated preconditions."
            ),
        }
    ]
    # One exact audit assertion per implementation obligation: this is the
    # three-way separation the PR #24 review asked for -- the guarantee (the
    # root conclusion), its preconditions (typed, class-tagged), and an exact
    # per-obligation assertion an auditor can carry into 02c.
    for i, h in enumerate(obligations, 1):
        facts.append(
            {
                "fact_id": f"FACT-OB{i}",
                "source_fact_ids": [h.get("name", "?")],
                "claim": (
                    f"Implementation obligation {h.get('name', '?')}: "
                    f"{h.get('type', '')}"
                ),
                "check": (
                    "Establish this obligation in the implementation; it is "
                    "the must-establish precondition under which the root "
                    "guarantee transfers."
                ),
                "expected": h.get("type", ""),
                "flag_if": (
                    "The implementation cannot be shown to establish this "
                    "obligation on the audited path."
                ),
            }
        )
    return {
        "guarantee": (
            "The implementation must realize the exact Lean root conclusion: "
            f"{conclusion}"
        ),
        # The three-way separation the PR #24 review asked for, explicit:
        # `obligations` = what the implementation must establish
        # (must-establish, one entry per named hypothesis, exact Lean type);
        # `preconditions` = the full class-tagged hypothesis list in the
        # EthTotal-compatible rendering (obligations plus any
        # context-precondition guards, which condition WHEN the guarantee
        # applies and are never obligations).
        "obligations": [
            {"name": h.get("name", "?"), "type": h.get("type", "")}
            for h in obligations
        ],
        "preconditions": pres,
        "supporting_facts": facts,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--health", required=True, type=Path)
    ap.add_argument("--anchors", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    m = json.loads(args.map.read_text(encoding="utf-8"))
    health = json.loads(args.health.read_text(encoding="utf-8"))
    theorems = {t["name"]: t for t in health["theorems"]}
    anchors = (
        json.loads(args.anchors.read_text(encoding="utf-8"))["entries"]
        if args.anchors
        else {}
    )

    missing_health: list[str] = []
    for entry in m["properties"]:
        th = theorems.get(entry["theorem"])
        if th is None or not th.get("resolved"):
            missing_health.append(entry["property_id"])
            continue
        entry["audit_packet"] = build_packet(th)
        if anchors:
            row = anchors.get(entry["property_id"])
            if row is None:
                raise SystemExit(f"no anchor curation for {entry['property_id']}")
            anchor = row["anchor"]
            if anchor == "N/A":
                entry["x_spec_anchor"] = (
                    f"N/A — {row.get('category', 'out-of-spec')}: "
                    f"{row.get('reason', '')}".rstrip(": ")
                )
            else:
                if not anchor.startswith(_ANCHOR_PREFIXES):
                    raise SystemExit(f"malformed anchor for {entry['property_id']}: {anchor}")
                entry["x_spec_anchor"] = anchor
                if row.get("spec_symbol"):
                    entry["x_spec_symbol"] = row["spec_symbol"]

    if missing_health:
        raise SystemExit(f"unresolved theorems in health: {missing_health}")

    out = args.out or args.map
    out.write_text(
        json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    n_anchored = sum(
        1
        for e in m["properties"]
        if str(e.get("x_spec_anchor", "")).startswith(_ANCHOR_PREFIXES)
    )
    print(
        f"packets: {len(m['properties'])} entries; "
        f"spec anchors: {n_anchored} anchored, "
        f"{len(m['properties']) - n_anchored} N/A"
    )


if __name__ == "__main__":
    main()
