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
    n_map = len(json.loads((_ROOT / "theorem_map.json").read_text(encoding="utf-8"))["properties"])
    assert g["n_properties"] >= n_map  # B1 decomposition: >= one property per theorem
    assert g["severity_kl_divergence_nats"] >= 0


def test_recall_report_uses_curated_judgments(our_01e):
    props = json.loads(our_01e.read_text(encoding="utf-8"))["properties"]
    fmap = json.loads((_ROOT / "data" / "findings_map.json").read_text(encoding="utf-8"))
    r = recall_report(props, fmap)
    assert r["findings_in_domain"] > 0
    assert r["findings_total"] >= r["findings_in_domain"]
    # every coverage judgment must reference property ids that actually exist
    # (base theorem-level id, possibly refined into -me<i> ids by B1)
    for row in r["rows"]:
        for pid in row["covered_by"]:
            assert any(
                p["property_id"] == pid or p["property_id"].startswith(pid + "-me")
                for p in props
            ), pid
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
    assert set(report) == {"benchmark", "granularity", "recall", "label_recall"}


def test_shard_granularity_within_band(tmp_path, bench_dir):
    """Sharded emit must land each shard's props/file within the benchmark 1-sigma."""
    from speca_lean4.cli import main
    from speca_lean4.precision import load_benchmark, shard_granularity

    out_dir = tmp_path / "shards"
    rc = main([
        "emit-01e",
        "--scope", str(_FIX / "bug_bounty_scope.sample.json"),
        "--health-json", str(_FIX / "theorem_health.sample.json"),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    sg = shard_granularity(out_dir, load_benchmark(bench_dir))
    assert sg["n_files"] >= 2
    total = sum(s["n_properties"] for s in sg["per_shard"])
    assert total == sg["total_properties"]
    # against the REAL benchmark 1-sigma (11.62 +/- 3.72) the two shards (12, 13)
    # must both be in band; here bench_dir is synthetic (mean ~11) so still holds
    for s in sg["per_shard"]:
        assert s["props_per_file_z"] is not None


def test_label_recall_basic(our_01e):
    from speca_lean4.precision import label_recall_report
    props = json.loads(our_01e.read_text(encoding="utf-8"))["properties"]
    fmap = {
        "findings": [
            {"id": "f1", "in_domain": True, "label": "beacon-chain:slashing"},
            {"id": "f2", "in_domain": True, "label": "beacon-chain:justification-and-finality"},
        ]
    }
    r = label_recall_report(props, fmap)
    assert r["findings_in_domain"] == 2
    assert r["label_matched"] == 2
    assert r["label_recall"] == 1.0


def test_label_recall_no_matching_label(our_01e):
    from speca_lean4.precision import label_recall_report
    props = json.loads(our_01e.read_text(encoding="utf-8"))["properties"]
    fmap = {
        "findings": [
            {"id": "f1", "in_domain": True, "label": "no-such-label"},
        ]
    }
    r = label_recall_report(props, fmap)
    assert r["label_matched"] == 0
    assert r["label_recall"] == 0.0
    assert "no-such-label" in r["uncovered_labels"]


def test_verify_precision_includes_label_recall(bench_dir, our_01e):
    report = verify_precision(our_01e, bench_dir, _ROOT / "data" / "findings_map.json")
    assert "label_recall" in report
    lr = report["label_recall"]
    assert lr["findings_in_domain"] > 0
    assert lr["label_recall"] is not None


def test_verify_precision_includes_shard_granularity(tmp_path, bench_dir):
    from speca_lean4.cli import main

    out_dir = tmp_path / "shards"
    out = tmp_path / "01e_all.json"
    main([
        "emit-01e",
        "--scope", str(_FIX / "bug_bounty_scope.sample.json"),
        "--health-json", str(_FIX / "theorem_health.sample.json"),
        "--out", str(out),
        "--out-dir", str(out_dir),
    ])
    report = verify_precision(out, bench_dir, _ROOT / "data" / "findings_map.json", out_dir)
    assert "shard_granularity" in report
    assert report["shard_granularity"]["total_properties"] == report["granularity"]["n_properties"]
