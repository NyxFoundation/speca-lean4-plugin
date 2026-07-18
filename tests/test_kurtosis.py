"""Workstream E (issue #7) — checker links, kurtosis fixture scaffolds, evidence seeds.

No Lean toolchain and no Kurtosis needed: everything runs on the sample health
fixture, and the emitted fixtures are SCAFFOLDS by contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speca_lean4 import build_properties, validate_property
from speca_lean4.health import index_health
from speca_lean4.kurtosis import (
    DEFAULT_CHECKER_MAP,
    DEFAULT_EVIDENCE_SEEDS,
    attach_checkers,
    base_property_id,
    emit_kurtosis,
    load_checker_map,
    load_evidence_seeds,
    safe_label,
    theorem_index,
)

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"

# The only decidable checkers / witnesses that exist in gasper-lean4's
# Executable layer (verified against GasperBeaconChain/Executable/*.lean).
_REAL_CHECKERS = {
    "GasperBeaconChain.Executable.slashedB",
    "GasperBeaconChain.Executable.justifiedB",
    "GasperBeaconChain.Executable.notSlashedB",
    "GasperBeaconChain.Executable.goodQuorumAtB",
    "GasperBeaconChain.Executable.qIntersectionWitnessB",
}
_REAL_WITNESSES = {
    "GasperBeaconChain.Executable.accountable_safety_witnessB",
    "GasperBeaconChain.Executable.k_accountable_safety_witnessB",
    "GasperBeaconChain.Core.plausible_liveness_construct_extension",
}


@pytest.fixture
def theorem_map() -> dict:
    return json.loads((_ROOT / "theorem_map.json").read_text(encoding="utf-8"))


@pytest.fixture
def health() -> dict:
    return index_health(json.loads((_FIX / "theorem_health.sample.json").read_text(encoding="utf-8")))


@pytest.fixture
def scope() -> dict:
    return json.loads((_FIX / "bug_bounty_scope.sample.json").read_text(encoding="utf-8"))


@pytest.fixture
def checker_map() -> dict:
    return load_checker_map(DEFAULT_CHECKER_MAP)


@pytest.fixture
def seeds() -> list:
    return load_evidence_seeds(DEFAULT_EVIDENCE_SEEDS)


@pytest.fixture
def props(theorem_map, health, scope) -> list[dict]:
    return build_properties(theorem_map, health, scope)


# ---------------------------------------------------------------------------
# E1 — checker_map integrity and attachment
# ---------------------------------------------------------------------------

def test_checker_map_keys_are_mapped_theorems(theorem_map, checker_map):
    theorems = {e["theorem"] for e in theorem_map["properties"]}
    for t in checker_map:
        assert t in theorems, f"checker_map references unmapped theorem {t}"


def test_checker_map_names_are_real(checker_map):
    """Honesty: every checker/witness must be a name verified to exist in
    gasper-lean4's Executable layer (or the Core constructive-witness theorem)."""
    for t, entry in checker_map.items():
        assert entry["checkers"], f"{t} has an empty checkers list"
        for c in entry["checkers"]:
            assert c in _REAL_CHECKERS, f"{t}: unknown checker {c}"
        if entry.get("witness"):
            assert entry["witness"] in _REAL_WITNESSES, f"{t}: unknown witness {entry['witness']}"
        assert entry.get("correctness"), f"{t} cites no correctness theorem"


def test_arithmetic_theorems_have_no_checker(checker_map):
    """The pure-arithmetic / definitional Core theorems have no Executable
    counterpart and must be honestly absent."""
    for t in (
        "GasperBeaconChain.Core.slashable_bound",
        "GasperBeaconChain.Core.quorum_intersection_weight_lower",
        "GasperBeaconChain.Core.validator_intersection_lower_bound",
        "GasperBeaconChain.Core.finalized_means_one_finalized",
        "GasperBeaconChain.Core.quorum_2_upclosed",
    ):
        assert t not in checker_map


def test_attach_checkers_surfaces_fields(props, theorem_map, checker_map):
    n = attach_checkers(props, theorem_map, checker_map)
    assert n > 0
    by_id = {p["property_id"]: p for p in props}
    # k_safety' decomposes to -me1..-me4; each inherits the checker + witness
    k = by_id["PROP-lean-safety-core-001-me1"]
    assert k["checker"] == "GasperBeaconChain.Executable.qIntersectionWitnessB"
    assert k["witness"] == "GasperBeaconChain.Executable.k_accountable_safety_witnessB"
    # the S1 decidable-checker theorem links to slashedB, no witness
    s1 = by_id["PROP-lean-slashing-001"]
    assert s1["checker"] == "GasperBeaconChain.Executable.slashedB"
    assert "witness" not in s1
    # slashable_bound has no Executable counterpart -> untouched
    for p in props:
        if base_property_id(p["property_id"]) == "PROP-lean-bound-001":
            assert "checker" not in p and "witness" not in p


