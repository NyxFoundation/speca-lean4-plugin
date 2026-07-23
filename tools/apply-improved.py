#!/usr/bin/env python3
"""Apply an improve-loop proposal back into theorem_map.json (speca#88/#143).

The improve loop writes improved_01e.json as a *proposal*; this persists the
sharpened `text`/`assertion` of each CHK-* entry into theorem_map.json so the
git diff of that file is the human-reviewable before/after record. Only those
two string fields are touched — theorem, label, severity, provenance and every
other field are left byte-identical. theorem_map.json round-trips exactly at
json.dumps(indent=2, ensure_ascii=False), so the diff is the changed values
only.

Usage: uv run python tools/apply-improved.py <improved_01e.json> [--map theorem_map.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("improved", help="improved_01e.json from the improve loop")
    ap.add_argument("--map", default=str(_ROOT / "theorem_map.json"))
    args = ap.parse_args()

    improved = {
        p["property_id"]: p
        for p in json.loads(Path(args.improved).read_text(encoding="utf-8"))["properties"]
        if str(p.get("property_id", "")).startswith("CHK-")
    }
    map_path = Path(args.map)
    raw = map_path.read_text(encoding="utf-8")
    doc = json.loads(raw)

    changed = []
    for entry in doc.get("properties", []):
        pid = entry.get("property_id", "")
        prop = improved.get(pid)
        if not prop:
            continue
        for field in ("text", "assertion"):
            new = prop.get(field)
            if new is not None and new != entry.get(field):
                entry[field] = new
                if pid not in changed:
                    changed.append(pid)

    out = json.dumps(doc, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")
    map_path.write_text(out, encoding="utf-8")
    print(f"applied {len(changed)} improved CHK entries: {', '.join(changed) or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
