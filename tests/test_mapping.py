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
    # empty health -> every entry must still appear (1:1, undecomposed), marked
    # unknown (honest)
    props = build_properties(theorem_map, {}, scope)
    assert len(props) == len(theorem_map["properties"])
    assert all(p["lean_status"] == "unknown" for p in props)


def _by_base(props: list[dict], base_id: str) -> list[dict]:
    """All properties lowered from one theorem_map entry (base id or -me<i>)."""
    return [
        p for p in props
        if p["property_id"] == base_id or p["property_id"].startswith(base_id + "-me")
    ]


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
    """Benchmark assertions are 94 +/- 15 chars. The decomposed (B1/B2) form
    carries one precondition + a capped conclusion, so its band is wider but
    bounded; the guard is against lowering one theorem into an unbounded blob."""
    props = build_properties(theorem_map, health, scope)
    for p in props:
        if "-me" in p["property_id"] or "guarantees [" in p["assertion"]:
            assert 30 <= len(p["assertion"]) <= 600, (p["property_id"], len(p["assertion"]))
        else:
            # unenriched 1:1 fallback keeps the hand-calibrated theorem_map assertion
            assert 30 <= len(p["assertion"]) <= 160, (p["property_id"], len(p["assertion"]))
        assert 40 <= len(p["text"]) <= 260, (p["property_id"], len(p["text"]))


def test_k_safety_pilot_property(theorem_map, health, scope):
    """M1 pilot: the k-generalized accountable-safety theorem is mapped and proved."""
    props = build_properties(theorem_map, health, scope)
    ks = _by_base(props, "PROP-lean-safety-002")
    assert ks, "k_accountable_safety_witnessB lowered to no properties"
    for k in ks:
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


