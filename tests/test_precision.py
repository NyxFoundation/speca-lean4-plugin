"""Tests for the M2 precision harness (synthetic mini-benchmark; no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speca_lean4.precision import (
    granularity_report,
    load_benchmark,
    recall_report,
    verify_precision,
)

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"


def _bench_prop(i: int, sev: str = "CRITICAL") -> dict:
    return {
        "property_id": f"PROP-B-x-{i:03d}",
        "text": "All allocations in some_function() must be freed on every error path" + "x" * 30,
        "type": "invariant",
        "assertion": "forall alloc(p) in f: on_every_path(exists free(p) OR transfer_ownership(p))",
        "severity": sev,
        "covers": f"FN-B-{i:03d}",
        "reachability": {
            "classification": "external-reachable",
            "entry_points": ["CallbackHandler"],
            "attacker_controlled": True,
            "bug_bounty_scope": "in-scope",
        },
        "exploitability": "external-attack",
        "bug_bounty_eligible": True,
    }


@pytest.fixture
def bench_dir(tmp_path) -> Path:
    d = tmp_path / "bench"
    d.mkdir()
    for f in range(3):
        props = [_bench_prop(i, "CRITICAL" if i % 2 else "HIGH") for i in range(10 + f)]
        (d / f"01e_PARTIAL_MANUAL_rq2a_X{f}.json").write_text(
            json.dumps({"properties": props}), encoding="utf-8"
        )
    return d


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


def test_load_benchmark_stats(bench_dir):
    b = load_benchmark(bench_dir)
    assert b["n_files"] == 3
    assert b["n_properties"] == 33
    assert b["props_per_file"]["mean"] == 11.0
    assert b["severity_counts"]["CRITICAL"] + b["severity_counts"]["HIGH"] == 33


def test_granularity_report_on_real_output(bench_dir, our_01e):
    props = json.loads(our_01e.read_text(encoding="utf-8"))["properties"]
    g = granularity_report(props, load_benchmark(bench_dir))
    assert g["schema_validity"] == 1.0, g["schema_problems"]
    assert g["vocabulary_conformance"] == 1.0, g["vocabulary_nonconforming"]
    assert g["n_properties"] == 7
    assert g["severity_kl_divergence_nats"] >= 0


def test_recall_report_uses_curated_judgments(our_01e):
    props = json.loads(our_01e.read_text(encoding="utf-8"))["properties"]
    fmap = json.loads((_ROOT / "data" / "findings_map.json").read_text(encoding="utf-8"))
    r = recall_report(props, fmap)
    assert r["findings_in_domain"] > 0
    assert r["findings_total"] >= r["findings_in_domain"]
    # every coverage judgment must reference property ids that actually exist
    for row in r["rows"]:
        for pid in row["covered_by"]:
            assert any(p["property_id"] == pid for p in props), pid
    # strict recall can never exceed lenient
    assert r["recall_strict"] <= r["recall_lenient"]


def test_recall_ignores_out_of_domain(our_01e):
    props = json.loads(our_01e.read_text(encoding="utf-8"))["properties"]
    fmap = {
        "findings": [
            {"id": "oom-thing", "in_domain": False, "covered_by": [], "coverage": "none"},
            {"id": "covered", "in_domain": True,
             "covered_by": ["PROP-lean-safety-001"], "coverage": "full"},
        ]
    }
    r = recall_report(props, fmap)
    assert r["findings_in_domain"] == 1
    assert r["recall_strict"] == 1.0


def test_coverage_claim_requires_existing_property(our_01e):
    """A finding 'covered by' a property we do not emit must count as NOT covered."""
    props = json.loads(our_01e.read_text(encoding="utf-8"))["properties"]
    fmap = {
        "findings": [
            {"id": "ghost", "in_domain": True,
             "covered_by": ["PROP-lean-does-not-exist"], "coverage": "full"},
        ]
    }
    r = recall_report(props, fmap)
    assert r["recall_strict"] == 0.0
    assert r["rows"][0]["coverage"] == "none"


def test_verify_precision_end_to_end(bench_dir, our_01e):
    report = verify_precision(our_01e, bench_dir, _ROOT / "data" / "findings_map.json")
    assert set(report) == {"benchmark", "granularity", "recall"}