def test_attach_checkers_keeps_schema_valid(props, theorem_map, checker_map):
    attach_checkers(props, theorem_map, checker_map)
    for p in props:
        assert not validate_property(p), p["property_id"]


def test_base_property_id():
    assert base_property_id("PROP-x-001-me3") == "PROP-x-001"
    assert base_property_id("PROP-x-001") == "PROP-x-001"


def test_theorem_index_covers_all_entries(theorem_map):
    idx = theorem_index(theorem_map)
    assert len(idx) == len(theorem_map["properties"])


# ---------------------------------------------------------------------------
# E3 — fixture scaffolds
# ---------------------------------------------------------------------------

def test_emit_kurtosis_writes_scaffolds_only_for_checker_linked(
    props, theorem_map, checker_map, seeds, tmp_path
):
    attach_checkers(props, theorem_map, checker_map)
    written = emit_kurtosis(props, theorem_map, checker_map, tmp_path, seeds)
    assert written
    linked = [p for p in props if "checker" in p]
    unlinked = [p for p in props if "checker" not in p]
    assert unlinked, "expected some honestly unlinked properties"
    assert len(written) == len(linked)
    # kurtosis_test non-null exactly where a real checker exists
    for p in linked:
        assert p.get("kurtosis_test"), p["property_id"]
        assert p["kurtosis_test"].endswith("assertion.scaffold.json")
    for p in unlinked:
        assert not p.get("kurtosis_test"), p["property_id"]


def test_fixture_layout_and_content(props, theorem_map, checker_map, seeds, tmp_path):
    attach_checkers(props, theorem_map, checker_map)
    emit_kurtosis(props, theorem_map, checker_map, tmp_path, seeds)
    k = next(p for p in props if p["property_id"] == "PROP-lean-safety-core-001-me1")
    fdir = tmp_path / safe_label(k["label"]) / k["property_id"]
    assert (fdir / "devnet.scaffold.json").is_file()
    assert (fdir / "assertion.scaffold.json").is_file()

    devnet = json.loads((fdir / "devnet.scaffold.json").read_text(encoding="utf-8"))
    assert devnet["scaffold"] is True
    assert "SCAFFOLD" in devnet["status"]
    assert devnet["devnet"]["participants"] is None  # placeholder, not a claim

    stub = json.loads((fdir / "assertion.scaffold.json").read_text(encoding="utf-8"))
    assert stub["scaffold"] is True
    assert stub["theorem"] == "GasperBeaconChain.Core.k_safety'"
    assert stub["checker"]["primary"] in _REAL_CHECKERS
    assert stub["checker"]["correctness"]
    assert stub["assertion"] == k["assertion"]
    # E5 handoff record shape (design contract with speca#92's backend)
    handoff = stub["handoff"]
    assert set(handoff) == {"property_id", "verdict", "harness", "artifact_path", "logs_path"}
    assert handoff["verdict"] is None  # nothing has run; scaffolds never claim a verdict
    assert handoff["harness"] == "NyxFoundation/kurtosis-harness"


def test_fixture_paths_are_windows_safe(props, theorem_map, checker_map, tmp_path):
    attach_checkers(props, theorem_map, checker_map)
    written = emit_kurtosis(props, theorem_map, checker_map, tmp_path, [])
    for fp in written:
        rel = fp.relative_to(tmp_path)
        assert ":" not in str(rel), rel


def test_safe_label():
    assert safe_label("beacon-chain:slashing") == "beacon-chain--slashing"


# ---------------------------------------------------------------------------
# E6 — dataset evidence seeds
# ---------------------------------------------------------------------------

def test_evidence_seeds_integrity(theorem_map, seeds):
    assert seeds
    labels_in_use = {e["label"] for e in theorem_map["properties"]}
    for s in seeds:
        assert s["label"] in labels_in_use, s["dataset_id"]
        assert s["files_changed"], s["dataset_id"]
        assert s["pre_fix_code_excerpt"].strip(), s["dataset_id"]
        assert s["source_url"].startswith("https://"), s["dataset_id"]
        assert s["why_implementation_linked"].strip(), s["dataset_id"]


def test_evidence_seeds_attached_by_label(props, theorem_map, checker_map, seeds, tmp_path):
    attach_checkers(props, theorem_map, checker_map)
    written = emit_kurtosis(props, theorem_map, checker_map, tmp_path, seeds)
    n_seeded = 0
    for fp in written:
        stub = json.loads(fp.read_text(encoding="utf-8"))
        for s in stub["evidence_seeds"]:
            assert s["label"] == stub["label"], fp
        n_seeded += bool(stub["evidence_seeds"])
    assert n_seeded > 0, "no fixture received a label-matched evidence seed"