def test_enriched_health_populates_lean_fields(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    ks = _by_base(props, "PROP-lean-safety-core-001")
    assert ks
    for k in ks:
        assert k.get("lean_statement") is not None
        assert "k_finalized" in k["lean_statement"]
        assert k.get("lean_must_establish") is not None
        assert len(k["lean_must_establish"]) > 0
        assert k.get("lean_proof_provenance") == "hand-written"
        assert k.get("lean_proof_code") is not None
        assert k.get("lean_proof_source"), "A7 verbatim source missing"
        assert k.get("lean_conclusion")


def test_label_from_theorem_map(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    for p in props:
        assert "label" in p, f"{p['property_id']} missing label"
        assert isinstance(p["label"], str)


def test_unenriched_health_has_none_lean_fields(theorem_map, scope):
    from speca_lean4.health import TheoremHealth
    old_health = {
        "GasperBeaconChain.Core.k_safety'": TheoremHealth({
            "name": "GasperBeaconChain.Core.k_safety'",
            "resolved": True, "lean_status": "proved",
            "sorry_free": True, "choice_free": True, "native_free": True,
            "module": "GasperBeaconChain.Core.AccountableSafety",
        })
    }
    props = build_properties(theorem_map, old_health, scope)
    k = next(p for p in props if p["property_id"] == "PROP-lean-safety-core-001")
    assert "lean_statement" not in k
    assert "lean_must_establish" not in k
    assert "lean_proof_code" not in k


def test_must_establish_extracted(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    k = _by_base(props, "PROP-lean-safety-core-001")[0]
    me = k.get("lean_must_establish", [])
    assert all(isinstance(s, str) for s in me)
    assert any("k_finalized" in s for s in me)


# ---------------------------------------------------------------------------
# B1 — must-establish decomposition (1 theorem -> N invariants)
# ---------------------------------------------------------------------------

def test_b1_decomposition_one_property_per_must_establish(theorem_map, health, scope):
    """k_safety' has 4 must-establish hypotheses -> exactly 4 properties, and
    the theorem-level base id is NOT emitted alongside them."""
    props = build_properties(theorem_map, health, scope)
    ks = _by_base(props, "PROP-lean-safety-core-001")
    assert len(ks) == 4
    assert {p["property_id"] for p in ks} == {
        f"PROP-lean-safety-core-001-me{i}" for i in range(1, 5)
    }
    preconds = [p["lean_precondition"] for p in ks]
    assert len(set(preconds)) == 4  # one distinct precondition each
    assert any("k_finalized" in p for p in preconds)
    assert any("not_ancestor" in p for p in preconds)


def test_b1_no_must_establish_falls_back_to_one_property(theorem_map, health, scope):
    """Iff-shaped decidable-checker theorems have no must-establish hypothesis;
    they lower 1:1 and keep the base property id."""
    props = build_properties(theorem_map, health, scope)
    dbl = _by_base(props, "PROP-lean-slashing-001")  # slashed_double_vote_iff_bex
    assert len(dbl) == 1
    assert dbl[0]["property_id"] == "PROP-lean-slashing-001"
    assert "lean_precondition" not in dbl[0]
    # B2 no-precondition shape: unconditional guarantee, neutral wording
    assert "guarantees [" in dbl[0]["assertion"]
    assert "no must-establish preconditions" in dbl[0]["assertion"]


def test_b1_depend_allowed_hypotheses_are_not_invariants(theorem_map, health, scope):
    """plausible_liveness_construct_extension carries 3 depend-allowed model
    assumptions (two_thirds_good, good_votes, blocks_exist) and 2 must-establish
    facts -> exactly 2 properties, none about a model assumption."""
    props = build_properties(theorem_map, health, scope)
    live = _by_base(props, "PROP-lean-liveness-core-001")
    assert len(live) == 2
    for p in live:
        assert "two_thirds_good" not in p["lean_precondition"]
        assert "good_votes" not in p["lean_precondition"]
        assert "blocks_exist" not in p["lean_precondition"]


def test_b1_total_property_count_grows(theorem_map, health, scope):
    """MTG principle: the must-establish set grows with sophistication; the
    decomposed property count must exceed the 25 theorem-level entries."""
    props = build_properties(theorem_map, health, scope)
    assert len(props) > len(theorem_map["properties"])


# ---------------------------------------------------------------------------
# B2 — neutral audit-result framing
# ---------------------------------------------------------------------------

def test_b2_audit_assertion_shape(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    k = next(p for p in props if p["property_id"] == "PROP-lean-safety-core-001-me1")
    assert k["assertion"].startswith("implementation must preserve [")
    assert "; if so, k_safety' guarantees [" in k["assertion"]
    assert k["lean_conclusion"].startswith("q_intersection_slashed")
    # neutral: no good/bad verdict vocabulary
    for banned in ("vulnerable", "secure", "bad", "good", "FAIL", "PASS"):
        assert banned not in k["assertion"]


# ---------------------------------------------------------------------------
# B3 — proof-DAG severity
# ---------------------------------------------------------------------------

def test_b3_lemma_inherits_dependent_severity(theorem_map, health, scope):
    """quorum_2_upclosed is MEDIUM in theorem_map, but the CRITICAL k_safety'
    depends (transitively, via two_justified_same_height_slashed) on it, so it
    inherits CRITICAL."""
    from speca_lean4.mapping import derive_severities
    sev = derive_severities(theorem_map["properties"], health)
    assert sev["GasperBeaconChain.Core.k_safety'"] == "CRITICAL"
    assert sev["GasperBeaconChain.Core.two_justified_same_height_slashed"] == "CRITICAL"
    assert sev["GasperBeaconChain.Core.quorum_2_upclosed"] == "CRITICAL"
    props = build_properties(theorem_map, health, scope)
    for p in _by_base(props, "PROP-lean-quorum-core-001"):
        assert p["severity"] == "CRITICAL"


def test_b3_never_downgrades(theorem_map, health, scope):
    """Upward-only inheritance: no derived severity is below its map severity."""
    from speca_lean4.mapping import derive_severities, _SEVERITY_RANK
    sev = derive_severities(theorem_map["properties"], health)
    for e in theorem_map["properties"]:
        assert _SEVERITY_RANK[sev[e["theorem"]]] >= _SEVERITY_RANK[str(e["severity"]).upper()]


def test_b3_unenriched_health_keeps_map_severity(theorem_map, scope):
    from speca_lean4.mapping import derive_severities
    sev = derive_severities(theorem_map["properties"], {})
    for e in theorem_map["properties"]:
        assert sev[e["theorem"]] == str(e["severity"]).upper()


# ---------------------------------------------------------------------------
# B5 — type-consistency gate
# ---------------------------------------------------------------------------

def test_b5_gasper_heads_are_consistent(theorem_map, health, scope):
    """Every decomposed property whose precondition has a gasper-local head must
    gate 'ok' (the head is a referenced constant of the same statement)."""
    props = build_properties(theorem_map, health, scope)
    decomposed = [p for p in props if "lean_type_consistency" in p]
    assert decomposed
    assert all(p["lean_type_consistency"] in ("ok", "unchecked") for p in decomposed)
    assert any(p["lean_type_consistency"] == "ok" for p in decomposed)


def test_b5_non_gasper_head_is_unchecked(theorem_map, health, scope):
    """`bj != bf` (head Ne) carries no gasper subject claim -> unchecked."""
    props = build_properties(theorem_map, health, scope)
    ne = [
        p for p in _by_base(props, "PROP-lean-safety-core-003")
        if "≠" in p["lean_precondition"]
    ]
    assert ne and all(p["lean_type_consistency"] == "unchecked" for p in ne)


# ---------------------------------------------------------------------------
# C5 — label-derived spec_reference / covers
# ---------------------------------------------------------------------------

def test_c5_spec_reference_derived_from_label(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    for p in props:
        assert p.get("spec_reference"), f"{p['property_id']} missing spec_reference"
        assert p["spec_reference"].startswith("consensus-specs:specs/")
        assert "#process_" in p["spec_reference"]
    s1 = next(p for p in props if p["property_id"].startswith("PROP-lean-slashing-001"))
    assert s1["spec_reference"] == "consensus-specs:specs/phase0/beacon-chain.md#process_slashings"


def test_c5_covers_falls_back_to_label_symbol(theorem_map, health, scope):
    """With no subgraphs, covers is the label's pyspec symbol, not prose."""
    props = build_properties(theorem_map, health, scope)
    s1 = next(p for p in props if p["property_id"].startswith("PROP-lean-slashing-001"))
    assert s1["covers"] == "process_slashings"
    k = next(p for p in props if p["property_id"].startswith("PROP-lean-safety-core-001"))
    assert k["covers"] == "process_justification_and_finalization"


def test_b5_mismatch_is_flagged(theorem_map, scope):
    """A precondition whose gasper-local head is NOT among the statement's
    referenced constants must be flagged 'mismatch', not dropped."""
    from speca_lean4.health import TheoremHealth
    doctored = {
        "GasperBeaconChain.Core.k_safety'": TheoremHealth({
            "name": "GasperBeaconChain.Core.k_safety'",
            "resolved": True, "lean_status": "proved",
            "sorry_free": True, "choice_free": True, "native_free": True,
            "module": "GasperBeaconChain.Core.Theories.AccountableSafety",
            "statement": "∀ st, drifted_predicate st → q_intersection_slashed st",
            "conclusion": "q_intersection_slashed st",
            "hypotheses": [
                {"name": "h", "type": "drifted_predicate st",
                 "head": "GasperBeaconChain.Core.drifted_predicate",
                 "class": "must-establish"},
            ],
            "referenced_constants": ["GasperBeaconChain.Core.q_intersection_slashed"],
        })
    }
    props = build_properties(theorem_map, doctored, scope)
    k = next(p for p in props if p["property_id"] == "PROP-lean-safety-core-001-me1")
    assert k["lean_type_consistency"] == "mismatch"
