"""Causal projection from proved Gasper theorems to implementation obligations.

The legacy stage-2 generator paired a theorem label with a prevalent defect
class.  That is useful as brainstorming input, but it does not establish why a
defect can invalidate a theorem assumption.  This module makes that missing
step explicit:

    theorem -> owned model input/precondition -> boundary obligation
            -> implementation surface -> dataset evidence

Candidate selection is deterministic and comes from a reviewed projection map.
An LLM may later improve ``text``/``assertion``; it never decides applicability.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .health import TheoremHealth, health_for
from .mapping import build_property, derive_severities
from .schema import validate_property


class ProjectionError(ValueError):
    """A projection map or generated property violates the causal contract."""


def load_projection_map(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ProjectionError("projection map version must be 1")
    if not isinstance(data.get("obligations"), list):
        raise ProjectionError("projection map must contain an obligations list")
    return data


def load_evidence(path: str | Path | None) -> list[dict[str, str]]:
    if not path:
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _matches(value: str, allowed: list[str]) -> bool:
    return not allowed or value in allowed


def match_evidence(
    obligation: dict[str, Any],
    rows: list[dict[str, str]],
    limit: int = 8,
) -> list[dict[str, str]]:
    """Match evidence only after an obligation has been selected causally.

    Matching is an intersection over the configured dimensions, not the legacy
    "most prevalent label wins" candidate-selection heuristic.
    """
    query = obligation.get("dataset_match", {})
    fields = {
        "label": list(query.get("labels", [])),
        "root_cause": list(query.get("root_causes", [])),
        "attack_path": list(query.get("attack_paths", [])),
        "source_platform": list(query.get("source_platforms", [])),
    }
    matched = [
        row for row in rows
        if all(_matches(str(row.get(field, "")), allowed)
               for field, allowed in fields.items())
    ]
    severity_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3,
                     "Info": 4, "Unrated": 5}
    matched.sort(key=lambda r: (
        severity_rank.get(str(r.get("severity", "")), 9),
        str(r.get("id", "")),
    ))
    keep = ("id", "source_platform", "severity", "label", "root_cause",
            "attack_path", "fix_commit", "introduced_in_commit",
            "source_url", "files_changed")
    return [
        {key: row[key] for key in keep if row.get(key)}
        for row in matched[:limit]
    ]


def _parent_status(
    health: dict[str, TheoremHealth], theorem_names: list[str], bridge_status: str
) -> str:
    statuses = [health_for(health, theorem).lean_status for theorem in theorem_names]
    parent = "proved" if statuses and all(x == "proved" for x in statuses) else "unknown"
    if bridge_status == "not-required":
        return f"descends-from-{parent}"
    if bridge_status == "proved":
        return f"descends-from-{parent}-via-proved-bridge"
    return f"descends-from-{parent}-via-unproved-bridge"


def _entry_index(theorem_map: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Choose the abstract entry as metadata source, not a hand-written CHK."""
    out: dict[str, dict[str, Any]] = {}
    for entry in theorem_map.get("properties", []):
        theorem = entry.get("theorem")
        if not theorem:
            continue
        if theorem not in out or out[theorem].get("lowering") == "verbatim":
            out[theorem] = entry
    return out


