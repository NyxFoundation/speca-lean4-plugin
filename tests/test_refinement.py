"""Recursive projection refinement tests."""

from __future__ import annotations

import json
from pathlib import Path

from speca_lean4.health import index_health
from speca_lean4.projection import (
    build_projected_properties,
    load_evidence,
    load_projection_map,
)
from speca_lean4.refinement import (
    load_refinement_rules,
    recursive_refine,
    refinement_diagnostics,
)
from speca_lean4.schema import validate_property

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"


def _projected():
    theorem_map = json.loads((_ROOT / "theorem_map.json").read_text())
    health = index_health(json.loads(
        (_FIX / "theorem_health.sample.json").read_text()
    ))
    scope = json.loads((_FIX / "bug_bounty_scope.sample.json").read_text())
    pmap = load_projection_map(_ROOT / "data" / "projection_map.json")
    evidence = load_evidence(_ROOT / "data" / "ethereum_vulns_high.csv")
    props = []
    for layer in ("cl", "el"):
        part, _ = build_projected_properties(
            theorem_map, health, scope, pmap, layer, evidence
        )
        props.extend(part)
    return props, evidence


def test_recursive_refinement_reaches_fixed_point():
    props, evidence = _projected()
    rules = load_refinement_rules(_ROOT / "data" / "projection_refinements.json")
    refined, report = recursive_refine(props, rules, evidence)
    assert report["converged"] is True
    assert report["stop_reason"] == "fixed_point"
    assert len(refined) == 30
    assert len({p["property_id"] for p in refined}) == 30
    assert {p["refinement_depth"] for p in refined} == {1, 2}
    assert all(not p["property_id"].startswith("CL-GASPER-FIN-001") for p in refined)
    grandchildren = [
        p for p in refined
        if p["property_id"].startswith("EL-GASPER-LIVE-")
        and p["property_id"] != "EL-GASPER-LIVE-CANONICAL-001"
    ]
    assert len(grandchildren) == 3
    assert all(p["refinement_depth"] == 2 for p in grandchildren)


def test_refinement_preserves_causal_and_proof_provenance():
    props, evidence = _projected()
    rules = load_refinement_rules(_ROOT / "data" / "projection_refinements.json")
    refined, _ = recursive_refine(props, rules, evidence)
    for prop in refined:
        assert validate_property(prop) == []
        assert prop["source_theorems"]
        assert prop["owned_inputs"]
        assert prop["parent_property_id"]
        assert prop["refinement_history"][-1] == prop["parent_property_id"]
        assert len(prop["refinement_history"]) == prop["refinement_depth"]
        assert prop["causal_chain"][-1]["kind"] == "recursive-refinement"
        if prop["target_layer"] == "el":
            assert prop["lean_status"].endswith("via-unproved-bridge")
            assert prop["reachability"]["bug_bounty_scope"] == "conditional"
            assert prop["bug_bounty_eligible"] is False


def test_refinement_reduces_bundling_and_wildcards():
    props, evidence = _projected()
    before = refinement_diagnostics(props)
    rules = load_refinement_rules(_ROOT / "data" / "projection_refinements.json")
    refined, _ = recursive_refine(props, rules, evidence)
    after = refinement_diagnostics(refined)
    assert len(after["bundled"]) < len(before["bundled"])
    assert not after["bundled"]
    assert not after["wildcard_covers"]


def test_refine_cli(tmp_path):
    from speca_lean4.cli import main

    props, _ = _projected()
    source = tmp_path / "projected.json"
    source.write_text(json.dumps({"phase": "01e", "properties": props}))
    out = tmp_path / "refined.json"
    assert main([
        "refine-projected-01e",
        "--input", str(source),
        "--out", str(out),
    ]) == 0
    doc = json.loads(out.read_text())
    assert len(doc["properties"]) == 30
    assert doc["projection_refinement"]["converged"] is True
