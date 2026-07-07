"""Unit tests for the theorem -> 01e mapping (Stage C). No Lean toolchain needed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speca_lean4 import build_properties, validate_property
from speca_lean4.health import index_health, status_for

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def theorem_map() -> dict:
    return json.loads((_ROOT / "theorem_map.json").read_text(encoding="utf-8"))


@pytest.fixture
def health() -> dict:
    return index_health(json.loads((_FIX / "theorem_health.sample.json").read_text(encoding="utf-8")))


@pytest.fixture
def scope() -> dict:
    return json.loads((_FIX / "bug_bounty_scope.sample.json").read_text(encoding="utf-8"))


def test_every_property_is_schema_valid(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    assert props, "expected non-empty property list"
    for p in props:
        problems = validate_property(p)
        assert not problems, f"{p['property_id']} invalid: {problems}"


def test_property_ids_unique(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    ids = [p["property_id"] for p in props]
    assert len(ids) == len(set(ids))


def test_lean_status_copied_from_health(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    for p in props:
        assert p["lean_status"] == "proved"


def test_unresolved_theorem_is_unknown_not_dropped(theorem_map, scope):
    # empty health -> every property must still appear, marked unknown (honest)
    props = build_properties(theorem_map, {}, scope)
    assert len(props) == len(theorem_map["properties"])
    assert all(p["lean_status"] == "unknown" for p in props)


def test_liveness_property_not_bug_bounty_eligible(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    by_id = {p["property_id"]: p for p in props}
    liveness = by_id["PROP-lean-liveness-001"]
    assert liveness["bug_bounty_eligible"] is False
    assert liveness["reachability"]["bug_bounty_scope"] in ("in-scope", "out-of-scope", "conditional")


def test_slashing_property_in_scope_and_eligible(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    by_id = {p["property_id"]: p for p in props}
    s1 = by_id["PROP-lean-slashing-001"]
    assert s1["reachability"]["bug_bounty_scope"] == "in-scope"  # scope mentions consensus/slashing
    assert s1["bug_bounty_eligible"] is True
    assert s1["reachability"]["attacker_controlled"] is True


def test_empty_scope_yields_conditional(theorem_map, health):
    props = build_properties(theorem_map, health, {})
    for p in props:
        assert p["reachability"]["bug_bounty_scope"] == "conditional"
        assert p["bug_bounty_eligible"] is False


def test_benchmark_vocabulary_conformance(theorem_map, health, scope):
    """Every emitted core-field value must use the bench-rq2a-20260508-speca vocabulary."""
    from speca_lean4.schema import (
        BENCHMARK_TYPE, CLASSIFICATIONS, ENTRY_POINTS, EXPLOITABILITIES, SEVERITIES,
    )
    props = build_properties(theorem_map, health, scope)
    for p in props:
        assert p["type"] == BENCHMARK_TYPE
        assert p["severity"] in SEVERITIES and p["severity"] == p["severity"].upper()
        assert p["exploitability"] in EXPLOITABILITIES
        assert p["reachability"]["classification"] in CLASSIFICATIONS
        assert p["reachability"]["entry_points"], p["property_id"]
        for ep in p["reachability"]["entry_points"]:
            assert ep in ENTRY_POINTS


def test_assertion_granularity_matches_benchmark(theorem_map, health, scope):
    """Benchmark assertions are 94 +/- 15 chars; stay within a generous 2-sigma-ish band
    so one theorem never lowers into a multi-invariant blob (impl plan section 4)."""
    props = build_properties(theorem_map, health, scope)
    for p in props:
        assert 40 <= len(p["assertion"]) <= 160, (p["property_id"], len(p["assertion"]))
        assert 40 <= len(p["text"]) <= 200, (p["property_id"], len(p["text"]))


def test_k_safety_pilot_property(theorem_map, health, scope):
    """M1 pilot: the k-generalized accountable-safety theorem is mapped and proved."""
    props = build_properties(theorem_map, health, scope)
    by_id = {p["property_id"]: p for p in props}
    k = by_id["PROP-lean-safety-002"]
    assert k["lean_status"] == "proved"
    assert k["severity"] == "CRITICAL"
    assert k["lean_artifact"].endswith("#k_accountable_safety_witnessB")
    assert "GasperBeaconChain/Executable/AccountableSafety.lean" in k["lean_artifact"]


def test_lean_artifact_points_at_source(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    s1 = next(p for p in props if p["property_id"] == "PROP-lean-slashing-001")
    assert "gasper-lean4" in s1["lean_artifact"]
    assert s1["lean_artifact"].endswith("#slashed_double_vote_iff_bex")
    assert "GasperBeaconChain/Executable/Slashing.lean" in s1["lean_artifact"]


def test_covers_resolves_against_subgraphs(theorem_map, health, scope):
    subgraphs = [{"elements": [{"id": "FN-042", "label": "process_attestation handler"}]}]
    props = build_properties(theorem_map, health, scope, subgraphs)
    s1 = next(p for p in props if p["property_id"] == "PROP-lean-slashing-001")
    assert s1["covers"] == "FN-042"


def test_status_for_defaults_unknown():
    assert status_for({}, "no.such.theorem") == ("unknown", "")
