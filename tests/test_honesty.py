"""H1 (issue #10) — explicit honesty-invariant tests.

The four invariants the plugin must never violate:

1. a `sorry`-dependent theorem is `lean_status=unknown`, never `proved`;
2. an unresolved target name is `unknown` on the Python side AND fails CI
   (the ci.yml lean-job smoke step asserts every target resolved);
3. the B3 proof-DAG severity propagation never downgrades or relabels a
   theorem_map severity;
4. a type mismatch fails the type-consistency gate (the ci.yml end-to-end
   step asserts zero `lean_type_consistency == "mismatch"`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speca_lean4 import build_properties
from speca_lean4.health import TheoremHealth, index_health, status_for, unresolved_targets
from speca_lean4.mapping import _SEVERITY_RANK, derive_severities

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"

_K_SAFETY = "GasperBeaconChain.Core.k_safety'"


@pytest.fixture
def theorem_map() -> dict:
    return json.loads((_ROOT / "theorem_map.json").read_text(encoding="utf-8"))


@pytest.fixture
def health() -> dict:
    return index_health(
        json.loads((_FIX / "theorem_health.sample.json").read_text(encoding="utf-8"))
    )


@pytest.fixture
def scope() -> dict:
    return json.loads((_FIX / "bug_bounty_scope.sample.json").read_text(encoding="utf-8"))


def _props_for(props: list[dict], base_id: str) -> list[dict]:
    return [
        p for p in props
        if p["property_id"] == base_id or p["property_id"].startswith(base_id + "-me")
    ]


# ---------------------------------------------------------------------------
# 1. sorry-dependent -> unknown
# ---------------------------------------------------------------------------

def test_sorry_dependent_theorem_is_unknown(theorem_map, scope):
    """A record the exporter classified sorry-dependent (sorry_free=false,
    lean_status=unknown) must lower to unknown properties — decomposition and
    enrichment must not resurrect a proved status."""
    doctored = {_K_SAFETY: TheoremHealth({
        "name": _K_SAFETY,
        "resolved": True, "lean_status": "unknown",
        "sorry_free": False, "choice_free": True, "native_free": True,
        "module": "GasperBeaconChain.Core.Theories.AccountableSafety",
        "statement": "∀ st, k_finalized st → q_intersection_slashed st",
        "conclusion": "q_intersection_slashed st",
        "hypotheses": [
            {"name": "h", "type": "k_finalized st",
             "head": "GasperBeaconChain.Core.k_finalized",
             "class": "must-establish"},
        ],
        "referenced_constants": [
            "GasperBeaconChain.Core.k_finalized",
            "GasperBeaconChain.Core.q_intersection_slashed",
        ],
    })}
    props = build_properties(theorem_map, doctored, scope)
    ks = _props_for(props, "PROP-lean-safety-core-001")
    assert ks, "sorry-dependent theorem must still be emitted, not dropped"
    assert all(p["lean_status"] == "unknown" for p in ks)
    assert not any(p["lean_status"] == "proved" for p in props if p["property_id"].startswith("PROP-lean-safety-core-001"))


def test_unresolved_record_can_never_claim_proved():
    """Python-side guard: even a doctored record with resolved=false and
    lean_status='proved' surfaces as unknown."""
    th = TheoremHealth({"name": "x", "resolved": False, "lean_status": "proved"})
    assert th.lean_status == "unknown"
    assert status_for({"x": th}, "x") == ("unknown", "")


# ---------------------------------------------------------------------------
# 2. unresolved target -> unknown AND CI failure
# ---------------------------------------------------------------------------

def test_unresolved_target_is_unknown_not_dropped(theorem_map, health, scope):
    """Remove one target from health: its properties are still emitted, marked
    unknown; every other property is untouched."""
    del health[_K_SAFETY]
    props = build_properties(theorem_map, health, scope)
    ks = _props_for(props, "PROP-lean-safety-core-001")
    assert len(ks) == 1  # unenriched -> 1:1 fallback, still present
    assert ks[0]["lean_status"] == "unknown"
    others = [p for p in props if not p["property_id"].startswith("PROP-lean-safety-core-001")]
    assert others and all(p["lean_status"] == "proved" for p in others)


def test_unresolved_target_fails_the_ci_gate(theorem_map, health, scope):
    """The gate CI enforces (ci.yml lean job asserts every target resolved):
    `unresolved_targets` must name a missing/unresolved target, and the gate
    assertion must fail on it."""
    targets = [e["theorem"] for e in theorem_map["properties"]]
    assert unresolved_targets(health, targets) == []  # green on real health

    del health[_K_SAFETY]
    bad = unresolved_targets(health, targets)
    assert bad == [_K_SAFETY]
    with pytest.raises(AssertionError):
        assert not bad, f"unresolved target theorems: {bad}"

    # a resolved=false record is just as unresolved as a missing one
    health[_K_SAFETY] = TheoremHealth({"name": _K_SAFETY, "resolved": False})
    assert unresolved_targets(health, targets) == [_K_SAFETY]


# ---------------------------------------------------------------------------
# 3. severity is never downgraded / relabeled by DAG propagation
# ---------------------------------------------------------------------------

def test_dag_propagation_never_downgrades_crafted_case():
    """A CRITICAL lemma with only a MEDIUM dependent keeps CRITICAL: the B3
    propagation is upward-only, it must not average or pull severities down."""
    entries = [
        {"theorem": "T.top", "severity": "MEDIUM"},
        {"theorem": "T.lemma", "severity": "CRITICAL"},
    ]
    health = {
        "T.top": TheoremHealth({"name": "T.top", "resolved": True,
                                "proof_constants": ["T.lemma"]}),
        "T.lemma": TheoremHealth({"name": "T.lemma", "resolved": True,
                                  "proof_constants": []}),
    }
    sev = derive_severities(entries, health)
    assert sev["T.lemma"] == "CRITICAL"  # not pulled down by the MEDIUM dependent
    assert sev["T.top"] == "MEDIUM"      # dependents themselves are never touched


def test_dag_propagation_only_upgrades_crafted_case():
    """The dual: a MEDIUM lemma under a CRITICAL dependent is upgraded — and
    that is the only kind of change the propagation may make."""
    entries = [
        {"theorem": "T.top", "severity": "CRITICAL"},
        {"theorem": "T.lemma", "severity": "MEDIUM"},
    ]
    health = {
        "T.top": TheoremHealth({"name": "T.top", "resolved": True,
                                "proof_constants": ["T.lemma"]}),
        "T.lemma": TheoremHealth({"name": "T.lemma", "resolved": True,
                                  "proof_constants": []}),
    }
    sev = derive_severities(entries, health)
    assert sev["T.lemma"] == "CRITICAL"
    assert sev["T.top"] == "CRITICAL"


def test_emitted_severity_never_below_theorem_map(theorem_map, health, scope):
    """End-to-end relabeling guard: every emitted property's severity is >= the
    hand-calibrated theorem_map severity of its theorem."""
    map_sev = {e["property_id"]: str(e["severity"]).upper() for e in theorem_map["properties"]}
    props = build_properties(theorem_map, health, scope)
    for p in props:
        base = p["property_id"].split("-me")[0]
        assert _SEVERITY_RANK[p["severity"]] >= _SEVERITY_RANK[map_sev[base]], p["property_id"]


# ---------------------------------------------------------------------------
# 4. type mismatch fails the type-consistency gate
# ---------------------------------------------------------------------------

def _mismatching_health() -> dict[str, TheoremHealth]:
    """A precondition whose gasper-local head is NOT among the statement's
    referenced constants."""
    return {_K_SAFETY: TheoremHealth({
        "name": _K_SAFETY,
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
    })}


def test_type_mismatch_fails_the_ci_gate(theorem_map, scope):
    """The gate CI enforces (ci.yml end-to-end step): zero mismatches on real
    output; a doctored mismatch must trip the same assertion, not vanish."""
    props = build_properties(theorem_map, _mismatching_health(), scope)
    bad = [p["property_id"] for p in props if p.get("lean_type_consistency") == "mismatch"]
    assert bad == ["PROP-lean-safety-core-001-me1"]
    with pytest.raises(AssertionError):
        assert not bad, f"type-consistency mismatches: {bad}"


def test_no_mismatch_on_real_health(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    assert not [p for p in props if p.get("lean_type_consistency") == "mismatch"]
