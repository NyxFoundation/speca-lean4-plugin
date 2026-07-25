"""Recursive structural self-improvement for projected 01e properties.

The normal improve loop rewrites text in place. Projected obligations also need
one-to-many refinement: a broad causal obligation must become several atomic
audit checks without losing provenance. Reviewed rules provide that split;
this engine applies them recursively until no child has another rule.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .projection import ProjectionError, match_evidence
from .schema import validate_property

_MUTABLE = {
    "property_id", "text", "assertion", "covers", "label",
    "implementation_surfaces", "engine_methods", "spec_references",
    "dataset_query", "derivation_kind",
}


def load_refinement_rules(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("rules"), list):
        raise ProjectionError("refinement rules must be version 1 with a rules list")
    return data


def refinement_diagnostics(properties: list[dict[str, Any]]) -> dict[str, Any]:
    bundled = []
    wildcard_covers = []
    for prop in properties:
        text = str(prop.get("text", ""))
        assertion = str(prop.get("assertion", ""))
        conjunctions = len(re.findall(r"\band\b", f"{text} {assertion}", re.I))
        if conjunctions > 2:
            bundled.append({
                "property_id": prop["property_id"],
                "conjunctions": conjunctions,
            })
        if "*" in str(prop.get("covers", "")):
            wildcard_covers.append(prop["property_id"])
    return {
        "property_count": len(properties),
        "bundled": bundled,
        "wildcard_covers": wildcard_covers,
        "conditional_scope": [
            p["property_id"] for p in properties
            if p.get("reachability", {}).get("bug_bounty_scope") == "conditional"
        ],
    }


def _rules_by_parent(rules: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for rule in rules["rules"]:
        parent = rule.get("parent_property_id")
        children = rule.get("children")
        if not isinstance(parent, str) or not isinstance(children, list) or not children:
            raise ProjectionError("every refinement rule needs parent_property_id and children")
        if parent in out:
            raise ProjectionError(f"duplicate refinement rule for {parent}")
        out[parent] = children
    return out


def _refine_one(
    parent: dict[str, Any],
    child_spec: dict[str, Any],
    evidence: list[dict[str, str]],
) -> dict[str, Any]:
    unknown = set(child_spec) - _MUTABLE
    if unknown:
        raise ProjectionError(
            f"{parent['property_id']}: refinement attempts immutable fields {sorted(unknown)}"
        )
    child = dict(parent)
    child.update(child_spec)
    if child.get("spec_references"):
        child["spec_reference"] = child["spec_references"][0]
    child["parent_property_id"] = parent["property_id"]
    child["refinement_depth"] = int(parent.get("refinement_depth", 0)) + 1
    child["refinement_history"] = list(parent.get("refinement_history", [])) + [
        parent["property_id"]
    ]
    child["causal_chain"] = list(parent.get("causal_chain", [])) + [{
        "kind": "recursive-refinement",
        "from": parent["property_id"],
        "to": child["property_id"],
    }]
    evidence_obligation = {"dataset_match": child.get("dataset_query", {})}
    child["dataset_evidence"] = match_evidence(evidence_obligation, evidence)
    problems = validate_property(child)
    if problems:
        raise ProjectionError(
            f"{child.get('property_id', '<missing>')}: invalid refined property: {problems}"
        )
    return child


def recursive_refine(
    properties: list[dict[str, Any]],
    rules: dict[str, Any],
    evidence: list[dict[str, str]] | None = None,
    max_rounds: int = 6,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply reviewed one-to-many rules until a fixed point."""
    by_parent = _rules_by_parent(rules)
    evidence = evidence or []
    current = [dict(p) for p in properties]
    rounds = [{
        "round": 0,
        "applied": [],
        "diagnostics": refinement_diagnostics(current),
    }]
    seen_ids = {p["property_id"] for p in current}
    for round_no in range(1, max_rounds + 1):
        changed = False
        applied = []
        next_props: list[dict[str, Any]] = []
        for prop in current:
            children = by_parent.get(prop["property_id"])
            if not children:
                next_props.append(prop)
                continue
            changed = True
            applied.append(prop["property_id"])
            seen_ids.discard(prop["property_id"])
            for child_spec in children:
                child = _refine_one(prop, child_spec, evidence)
                cid = child["property_id"]
                if cid in seen_ids:
                    raise ProjectionError(f"duplicate refined property id: {cid}")
                seen_ids.add(cid)
                next_props.append(child)
        current = next_props
        rounds.append({
            "round": round_no,
            "applied": applied,
            "diagnostics": refinement_diagnostics(current),
        })
        if not changed:
            return current, {
                "converged": True,
                "stop_reason": "fixed_point",
                "rounds": rounds,
            }
    remaining = sorted(p["property_id"] for p in current if p["property_id"] in by_parent)
    return current, {
        "converged": not remaining,
        "stop_reason": "fixed_point" if not remaining else "max_rounds",
        "remaining_rules": remaining,
        "rounds": rounds,
    }
