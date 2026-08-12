#!/usr/bin/env python3
"""Trim the full EthTotal health export down to the mapped theorems.

`lean-ethtotal/health.json` covers all 3333 theorems (~11 MB) — that is the
point of it, and it is a build artifact, not something to commit. But
`emit-01e` only ever reads the theorems `theorem_map_ethtotal.json` names, so a
trimmed copy is enough to re-emit the `01e` without a Lean toolchain, and small
enough to version.

The trim is a filter and nothing else: records are copied byte-identical, and
the header keeps the same `project`. Anything downstream reads exactly what the
exporter wrote.

Usage:
    python3 tools/ethtotal-trim-health.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--health", default=str(_ROOT / "lean-ethtotal" / "health.json"))
    ap.add_argument("--map", default=str(_ROOT / "theorem_map_ethtotal.json"))
    ap.add_argument("--out", default=str(_ROOT / "lean-ethtotal" / "health.mapped.json"))
    args = ap.parse_args()

    full = json.loads(Path(args.health).read_text(encoding="utf-8"))
    wanted = {e["theorem"] for e in json.loads(Path(args.map).read_text(encoding="utf-8"))["properties"]}
    kept = [t for t in full["theorems"] if t["name"] in wanted]
    missing = wanted - {t["name"] for t in kept}
    if missing:
        print(f"ERROR: mapped theorems absent from the export: {sorted(missing)[:5]}")
        return 1

    out = dict(full)
    out["theorems"] = kept
    out["x_trimmed_from"] = {
        "source": Path(args.health).name,
        "theorems_in_full_export": len(full["theorems"]),
        "theorems_kept": len(kept),
        "criterion": "named by theorem_map_ethtotal.json",
        "tool": "tools/ethtotal-trim-health.py",
    }
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    size = Path(args.out).stat().st_size
    print(f"{len(kept)} of {len(full['theorems'])} records -> {args.out} ({size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
