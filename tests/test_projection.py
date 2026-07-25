"""Causal CL/EL projection tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speca_lean4.health import index_health
from speca_lean4.projection import (
    ProjectionError,
    build_projected_properties,
    load_evidence,
    load_projection_map,
    match_evidence,
)
from speca_lean4.schema import validate_property

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def theorem_map() -> dict:
    return json.loads((_ROOT / "theorem_map.json").read_text(encoding="utf-8"))


@pytest.fixture
def projection_map() -> dict:
    return load_projection_map(_ROOT / "data" / "projection_map.json")


@pytest.fixture
def health() -> dict:
    data = json.loads(
        (_FIX / "theorem_health.sample.json").read_text(encoding="utf-8")
    )
    return index_health(data)


@pytest.fixture
def scope() -> dict:
    return json.loads(
        (_FIX / "bug_bounty_scope.sample.json").read_text(encoding="utf-8")
    )


def test_projection_map_classifies_every_theorem(
    theorem_map, projection_map, health, scope
):
    for layer in ("cl", "el"):
        props, report = build_projected_properties(
            theorem_map, health, scope, projection_map, layer
        )
        assert props
        assert report["unclassified"] == []
        assert report["stale_exclusions"] == []


def test_projected_properties_are_schema_valid(
    theorem_map, projection_map, health, scope
):
    ids: list[str] = []
    for layer in ("cl", "el"):
        props, _ = build_projected_properties(
            theorem_map, health, scope, projection_map, layer
        )
        for prop in props:
            assert validate_property(prop) == []
            assert prop["target_layer"] == layer
            assert prop["source_theorems"]
            assert prop["owned_inputs"]
            assert len(prop["causal_chain"]) == 4
            assert prop["spec_references"]
            ids.append(prop["property_id"])
    assert len(ids) == len(set(ids))


def test_cl_and_el_proof_status_are_honest(
    theorem_map, projection_map, health, scope
):
    cl, _ = build_projected_properties(
        theorem_map, health, scope, projection_map, "cl"
    )
    el, _ = build_projected_properties(
        theorem_map, health, scope, projection_map, "el"
    )
    assert {p["lean_status"] for p in cl} == {"descends-from-proved"}
    assert {p["lean_status"] for p in el} == {
        "descends-from-proved-via-unproved-bridge"
    }
    assert {p["bridge_status"] for p in cl} == {"not-required"}
    assert {p["bridge_status"] for p in el} == {"specified-unproved"}


def test_missing_health_never_upgrades_projection(
    theorem_map, projection_map, scope
):
    cl, _ = build_projected_properties(
        theorem_map, {}, scope, projection_map, "cl"
    )
    el, _ = build_projected_properties(
        theorem_map, {}, scope, projection_map, "el"
    )
    assert {p["lean_status"] for p in cl} == {"descends-from-unknown"}
    assert {p["lean_status"] for p in el} == {
        "descends-from-unknown-via-unproved-bridge"
    }


def test_evidence_is_intersection_not_prevalence():
    obligation = {
        "dataset_match": {
            "labels": ["engine-api"],
            "root_causes": ["consensus_divergence"],
            "attack_paths": ["malformed_input"],
        }
    }
    rows = [
        {
            "id": "keep",
            "severity": "High",
            "label": "engine-api",
            "root_cause": "consensus_divergence",
            "attack_path": "malformed_input",
        },
        {
            "id": "wrong-label",
            "severity": "Critical",
            "label": "gas",
            "root_cause": "consensus_divergence",
            "attack_path": "malformed_input",
        },
        {
            "id": "wrong-cause",
            "severity": "Critical",
            "label": "engine-api",
            "root_cause": "resource_exhaustion",
            "attack_path": "malformed_input",
        },
    ]
    assert [x["id"] for x in match_evidence(obligation, rows)] == ["keep"]


def test_vendored_evidence_attaches_after_projection(
    theorem_map, projection_map, health, scope
):
    evidence = load_evidence(_ROOT / "data" / "ethereum_vulns_high.csv")
    props, _ = build_projected_properties(
        theorem_map, health, scope, projection_map, "el", evidence
    )
    by_id = {p["property_id"]: p for p in props}
    assert by_id["EL-GASPER-FCU-001"]["dataset_query"]["labels"]
    assert by_id["EL-GASPER-FCU-001"]["dataset_evidence"]


def test_unknown_theorem_in_projection_map_is_rejected(
    theorem_map, projection_map, health, scope
):
    doctored = json.loads(json.dumps(projection_map))
    doctored["obligations"][0]["source_theorems"].append("Missing.theorem")
    with pytest.raises(ProjectionError, match="unknown source theorem"):
        build_projected_properties(
            theorem_map, health, scope, doctored, "cl"
        )


def test_projected_cli_emits_both_layers(tmp_path):
    from speca_lean4.cli import main

    out = tmp_path / "01e_projected.json"
    rc = main([
        "emit-projected-01e",
        "--scope", str(_FIX / "bug_bounty_scope.sample.json"),
        "--health-json", str(_FIX / "theorem_health.sample.json"),
        "--target-layer", "both",
        "--out", str(out),
    ])
    assert rc == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["projection"] == "gasper-causal"
    assert {p["target_layer"] for p in doc["properties"]} == {"cl", "el"}
    assert all(
        not report["unclassified"]
        for report in doc["projection_report"].values()
    )
