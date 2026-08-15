#!/usr/bin/env python3
"""Materialize conservative audit packets directly from Lean export data.

This bounded fallback never paraphrases or extends the theorem: the root
conclusion and every project-local theorem/lemma conclusion are copied into
auditable facts. The few-shot wording loop may later improve only text and
assertion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from speca_lean4.frontier import proof_evidence
from speca_lean4.health import load_health


def packet_for(payload: dict) -> dict:
    supporting = [{
        "fact_id": "FACT-ROOT", "source_fact_ids": ["ROOT"],
        "claim": f"Root conclusion: {payload['conclusion']}",
        "check": "Check the exact root relation on every implementation path covered by the property.",
        "expected": payload["conclusion"],
        "flag_if": "The implementation produces any result that violates the exact root relation or its stated preconditions.",
    }]
    obligations = [{
        "obligation_id": "OBS-ROOT",
        "check": "Recompute the root relation from the implementation post-state and compare it exactly with the Lean conclusion.",
        "expected": payload["conclusion"],
        "flag_if": "The relation is weakened, evaluated on different operands/state, or fails on a reachable input.",
        "supports": ["FACT-ROOT"],
    }]
    for fact in payload.get("proof_closure", []):
        fid = fact["fact_id"]
        conclusion = fact.get("conclusion") or fact.get("statement") or "(no pretty-printed conclusion)"
        supporting.append({
            "fact_id": f"FACT-{fid}", "source_fact_ids": [fid],
            "claim": f"Lean closure fact {fid}: {conclusion}",
            "check": f"Check the exact lemma relation represented by {fid} wherever the implementation realizes this transition.",
            "expected": conclusion,
            "flag_if": f"The implementation violates, weakens, or silently drops the relation represented by {fid}.",
        })
        obligations.append({
            "obligation_id": f"OBS-{fid}",
            "check": f"Compare the implementation behavior against the exact conclusion of {fid}.",
            "expected": conclusion,
            "flag_if": f"Any input or state produces a result inconsistent with {fid}.",
            "supports": [f"FACT-{fid}"],
        })
    return {
        "guarantee": f"The implementation must realize the exact Lean root conclusion: {payload['conclusion']}",
        "preconditions": [f"{h['name']}: {h['type']} ({h['class']})" for h in payload.get("must_establish", [])],
        "supporting_facts": supporting,
        "derived_obligations": obligations,
        "derivation": "Conservative transcription of the Lean root and project-local proof closure; no protocol, client, file, function, or exploit semantics are added.",
        "omitted_facts": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="theorem_map_ethtotal.json")
    ap.add_argument("--health-json", default="lean-ethtotal/health.json")
    ap.add_argument("--out", default="data/ethtotal_audit_packets.json")
    args = ap.parse_args()
    health = load_health(args.health_json)
    theorem_map = json.loads(Path(args.map).read_text(encoding="utf-8"))
    packets, seen = [], set()
    for entry in theorem_map.get("properties", []):
        if str(entry.get("property_id", "")).startswith("CHK-"):
            continue
        theorem = entry.get("theorem")
        if not theorem or theorem in seen:
            continue
        seen.add(theorem)
        evidence = proof_evidence(theorem, health)
        if evidence is None:
            raise SystemExit(f"missing Lean evidence for {theorem}")
        encoded = json.dumps(evidence, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        packets.append({
            "theorem": theorem, "audit_packet": packet_for(evidence),
            "x_evidence_id": f"lean-health:{theorem}:{digest[:16]}",
            "x_evidence_sha256": digest, "x_evidence_kind": "live-export",
            "x_lean_obligations": evidence["must_establish"],
            "x_proof_closure": evidence["proof_closure"],
            "x_proof_dependency_stats": evidence["proof_dependency_stats"],
        })
    Path(args.out).write_text(json.dumps({
        "version": "0.1.0", "source": "conservative Lean-export packet materialization",
        "theorem_count": len(packets), "packet_count": len(packets), "packets": packets,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(packets)} conservative theorem packets -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
