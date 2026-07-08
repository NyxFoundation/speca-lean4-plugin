"""End-to-end CLI test: emit-01e from a health fixture, validate the output file."""

from __future__ import annotations

import json
from pathlib import Path

from speca_lean4.cli import main
from speca_lean4.schema import validate_property

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"


def test_emit_01e_end_to_end(tmp_path):
    out = tmp_path / "01e_lean.json"
    rc = main([
        "emit-01e",
        "--scope", str(_FIX / "bug_bounty_scope.sample.json"),
        "--health-json", str(_FIX / "theorem_health.sample.json"),
        "--gasper-ref", "deadbeef",
        "--out", str(out),
    ])
    assert rc == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["phase"] == "01e"
    assert doc["provider"] == "lean"
    assert doc["gasper_ref"] == "deadbeef"
    props = doc["properties"]
    n_map = len(json.loads((_ROOT / "theorem_map.json").read_text(encoding="utf-8"))["properties"])
    assert len(props) == n_map  # every mapped theorem emits exactly one property
    for p in props:
        assert not validate_property(p), p["property_id"]
        assert "@deadbeef:" in p["lean_artifact"]
    proved = [p for p in props if p["lean_status"] == "proved"]
    assert len(proved) == n_map  # fixture marks every target proved


def test_emit_01e_sharded_out_dir(tmp_path):
    out_dir = tmp_path / "shards"
    rc = main([
        "emit-01e",
        "--scope", str(_FIX / "bug_bounty_scope.sample.json"),
        "--health-json", str(_FIX / "theorem_health.sample.json"),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    files = sorted(out_dir.glob("01e_PARTIAL_*.json"))
    assert files, "no shard files written"
    theorem_map = json.loads((_ROOT / "theorem_map.json").read_text(encoding="utf-8"))
    shards = {e.get("shard") for e in theorem_map["properties"]}
    written_shards = set()
    total = 0
    for fp in files:
        doc = json.loads(fp.read_text(encoding="utf-8"))
        assert doc["phase"] == "01e" and doc["provider"] == "lean"
        assert doc["shard"] in shards
        assert doc["properties"], fp.name
        written_shards.add(doc["shard"])
        total += len(doc["properties"])
        # shard is a grouping key only; never leaks into a property
        for p in doc["properties"]:
            assert "shard" not in p
            assert not validate_property(p), p["property_id"]
    assert written_shards == shards
    assert total == len(theorem_map["properties"])  # partition, no loss/dup


def test_emit_01e_requires_an_output(tmp_path):
    rc = main([
        "emit-01e",
        "--scope", str(_FIX / "bug_bounty_scope.sample.json"),
        "--health-json", str(_FIX / "theorem_health.sample.json"),
    ])
    assert rc == 2  # neither --out nor --out-dir


def test_emit_01e_no_health_is_honest_unknown(tmp_path, capsys):
    out = tmp_path / "01e_lean.json"
    rc = main([
        "emit-01e",
        "--scope", str(_FIX / "bug_bounty_scope.sample.json"),
        "--out", str(out),
    ])
    assert rc == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert all(p["lean_status"] == "unknown" for p in doc["properties"])
