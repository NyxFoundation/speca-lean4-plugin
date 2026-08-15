#!/usr/bin/env python3
"""Deterministically validate every packet against the live Lean evidence."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from speca_lean4.health import load_health

ROOT = Path(__file__).resolve().parents[1]


def load_generator():
    path = ROOT / "tools" / "generate-properties.py"
    spec = importlib.util.spec_from_file_location("generate_properties", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--health-json", default="lean-ethtotal/health.json")
    ap.add_argument("--map", default="theorem_map_ethtotal.json")
    args = ap.parse_args()
    generator = load_generator()
    health = load_health(args.health_json)
    short = {}
    for name in health:
        short.setdefault(name.rsplit(".", 1)[-1], []).append(name)
    doc = json.loads(Path(args.input).read_text(encoding="utf-8"))
    map_doc = json.loads(Path(args.map).read_text(encoding="utf-8"))
    theorem_by_id = {p.get("property_id"): p.get("theorem") for p in map_doc.get("properties", [])}
    kept = []
    errors = []
    for prop in doc.get("properties", []):
        thm = prop.get("theorem") or theorem_by_id.get(prop.get("property_id"))
        if not thm:
            leaf = str(prop.get("lean_artifact", "")).split("#")[-1]
            matches = short.get(leaf, [])
            thm = matches[0] if len(matches) == 1 else None
        if not thm:
            errors.append(f"{prop.get('property_id')}: cannot resolve theorem")
            continue
        evidence = generator.evidence_for({"theorem": thm}, health)
        if evidence is None:
            errors.append(f"{prop.get('property_id')}: missing Lean evidence")
            continue
        _packet, reason = generator.validate_audit_packet(prop.get("audit_packet"), evidence)
        if _packet is None:
            errors.append(f"{prop.get('property_id')}: {reason}")
            continue
        out = dict(prop)
        out.setdefault("x_fidelity_verdict", "deterministic-validated")
        out.setdefault("x_fidelity_reason", "packet structure, closure coverage, and evidence hash validated deterministically")
        out.setdefault("x_fidelity_model", "deterministic closure validator")
        kept.append(out)
    if errors:
        for error in errors:
            print(error)
        return 1
    out_doc = {k: v for k, v in doc.items() if k != "properties"}
    out_doc["x_fidelity_review"] = {
        "model_command": "deterministic closure validator",
        "health_source": args.health_json,
        "input_count": len(doc.get("properties", [])),
        "output_count": len(kept),
        "faithful_or_repaired": len(kept),
    }
    out_doc["properties"] = kept
    Path(args.out).write_text(json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"validated {len(kept)}/{len(doc.get('properties', []))} packets -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