def _scope_mentions(scope: dict[str, Any], token: str) -> bool:
    def strings(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [s for v in value.values() for s in strings(v)]
        if isinstance(value, list):
            return [s for v in value for s in strings(v)]
        return []

    return token.lower() in " ".join(strings(scope)).lower()


def _apply_projection_scope(base: dict[str, Any], target_layer: str) -> None:
    """Do not inherit CL scope/references when projecting onto the EL."""
    scope = base.pop("_projection_scope", {})
    if target_layer != "el":
        return
    # The caller's scope may be a CL-only audit scope. EL findings cannot be
    # labelled in-scope merely because their source theorem is in scope.
    in_scope = _scope_mentions(scope, "execution")
    reach = dict(base["reachability"])
    reach["classification"] = "external-reachable"
    reach["entry_points"] = ["CallbackHandler"]
    reach["attacker_controlled"] = True
    reach["bug_bounty_scope"] = "in-scope" if in_scope else "conditional"
    base["reachability"] = reach
    base["bug_bounty_eligible"] = in_scope
    base["exploitability"] = "external-attack"


def _validate_obligation(
    obligation: dict[str, Any], entries: dict[str, dict[str, Any]]
) -> None:
    required = {
        "obligation_id", "target_layer", "source_theorems", "owned_inputs",
        "causal_rationale", "text", "assertion", "covers", "severity",
        "bridge_status", "spec_references",
    }
    missing = sorted(required - set(obligation))
    if missing:
        raise ProjectionError(
            f"{obligation.get('obligation_id', '<unknown>')}: missing {missing}"
        )
    if obligation["target_layer"] not in {"cl", "el"}:
        raise ProjectionError(f"{obligation['obligation_id']}: invalid target_layer")
    if obligation["bridge_status"] not in {
        "not-required", "specified-unproved", "proved"
    }:
        raise ProjectionError(f"{obligation['obligation_id']}: invalid bridge_status")
    unknown = [t for t in obligation["source_theorems"] if t not in entries]
    if unknown:
        raise ProjectionError(
            f"{obligation['obligation_id']}: unknown source theorem(s): {unknown}"
        )
    if not obligation["owned_inputs"]:
        raise ProjectionError(
            f"{obligation['obligation_id']}: owned_inputs must be non-empty"
        )
    if not obligation["spec_references"]:
        raise ProjectionError(
            f"{obligation['obligation_id']}: spec_references must be non-empty"
        )


def build_projected_properties(
    theorem_map: dict[str, Any],
    health: dict[str, TheoremHealth],
    scope: dict[str, Any],
    projection_map: dict[str, Any],
    target_layer: str,
    evidence: list[dict[str, str]] | None = None,
    gasper_ref: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build causal CL or EL 01e properties and an applicability report."""
    if target_layer not in {"cl", "el"}:
        raise ProjectionError("target_layer must be 'cl' or 'el'")

    entries = _entry_index(theorem_map)
    source = theorem_map.get("gasper_source", "NyxFoundation/gasper-lean4")
    ref = gasper_ref or theorem_map.get("gasper_ref", "main")
    severities = derive_severities(theorem_map.get("properties", []), health)
    obligations = [
        item for item in projection_map["obligations"]
        if item.get("target_layer") == target_layer
    ]
    evidence = evidence or []
    properties: list[dict[str, Any]] = []
    covered: dict[str, list[str]] = defaultdict(list)

    for obligation in obligations:
        _validate_obligation(obligation, entries)
        theorem_names = list(obligation["source_theorems"])
        primary = theorem_names[0]
        base = build_property(
            entries[primary], health, scope, None, source, ref,
            severities.get(primary),
        ).to_dict()
        property_id = obligation["obligation_id"]
        base.update({
            "property_id": property_id,
            "text": obligation["text"],
            "assertion": obligation["assertion"],
            "severity": str(obligation["severity"]).upper(),
            "covers": obligation["covers"],
            "lean_status": _parent_status(
                health, theorem_names, obligation["bridge_status"]
            ),
            "target_layer": target_layer,
            "source_theorems": theorem_names,
            "owned_inputs": list(obligation["owned_inputs"]),
            "causal_chain": [
                {"kind": "lean-theorem", "refs": theorem_names},
                {"kind": "owned-input", "refs": list(obligation["owned_inputs"])},
                {
                    "kind": "bridge-obligation",
                    "ref": property_id,
                    "status": obligation["bridge_status"],
                },
                {
                    "kind": "implementation-surface",
                    "refs": list(obligation.get("implementation_surfaces", [])),
                },
            ],
            "causal_rationale": obligation["causal_rationale"],
            "bridge_status": obligation["bridge_status"],
            "spec_references": list(obligation["spec_references"]),
            "implementation_surfaces": list(
                obligation.get("implementation_surfaces", [])
            ),
            "engine_methods": list(obligation.get("engine_methods", [])),
            "dataset_query": dict(obligation.get("dataset_match", {})),
            "dataset_evidence": match_evidence(obligation, evidence),
        })
        base["_projection_scope"] = scope
        _apply_projection_scope(base, target_layer)
        base["spec_reference"] = obligation["spec_references"][0]
        # The primary theorem's single label is not a valid layer-crossing
        # anchor.  The projection map owns this field explicitly.
        if obligation.get("label"):
            base["label"] = obligation["label"]
        if obligation.get("liveness_only"):
            base["bug_bounty_eligible"] = False
        problems = validate_property(base)
        if problems:
            raise ProjectionError(f"{property_id}: invalid 01e property: {problems}")
        properties.append(base)
        for theorem in theorem_names:
            covered[theorem].append(property_id)

    exclusions = projection_map.get("not_applicable", {}).get(target_layer, {})
    all_theorems = sorted(entries)
    unclassified = [
        theorem for theorem in all_theorems
        if theorem not in covered and theorem not in exclusions
    ]
    stale_exclusions = sorted(set(exclusions) - set(all_theorems))
    report = {
        "target_layer": target_layer,
        "theorem_count": len(all_theorems),
        "property_count": len(properties),
        "applicable": dict(sorted(covered.items())),
        "not_applicable": [
            {"theorem": theorem, "reason": exclusions[theorem]}
            for theorem in sorted(exclusions)
            if theorem in entries
        ],
        "unclassified": unclassified,
        "stale_exclusions": stale_exclusions,
    }
    return properties, report
