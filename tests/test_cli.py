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
    assert len(props) == 7
    for p in props:
        assert not validate_property(p), p["property_id"]
        assert "@deadbeef:" in p["lean_artifact"]
    proved = [p for p in props if p["lean_status"] == "proved"]
    assert len(proved) == 7  # fixture marks every target proved


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
