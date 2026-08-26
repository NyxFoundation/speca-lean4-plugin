import importlib.util
from pathlib import Path

from speca_lean4.frontier import proof_closure, proof_evidence
from speca_lean4.health import load_health


ROOT = Path(__file__).resolve().parents[1]

_FULL_HEALTH = ROOT / "lean-ethtotal" / "health.json"
_FRONTIER_FIXTURE = ROOT / "tests" / "fixtures" / "theorem_health.frontier.sample.json"


def _health_path() -> Path:
    """Use a full export when available, otherwise the committed closure fixture."""
    return _FULL_HEALTH if _FULL_HEALTH.exists() else _FRONTIER_FIXTURE


def _load_generator():
    path = ROOT / "tools" / "generate-properties.py"
    spec = importlib.util.spec_from_file_location("generate_properties_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_proof_closure_is_transitive_and_excludes_definitions():
    health = load_health(_health_path())
    root = "EthTotal.Ledger.destroy_guard_invalidated_by_credit"
    closure = proof_closure(health, root)
    names = [x["theorem"] for x in closure]
    assert names[:2] == [
        "EthTotal.Ledger.bal_credit_after_zero",
        "EthTotal.Ledger.setBal_bal_self",
    ]
    assert "EthTotal.Ledger.setBal" not in names
    assert all(x["fact_id"].startswith("L") for x in closure)


def test_evidence_hash_changes_when_proof_closure_changes():
    generator = _load_generator()
    health = load_health(_health_path())
    evidence = generator.evidence_for(
        {"theorem": "EthTotal.Ledger.destroy_guard_invalidated_by_credit"}, health
    )
    assert evidence is not None
    assert evidence["payload"]["proof_closure"]
    assert evidence["payload"]["proof_dependency_stats"]["theorem_records"] == 4
    assert evidence["payload"]["must_establish"]


def test_packet_validation_requires_full_closure_coverage():
    generator = _load_generator()
    health = load_health(_health_path())
    evidence = generator.evidence_for(
        {"theorem": "EthTotal.Ledger.destroy_guard_invalidated_by_credit"}, health
    )
    assert evidence is not None
    packet = {
        "guarantee": "root",
        "preconditions": [],
        "supporting_facts": [{
            "fact_id": "FACT-1", "source_fact_ids": ["ROOT"],
            "claim": "claim", "check": "check", "expected": "expected",
            "flag_if": "flag",
        }],
        "derived_obligations": [{
            "obligation_id": "OBS-1", "check": "check", "expected": "expected",
            "flag_if": "flag", "supports": ["FACT-1"],
        }],
        "derivation": "root follows",
        "omitted_facts": [],
    }
    checked, reason = generator.validate_audit_packet(packet, evidence)
    assert checked is None
    assert "not covered" in reason
