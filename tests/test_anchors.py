"""C3/C4 (issue #5) — anchor-table tests.

data/anchor_map.json is the def -> spec-symbol -> client-code-symbol alignment
table; `covers`/`spec_reference` must derive from it (via the label vocabulary),
never from prose guesses. Client-code rows are best-effort and honestly marked
verified-or-todo — these tests enforce that honesty contract too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speca_lean4 import build_properties
from speca_lean4.anchors import (
    anchor_for_def,
    anchor_map_path,
    client_symbols,
    load_anchor_map,
    spec_anchor,
    spec_reference,
    spec_symbol,
)
from speca_lean4.health import index_health

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def anchor_map() -> dict:
    m = load_anchor_map()
    assert m is not None, "data/anchor_map.json missing"
    return m


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


# ---------------------------------------------------------------------------
# C3 — table shape and coverage
# ---------------------------------------------------------------------------

def test_anchor_map_exists_at_expected_path(anchor_map):
    assert anchor_map_path() == _ROOT / "data" / "anchor_map.json"
    assert anchor_map.get("version") == 1
    assert anchor_map.get("labels")
    assert anchor_map.get("defs")


def test_every_theorem_map_label_is_anchored(anchor_map, theorem_map):
    """No target label may be missing from the anchor table (else covers/
    spec_reference would silently fall back)."""
    labels = set(anchor_map["labels"])
    for e in theorem_map["properties"]:
        assert e["label"] in labels, f"{e['property_id']}: label {e['label']} unanchored"


def test_one_defs_row_per_theorem_map_entry(anchor_map, theorem_map):
    """Rows are keyed by property_id: since the stage-2 checklist (CHK-*), one
    theorem may back several theorem_map entries, so lean_def is no longer a
    unique key — but each entry still has exactly one defs row."""
    by_pid = {r["property_id"]: r for r in anchor_map["defs"]}
    assert len(by_pid) == len(anchor_map["defs"]), "duplicate property_id rows"
    assert len(by_pid) == len(theorem_map["properties"]), "defs rows != entries"
    for e in theorem_map["properties"]:
        row = by_pid.get(e["property_id"])
        assert row, f"no defs row for {e['property_id']}"
        assert row["lean_def"] == e["theorem"]
        assert row["label"] == e["label"]


def test_defs_rows_are_internally_consistent(anchor_map):
    """Each defs row's spec_symbol/spec_reference must equal what its label
    resolves to in the labels table (one source of truth, no drift)."""
    labels = anchor_map["labels"]
    for row in anchor_map["defs"]:
        lab = labels[row["label"]]
        assert row["spec_symbol"] == lab["spec_symbol"], row["lean_def"]
        expected = f"consensus-specs:{lab['spec_doc']}#{lab['spec_symbol']}"
        assert row["spec_reference"] == expected, row["lean_def"]


def test_spec_symbols_are_pyspec_section_names(anchor_map):
    """Spec symbols come from the label vocabulary. beacon-chain:* labels use
    pyspec process_* names; fork-choice uses its pyspec handler names (on_*,
    get_head); the p2p-interface doc defines no pyspec functions, so its
    symbol is the document's section anchor."""
    for label, row in anchor_map["labels"].items():
        sym = row["spec_symbol"]
        assert row["spec_doc"].startswith("specs/"), (label, row["spec_doc"])
        if label.startswith("beacon-chain:"):
            assert sym.startswith("process_"), (label, sym)
        elif label == "fork-choice":
            assert sym.startswith(("on_", "get_")), (label, sym)
        else:
            assert sym and " " not in sym, (label, sym)


def test_client_code_rows_are_honest(anchor_map):
    """Best-effort client column: a row is either verified-<date> with a real
    repo/symbol/path, or explicitly 'todo' — never a fabricated mapping."""
    for label, row in anchor_map["labels"].items():
        for c in row["client_code"]:
            status = str(c.get("status", ""))
            assert status.startswith("verified-") or status == "todo", (label, c)
            if status.startswith("verified-"):
                assert c.get("repo") and c.get("symbol") and c.get("path"), (label, c)
                assert c["symbol"] != "TODO", (label, c)
            else:
                # todo rows must not pretend to carry a resolved path
                assert not c.get("path"), (label, c)


def test_client_symbols_helper_filters_verified(anchor_map):
    allc = client_symbols("beacon-chain:justification-and-finality")
    ver = client_symbols("beacon-chain:justification-and-finality", verified_only=True)
    assert ver and len(ver) <= len(allc)
    assert all(str(c["status"]).startswith("verified") for c in ver)
    assert client_symbols("no-such-label") == []
    assert client_symbols(None) == []


def test_anchor_for_def_lookup(anchor_map):
    row = anchor_for_def("GasperBeaconChain.Core.k_safety'")
    assert row
    assert row["property_id"] == "PROP-lean-safety-core-001"
    assert row["spec_symbol"] == "process_justification_and_finalization"
    assert anchor_for_def("GasperBeaconChain.Core.no_such_theorem") is None


# ---------------------------------------------------------------------------
# C4 — covers/spec_reference derive from the table, not guesses
# ---------------------------------------------------------------------------

def test_anchor_table_agrees_with_inline_fallback():
    """The inline C5 fallback in mapping.py must never drift from the table."""
    from speca_lean4.mapping import _LABEL_SPEC
    for label, (doc, symbol) in _LABEL_SPEC.items():
        assert spec_anchor(label) == (doc, symbol), label


def test_spec_reference_of_every_property_comes_from_table(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    for p in props:
        assert p.get("spec_reference") == spec_reference(p["label"]), p["property_id"]


def test_covers_fallback_is_the_anchored_spec_symbol(theorem_map, health, scope):
    """With no 01b subgraphs, `covers` must be the label's anchored pyspec
    symbol — a spec symbol from the table, not a prose covers_hint."""
    props = build_properties(theorem_map, health, scope)
    for p in props:
        assert p["covers"] == spec_symbol(p["label"]), p["property_id"]
        # retired prose fallbacks: no free-text hint may leak into covers
        assert " " not in p["covers"], p["property_id"]


def test_helpers_none_on_unknown_label():
    assert spec_anchor(None) is None
    assert spec_anchor("no-such-label") is None
    assert spec_reference("no-such-label") is None
    assert spec_symbol("no-such-label") is None
