#!/usr/bin/env python3
"""Persist a closure-aware fidelity review into a generated property map.

Unlike ``apply-improved.py`` (which intentionally changes only the quality
surface), this command persists the semantic ``audit_packet`` and its proof
closure after the dedicated fidelity gate has repaired them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELDS = (
    "text", "assertion", "audit_packet", "x_evidence_id",
    "x_evidence_sha256", "x_evidence_kind", "x_lean_obligations",
    "x_proof_closure", "x_proof_dependency_stats", "x_fidelity_verdict",
    "x_fidelity_reason", "x_fidelity_model",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("reviewed", help="closure-aware fidelity output JSON")
    ap.add_argument("--map", default="data/ethtotal_generated_properties.json")
    args = ap.parse_args()

    reviewed_doc = json.loads(Path(args.reviewed).read_text(encoding="utf-8"))
    reviewed = {
        str(p["property_id"]): p for p in reviewed_doc.get("properties", [])
    }
    map_path = Path(args.map)
    raw = map_path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    changed: list[str] = []
    missing: list[str] = []
    for entry in doc.get("properties", []):
        pid = str(entry.get("property_id", ""))
        prop = reviewed.get(pid)
        if prop is None:
            continue
        for field in FIELDS:
            if field in prop and prop[field] != entry.get(field):
                entry[field] = prop[field]
                if pid not in changed:
                    changed.append(pid)
    for pid in reviewed:
        if not any(str(e.get("property_id", "")) == pid for e in doc.get("properties", [])):
            missing.append(pid)
    if missing:
        raise SystemExit("reviewed properties absent from map: " + ", ".join(sorted(missing)))
    map_path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else ""),
        encoding="utf-8",
    )
    print(f"applied fidelity fields to {len(changed)} properties in {map_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
