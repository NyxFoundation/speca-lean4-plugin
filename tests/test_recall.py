"""Tests for the D6 label-grounded recall harness (issue #6).

The real-data tests pin the CURRENT domain-v1 numbers on purpose: the
denominator is part of the reviewable contract (D1), so growing the domain
or the coverage must show up as a deliberate test change, never silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speca_lean4.recall import (
    format_recall_summary,
    in_domain,
    label_recall_report,
    load_json,
    load_vulns,
    strict_problems,
    verify_recall,
)

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"
_DATA = _ROOT / "data"


@pytest.fixture
def our_01e(tmp_path) -> Path:
    from speca_lean4.cli import main

    out = tmp_path / "01e_lean.json"
    rc = main([
        "emit-01e",
        "--scope", str(_FIX / "bug_bounty_scope.sample.json"),
        "--health-json", str(_FIX / "theorem_health.sample.json"),
        "--out", str(out),
    ])
    assert rc == 0
    return out


@pytest.fixture
def props(our_01e) -> list[dict]:
    return json.loads(our_01e.read_text(encoding="utf-8"))["properties"]


def _rules() -> dict:
    return load_json(_DATA / "label_match_rules.json")


def _gaps() -> dict:
    return load_json(_DATA / "recall_gaps.json")


# ---------------------------------------------------------------- domain (D1)

def test_domain_filter_is_structural():
    domain = _rules()["domain"]
    ok, _ = in_domain(
        {"label": "beacon-chain:slashing", "severity": "High",
         "root_cause": "integer_overflow_underflow", "attack_path": "malicious_block"},
        domain,
    )
    assert ok
    # out-of-domain label
    assert not in_domain(
        {"label": "fork-choice", "severity": "High",
         "root_cause": "consensus_divergence", "attack_path": "malicious_block"},
        domain,
    )[0]
    # resource-exhaustion class excluded (plan section 4)
    assert not in_domain(
        {"label": "beacon-chain:slashing", "severity": "High",
         "root_cause": "resource_exhaustion", "attack_path": "malicious_block"},
        domain,
    )[0]
    # transport trigger excluded
    assert not in_domain(
        {"label": "beacon-chain:slashing", "severity": "High",
         "root_cause": "integer_overflow_underflow", "attack_path": "peer"},
        domain,
    )[0]
    # informational crawl rows excluded
    assert not in_domain(
        {"label": "beacon-chain:slashing", "severity": "Info",
         "root_cause": "integer_overflow_underflow", "attack_path": "malicious_block"},
        domain,
    )[0]


def test_vendored_slice_matches_meta():
    rows = load_vulns(_DATA / "ethereum_vulns.csv")
    meta = load_json(_DATA / "ethereum_vulns.meta.json")
    assert len(rows) == meta["n_rows"]
    assert {r["label"] for r in rows} <= set(meta["slice_criteria"]["label_in"])
    # slice labels are exactly the v1 domain labels (D1 narrow start)
    assert set(meta["slice_criteria"]["label_in"]) == set(_rules()["domain"]["labels"])


# --------------------------------------------------------- recall on real data

def test_label_recall_on_real_data(props):
    """Pin the domain-v1 numbers: denominator 9, covered 5, recall 0.556."""
    r = label_recall_report(props, load_vulns(), _rules(), _gaps())
    assert r["slice_rows"] == 37
    assert r["findings_in_domain"] == 9  # documented denominator (D1)
    assert r["covered"] == 5
    assert r["label_recall"] == 0.556
    # D2 loop is clean: every uncovered finding triaged, nothing stale
    assert r["untriaged_uncovered"] == []
    assert r["stale_gap_entries"] == []
    assert r["unverifiable_rules"] == []
    assert r["gap_dispositions"] == {"new_target": 2, "out_of_model": 2}
    assert strict_problems(r) == []


def test_covered_by_ids_are_actually_emitted(props):
    """Grounding guard: every id a match claims must exist in the real 01e
    (base id or a B1 -me refinement) and carry the matching label."""
    r = label_recall_report(props, load_vulns(), _rules(), _gaps())
    pids = [p["property_id"] for p in props]
    by_label = {p["property_id"]: p.get("label") for p in props}
    for row in r["rows"]:
        for base in row["covered_by"]:
            hits = [pid for pid in pids if pid == base or pid.startswith(base + "-me")]
            assert hits, base
            assert all(by_label[h] == row["label"] for h in hits)


def test_rule_claiming_ghost_property_is_not_coverage(props):
    """A rule pointing at a non-emitted property must NOT count as covered."""
    rules = {
        "domain": _rules()["domain"],
        "rules": [{
            "label": "beacon-chain:slashing",
            "root_cause": "integer_overflow_underflow",
            "covered": True,
            "covered_by": ["PROP-lean-does-not-exist"],
            "rationale": "test",
        }],
    }
    vulns = [{
        "id": "x1", "label": "beacon-chain:slashing", "severity": "High",
        "root_cause": "integer_overflow_underflow", "attack_path": "malicious_block",
    }]
    r = label_recall_report(props, vulns, rules, {"gaps": []})
    assert r["covered"] == 0
    assert r["rows"][0]["match_basis"] == "rule_unverifiable"
    assert r["unverifiable_rules"]
    assert r["untriaged_uncovered"] == ["x1"]
    assert strict_problems(r)


def test_no_rule_cell_is_not_coverage(props):
    """An unlisted (label, root_cause) cell counts as uncovered (no_rule)."""
    vulns = [{
        "id": "x2", "label": "beacon-chain:slashing", "severity": "High",
        "root_cause": "improper_state_update", "attack_path": "malicious_block",
    }]
    r = label_recall_report(props, vulns, {"domain": _rules()["domain"], "rules": []}, {"gaps": []})
    assert r["covered"] == 0
    assert r["rows"][0]["match_basis"] == "no_rule"


def test_stale_gap_entry_is_flagged(props):
    """A gap entry for a finding that is covered (or absent) must be flagged."""
    vulns = [{
        "id": "cov1", "label": "beacon-chain:effective-balance-updates", "severity": "High",
        "root_cause": "consensus_divergence", "attack_path": "crafted_state",
    }]
    gaps = {"gaps": [{"finding_id": "cov1", "disposition": "out_of_model"}]}
    r = label_recall_report(props, vulns, _rules(), gaps)
    assert r["covered"] == 1
    assert r["stale_gap_entries"] == ["cov1"]
    assert strict_problems(r)


def test_verify_recall_cli_strict_green_on_shipped_data(our_01e, tmp_path):
    from speca_lean4.cli import main

    out = tmp_path / "recall_report.json"
    rc = main(["verify-recall", "--ours", str(our_01e), "--strict", "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["label_recall"] == 0.556
    summary = format_recall_summary(report)
    assert "label-grounded recall" in summary
    assert "PROBLEM" not in summary


def test_verify_recall_function_matches_cli(our_01e):
    r = verify_recall(our_01e)
    assert r["findings_in_domain"] == 9
    assert r["label_recall"] == 0.556
