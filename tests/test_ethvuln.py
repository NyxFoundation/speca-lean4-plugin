"""Honesty invariants for the ethereum-vuln-dataset track (speca#146 c-1).

`theorem_map_ethvuln.json` registers the 66 Critical/High invariants that live
in this repo under `lean/SpecaExport/EthVuln/`; the exporter entry point is
`lean/MainEthVuln.lean` (`lake exe speca-export-ethvuln`). Like the EthTotal
track (tests/test_ethtotal.py) it has its own map, its own exporter entry
point and its own fixture health, so the gasper contract tests stay untouched.

What is pinned:

1. module wiring — the root module imports every Props file, the package root
   imports the track, and the exporter entry point loads the track at run
   time (the first CI failure of the track was exactly this: the modules built
   but the gasper exporter never imported them, so every target was
   unresolved);
2. map <-> Lean 1:1 — every registered theorem is declared in the placed
   sources and every declared theorem is registered; x_layer names the file
   the theorem is declared in;
3. the map is internally consistent (unique ids/theorems, non-empty required
   fields, benchmark-band assertion/text lengths);
4. proof status is never claimed by the map: the fixture health is real
   exporter output, `lean_status` is copied from it verbatim, and while the
   proofs are `sorry` stubs it reads `unknown` / `sorry_free=false` -- the
   emitted 01e must never say `proved` for a theorem the exporter did not
   certify;
5. the emitted 01e is schema-valid, represents every entry, and its spec
   anchoring is table-derived or honestly absent (never a prose guess).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from speca_lean4 import build_properties
from speca_lean4.anchors import spec_reference, spec_symbol
from speca_lean4.health import index_health, load_health
from speca_lean4.schema import validate_property

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"
_MAP = _ROOT / "theorem_map_ethvuln.json"
_LEAN = _ROOT / "lean"
_TRACK = _LEAN / "SpecaExport" / "EthVuln"
_PROPS = _TRACK / "Props"
_NS = "EthVulnFormalProps"

_DECL = re.compile(r"^theorem\s+([A-Za-z0-9_'.]+)", re.M)
_NAMESPACE = re.compile(r"^namespace\s+(\S+)", re.M)


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def theorem_map() -> dict:
    return _load(_MAP)


@pytest.fixture(scope="module")
def health() -> dict:
    return index_health(_load(_FIX / "theorem_health.ethvuln.sample.json"))


@pytest.fixture(scope="module")
def scope() -> dict:
    return _load(_FIX / "bug_bounty_scope.ethvuln.sample.json")


@pytest.fixture(scope="module")
def declared() -> dict[str, str]:
    """fully-qualified theorem name -> source file (relative to lean/)."""
    out: dict[str, str] = {}
    for f in sorted(_PROPS.glob("*.lean")):
        src = f.read_text(encoding="utf-8")
        ns = _NAMESPACE.findall(src)
        assert ns == [_NS], (f.name, ns)
        for m in _DECL.finditer(src):
            name = f"{_NS}.{m.group(1)}"
            assert name not in out, f"{name} declared twice"
            out[name] = str(f.relative_to(_LEAN))
    assert out, "no theorem declared under lean/SpecaExport/EthVuln/Props"
    return out


# ---------------------------------------------------------------------------
# 1. module wiring
# ---------------------------------------------------------------------------

def test_root_module_imports_every_props_file():
    root = (_TRACK.parent / "EthVuln.lean").read_text(encoding="utf-8")
    assert "import SpecaExport.EthVuln.Common" in root
    for f in sorted(_PROPS.glob("*.lean")):
        assert f"import SpecaExport.EthVuln.Props.{f.stem}" in root, f.name


def test_package_root_and_exporter_entry_point_load_the_track():
    """lake builds the track through the package root; the exporter resolves
    it only if the entry point imports it at compile time AND passes it to
    driverMain at run time (importModules)."""
    assert "import SpecaExport.EthVuln" in (_LEAN / "SpecaExport.lean").read_text(encoding="utf-8")
    entry = (_LEAN / "MainEthVuln.lean").read_text(encoding="utf-8")
    assert "import SpecaExport.EthVuln" in entry
    assert re.search(r"driverMain\s+ethVulnConfig\s+#\[`SpecaExport\.EthVuln\]", entry), entry
    lakefile = (_LEAN / "lakefile.lean").read_text(encoding="utf-8")
    assert re.search(r"lean_exe\s+«speca-export-ethvuln»\s+where\s+root\s*:=\s*`MainEthVuln", lakefile)
    basic = (_LEAN / "SpecaExport" / "Basic.lean").read_text(encoding="utf-8")
    assert re.search(r"def ethVulnConfig : ProjectConfig where\s+nsPrefix := `EthVulnFormalProps", basic)


def test_gasper_entry_point_stays_byte_compatible():
    """The gasper exporter must NOT grow the track: theorem_map.json is
    consensus-only and its export is byte-compatible (README)."""
    main = (_LEAN / "Main.lean").read_text(encoding="utf-8")
    assert "EthVuln" not in main
    gasper = _load(_ROOT / "theorem_map.json")
    assert not any(e["theorem"].startswith(_NS + ".") for e in gasper["properties"])
    assert not any(e["property_id"].startswith("PROP-lean-ethvuln") for e in gasper["properties"])


def test_map_names_its_exporter(theorem_map):
    assert theorem_map["lean_exe"] == "speca-export-ethvuln"
    assert theorem_map["source"] == "NyxFoundation/speca-lean4-plugin"
    assert theorem_map["ethvuln_source"] == "NyxFoundation/ethereum-vuln-dataset"
    assert re.fullmatch(r"[0-9a-f]{40}", theorem_map["ethvuln_ref"])


# ---------------------------------------------------------------------------
# 2. map <-> Lean 1:1
# ---------------------------------------------------------------------------

def test_every_registered_theorem_is_declared_and_vice_versa(theorem_map, declared):
    registered = {e["theorem"] for e in theorem_map["properties"]}
    assert registered == set(declared), (
        sorted(registered - set(declared)), sorted(set(declared) - registered))


def test_x_layer_is_the_declaring_file(theorem_map, declared):
    for e in theorem_map["properties"]:
        assert e["x_layer"] == declared[e["theorem"]], e["property_id"]


def test_theorem_names_follow_the_entry_scheme(theorem_map):
    for e in theorem_map["properties"]:
        cls = e["shard"].replace("-", "_")
        assert e["theorem"].startswith(f"{_NS}.entry_"), e["theorem"]
        assert e["theorem"].endswith("_" + cls), (e["theorem"], cls)
        assert e["x_entry_id"].strip(), e["property_id"]


# ---------------------------------------------------------------------------
# 3. map integrity
# ---------------------------------------------------------------------------

def test_map_is_internally_consistent(theorem_map):
    props = theorem_map["properties"]
    assert len(props) == 66
    ids = [e["property_id"] for e in props]
    ths = [e["theorem"] for e in props]
    assert len(ids) == len(set(ids)), "duplicate property_id"
    assert len(ths) == len(set(ths)), "duplicate theorem"
    for e in props:
        assert e["property_id"].startswith("PROP-lean-ethvuln-"), e["property_id"]
        for key in ("theorem", "label", "text", "assertion", "severity",
                    "bug_bounty_area", "shard", "x_dataset_evidence"):
            assert str(e.get(key, "")).strip(), (e["property_id"], key)
        assert e["severity"] in ("CRITICAL", "HIGH"), e["property_id"]
        assert e["bug_bounty_area"].split("/", 1)[0] in ("consensus", "execution"), e["property_id"]
        assert e.get("lowering") != "verbatim", e["property_id"]
        # benchmark bands (tests/test_mapping.py): the hand-written 1:1 form
        assert 30 <= len(e["assertion"]) <= 160, (e["property_id"], len(e["assertion"]))
        assert 40 <= len(e["text"]) <= 260, (e["property_id"], len(e["text"]))


def test_map_carries_no_proof_status_field(theorem_map):
    """Proof status comes ONLY from the exporter; the map must not grow a
    field a reader could mistake for a certification."""
    for e in theorem_map["properties"]:
        for key in e:
            assert "status" not in key.lower() and "proved" not in key.lower(), (e["property_id"], key)


# ---------------------------------------------------------------------------
# 4. proof status is the exporter's, never the map's
# ---------------------------------------------------------------------------

def test_fixture_health_is_the_tracks_exporter_output(theorem_map, health):
    raw = _load(_FIX / "theorem_health.ethvuln.sample.json")
    assert raw["project"] == _NS
    for e in theorem_map["properties"]:
        th = health.get(e["theorem"])
        assert th is not None, e["theorem"]
        assert th.resolved, e["theorem"]
        assert th.module.startswith("SpecaExport.EthVuln.Props."), e["theorem"]
        assert th.statement, e["theorem"]
        # honest status pairing: proved iff sorry-free
        assert th.lean_status in ("proved", "unknown"), (e["theorem"], th.lean_status)
        assert bool(th.get("sorry_free")) == (th.lean_status == "proved"), e["theorem"]


def test_emitted_status_is_copied_from_health_never_proved_without_certificate(
    theorem_map, health, scope
):
    props = build_properties(theorem_map, health, scope)
    for p in props:
        base = p["property_id"].split("-me")[0]
        th = health[next(e["theorem"] for e in theorem_map["properties"]
                         if e["property_id"] == base)]
        assert p["lean_status"] == th.lean_status, p["property_id"]
        if p["lean_status"] == "proved":
            assert th.get("sorry_free") is True, p["property_id"]
        assert not p["lean_status"].startswith("descends-from-"), p["property_id"]


def test_missing_health_is_unknown_not_dropped(theorem_map, scope):
    props = build_properties(theorem_map, {}, scope)
    assert {p["property_id"] for p in props} == {e["property_id"] for e in theorem_map["properties"]}
    assert all(p["lean_status"] == "unknown" for p in props)


# ---------------------------------------------------------------------------
# 5. emitted 01e
# ---------------------------------------------------------------------------

def test_emitted_properties_are_schema_valid_and_complete(theorem_map, health, scope):
    props = build_properties(theorem_map, health, scope)
    assert len(props) >= len(theorem_map["properties"])
    ids = {p["property_id"] for p in props}
    assert len(ids) == len(props)
    for e in theorem_map["properties"]:
        b = e["property_id"]
        assert b in ids or any(i.startswith(b + "-me") for i in ids), b
    for p in props:
        assert validate_property(p) == [], p["property_id"]
        assert p["lean_artifact"].startswith(
            "NyxFoundation/speca-lean4-plugin@main:SpecaExport/EthVuln/Props/"), p["property_id"]
        assert p["label"], p["property_id"]
        assert p["reachability"]["bug_bounty_scope"] == "in-scope", p["property_id"]
        if "-me" in p["property_id"] or "guarantees [" in p["assertion"]:
            assert 30 <= len(p["assertion"]) <= 600, (p["property_id"], len(p["assertion"]))
        else:
            assert 30 <= len(p["assertion"]) <= 160, (p["property_id"], len(p["assertion"]))
        assert p.get("lean_type_consistency") != "mismatch", p["property_id"]


def test_spec_anchoring_is_table_derived_or_honestly_absent(theorem_map, health, scope):
    """Labels with a consensus/execution anchor row resolve through the tables;
    the rest emit no spec_reference at all -- never a fabricated one -- and
    the map's note names them."""
    props = build_properties(theorem_map, health, scope)
    unanchored = {e["label"] for e in theorem_map["properties"] if spec_symbol(e["label"]) is None}
    for lab in unanchored:
        assert lab in theorem_map["note"], f"unanchored label {lab} not declared in the map note"
    for p in props:
        assert p.get("spec_reference") == spec_reference(p["label"]), p["property_id"]
        if p.get("spec_reference"):
            assert p["spec_reference"].startswith(("consensus-specs:", "execution-specs:"))
            assert p["covers"] == spec_symbol(p["label"]), p["property_id"]
        assert " " not in p["covers"], p["property_id"]
