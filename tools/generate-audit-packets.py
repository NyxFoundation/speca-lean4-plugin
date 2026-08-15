#!/usr/bin/env python3
"""Generate proof-aware audit packets for existing theorem-map properties.

Stage-2 CHK properties already carry packets. This companion step gives the
older theorem-backed properties the same semantic anchor before the global
few-shot wording loop runs. One packet is generated per distinct theorem and
is later shared by all 01e decompositions of that theorem.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from speca_lean4.health import load_health
from speca_lean4.judge import split_cmd, subprocess_llm

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "generate-properties.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_properties", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidates(theorem_map: dict, vulns: list[dict[str, str]]) -> list[dict]:
    prevalence = Counter(
        (v.get("label", ""), v.get("root_cause", ""))
        for v in vulns
        if v.get("severity") in ("Critical", "High")
    )
    by_label: dict[str, str] = {}
    for (label, cause), _ in prevalence.most_common():
        by_label.setdefault(label, cause)

    out: list[dict] = []
    seen: set[str] = set()
    for entry in theorem_map.get("properties", []):
        if str(entry.get("property_id", "")).startswith("CHK-"):
            continue
        theorem = entry.get("theorem")
        if not theorem or theorem in seen:
            continue
        seen.add(theorem)
        label = str(entry.get("label", ""))
        severity = str(entry.get("severity", "MEDIUM")).upper()
        cause = by_label.get(label, "logic_error_invariant_violation")
        out.append({
            "theorem": theorem,
            "label": label,
            "root_cause": cause,
            "severity": "Critical" if severity == "CRITICAL" else "High" if severity == "HIGH" else "Medium",
            "covers_hint": list(entry.get("covers_hint", [])),
            "x_layer": entry.get("x_layer", ""),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=str(ROOT / "theorem_map_ethtotal.json"))
    ap.add_argument("--health-json", default=str(ROOT / "lean-ethtotal" / "health.json"))
    ap.add_argument("--vulns-csv", default=str(ROOT / "data" / "ethtotal_vulns_high.csv"))
    ap.add_argument("--gen-cmd", default="claude -p")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--out", default=str(ROOT / "data" / "ethtotal_audit_packets.json"))
    args = ap.parse_args()

    generator = load_generator()
    theorem_map = json.loads(Path(args.map).read_text(encoding="utf-8"))
    health = load_health(args.health_json)
    with Path(args.vulns_csv).open(encoding="utf-8-sig", newline="") as fh:
        vulns = list(csv.DictReader(fh))
    cands = candidates(theorem_map, vulns)
    print(f"generating one proof-aware packet for {len(cands)} distinct theorem roots")

    gen = subprocess_llm(split_cmd(args.gen_cmd), timeout=args.timeout)

    def run(pair):
        candidate, seq = pair
        return generator._generate_one(
            candidate, seq, health, gen, None, 0.0, skip_judge=True
        )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, zip(cands, range(1, len(cands) + 1))))

    packets = []
    for _seq, record, message in sorted(results):
        print(message)
        if record is not None:
            packets.append({
                "theorem": record["theorem"],
                "audit_packet": record["audit_packet"],
                "x_evidence_id": record.get("x_evidence_id"),
                "x_evidence_sha256": record.get("x_evidence_sha256"),
                "x_evidence_kind": record.get("x_evidence_kind"),
                "x_lean_obligations": record.get("x_lean_obligations", []),
                "x_proof_closure": record.get("x_proof_closure", []),
                "x_proof_dependency_stats": record.get("x_proof_dependency_stats", {}),
            })

    Path(args.out).write_text(json.dumps({
        "version": "0.1.0",
        "source": "proof-aware packet generation for existing 01e roots",
        "theorem_count": len(cands),
        "packet_count": len(packets),
        "packets": packets,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(packets)}/{len(cands)} theorem packets -> {args.out}")
    return 0 if len(packets) == len(cands) else 1


if __name__ == "__main__":
    raise SystemExit(main())
