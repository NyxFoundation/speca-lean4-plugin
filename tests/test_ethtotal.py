"""Honesty invariants for the EthTotal track (docs/ethtotal-track.md).

The gasper track pins its invariants in tests/test_honesty.py and in the CI
`honesty check` steps. This is the same idea for the second target: the claims
that make the EthTotal `01e` trustworthy are the ones a future edit is most
likely to break quietly, so they are asserted here rather than described in
prose.

What is pinned:

1. the lemma sweep is total — every theorem in the inventory is bucketed by the
   triage, with a reason, and every theorem-bearing source file is represented;
2. the reviewed curation only names theorems that exist;
3. the map is internally consistent, and its severity claims are only made
   where a human made them;
4. every generated CHK item descends from a mapped theorem and cites dataset
   evidence;
5. the map never claims a proof status the exporter did not report.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_INVENTORY = _ROOT / "data" / "ethtotal_inventory.json"
_TRIAGE = _ROOT / "data" / "ethtotal_triage.json"
_CURATION = _ROOT / "data" / "ethtotal_curation.json"
_MAP = _ROOT / "theorem_map_ethtotal.json"
_HEALTH = _ROOT / "lean-ethtotal" / "health.mapped.json"

_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def inventory() -> dict:
    return _load(_INVENTORY)


@pytest.fixture(scope="module")
def triage() -> dict:
    return _load(_TRIAGE)


@pytest.fixture(scope="module")
def curation() -> dict:
    return _load(_CURATION)


@pytest.fixture(scope="module")
def theorem_map() -> dict:
    return _load(_MAP)


@pytest.fixture(scope="module")
def health() -> dict:
    return {t["name"]: t for t in _load(_HEALTH)["theorems"]}


# --- 1. the lemma sweep is total -------------------------------------------

def test_triage_buckets_every_theorem(inventory, triage):
    """No theorem is silently dropped between inventory and triage."""
    inv_names = {d["name"] for d in inventory["declarations"] if d["kind"] == "theorem"}
    triaged = {e["name"] for f in triage["files"] for e in f["theorems"]}
    assert triaged == inv_names, (
        f"{len(inv_names - triaged)} theorem(s) missing from the triage, "
        f"{len(triaged - inv_names)} triaged theorem(s) not in the inventory"
    )


def test_every_triaged_theorem_has_a_bucket_and_a_reason(triage):
    for f in triage["files"]:
        for e in f["theorems"]:
            assert e["bucket"] in {"selected", "represented", "screened-out"}, e
            assert e["reason"].strip(), f"{e['name']}: bucketed without a reason"


def test_every_theorem_bearing_file_is_represented(triage):
    """The lemma layers get the same treatment as the headline theorems."""
    for f in triage["files"]:
        assert f["theorem_count"] > 0
        assert f["selected"], f"{f['file']}: {f['theorem_count']} theorems, none selected"


def test_lemma_layers_are_actually_covered(triage):
    layers = {f["layer"] for f in triage["files"] if f["selected"]}
    for required in ("Lemmata.Derives", "Lemmata.EthConcepts", "AtomicDef", "Extentions"):
        assert required in layers, f"no selection from the {required} layer"


# --- 2. the reviewed curation ----------------------------------------------

def test_curated_theorems_exist(inventory, curation):
    by_short: dict[str, list[str]] = {}
    names = set()
    for d in inventory["declarations"]:
        names.add(d["name"])
        by_short.setdefault(d["short_name"], []).append(d["name"])
    for c in curation["curated"]:
        n = c["theorem"]
        resolved = [n] if n in names else by_short.get(n.rsplit(".", 1)[-1], [])
        assert len(resolved) == 1, f"curated theorem {n!r} resolves to {resolved}"


def test_every_source_file_has_a_theme(triage, curation):
    for f in triage["files"]:
        assert f["file"] in curation["file_themes"], f"{f['file']}: no theme assigned"
    for f, theme in curation["file_themes"].items():
        assert theme in curation["themes"], f"{f}: unknown theme {theme!r}"


def test_curated_entries_are_complete(curation):
    for c in curation["curated"]:
        assert c["severity"] in _SEVERITIES, c
        assert c["text"].strip() and len(c["text"]) <= 260, c["theorem"]
        assert c["assertion"].strip() and len(c["assertion"]) <= 200, c["theorem"]


# --- 3. the map ------------------------------------------------------------

def test_map_ids_are_unique(theorem_map):
    ids = [e["property_id"] for e in theorem_map["properties"]]
    assert len(ids) == len(set(ids))


def test_base_entries_do_not_double_count_a_theorem(theorem_map):
    """A theorem may back several verbatim checklist entries, but only one base
    (decomposed) entry — otherwise its must-establish obligations are emitted
    twice."""
    base = [e["theorem"] for e in theorem_map["properties"] if e.get("lowering") != "verbatim"]
    assert len(base) == len(set(base))


def test_severity_is_only_claimed_where_reviewed(theorem_map):
    """Derived entries carry real proof obligations but no reviewed severity, so
    they must not claim CRITICAL/HIGH."""
    for e in theorem_map["properties"]:
        assert e["severity"] in _SEVERITIES, e["property_id"]
        if e.get("x_origin", "").startswith("derived"):
            assert e["severity"] == "MEDIUM", (
                f"{e['property_id']}: derived entry claims {e['severity']} without review"
            )


def test_every_entry_has_label_and_area(theorem_map):
    for e in theorem_map["properties"]:
        assert e.get("label", "").strip(), e["property_id"]
        assert e.get("bug_bounty_area", "").strip(), e["property_id"]
        assert e.get("type") == "invariant", e["property_id"]


# --- 4. the generated checklist overlay ------------------------------------

def test_checklist_entries_descend_from_a_mapped_theorem(theorem_map):
    base = {e["theorem"] for e in theorem_map["properties"] if e.get("lowering") != "verbatim"}
    for e in theorem_map["properties"]:
        if e.get("lowering") != "verbatim":
            continue
        assert e["theorem"] in base, f"{e['property_id']}: cites unmapped theorem {e['theorem']}"
        assert e.get("x_dataset_evidence", "").strip(), (
            f"{e['property_id']}: checklist entry without dataset evidence"
        )
        assert str(e["property_id"]).startswith("CHK-"), e["property_id"]


# --- 5. no proof status the exporter did not report ------------------------

def test_map_targets_are_proved_in_the_export(theorem_map, health):
    for e in theorem_map["properties"]:
        h = health.get(e["theorem"])
        assert h is not None, f"{e['property_id']}: {e['theorem']} absent from the health export"
        assert h["lean_status"] == "proved", f"{e['theorem']}: {h['lean_status']}"
        assert h["resolved"] is True and not h.get("export_error")


def test_export_reports_no_project_axioms(health):
    """EthTotal's own audit module reports the development axiom-free; the
    export must agree, or one of the two is wrong."""
    for name, h in health.items():
        assert not h.get("project_axioms"), f"{name}: non-builtin axioms {h['project_axioms']}"


# --- 6. the execution-layer anchor table -----------------------------------

_EL_ANCHORS = _ROOT / "data" / "anchor_map_execution.json"


@pytest.fixture(scope="module")
def el_anchors() -> dict:
    return _load(_EL_ANCHORS)


def test_every_el_anchor_is_verified_against_a_pinned_revision(el_anchors):
    """Rows carry the file and line the symbol was found at, so a spec bump that
    moves or renames a symbol is detectable rather than silently stale."""
    assert el_anchors["spec_source"] == "ethereum/execution-specs"
    assert len(el_anchors["spec_revision"]) == 40
    assert el_anchors["spec_fork"]
    for label, row in el_anchors["labels"].items():
        assert row["spec_doc"].endswith(".py"), label
        assert row["spec_symbol_line"] > 0, label
        assert row["spec_symbol_kind"] in {"function", "method"}, label
        assert row["why"].strip(), label
        for s in row["surfaces"]:
            assert s["line"] > 0 and s["file"].endswith(".py"), (label, s)


def test_every_mapped_label_has_an_el_anchor(theorem_map, el_anchors):
    for e in theorem_map["properties"]:
        assert e["label"] in el_anchors["labels"], (
            f"{e['property_id']}: label {e['label']!r} has no execution-specs anchor"
        )


def test_el_anchor_rows_cover_every_property_and_name_their_theorem(theorem_map, el_anchors):
    """Rows are keyed by (property_id, theorem): ids alone are only unique within
    a track — both checklists number generated items CHK-GEN-NN — so an id-only
    row would hand a consensus property an execution-layer anchor."""
    rows = {(r["property_id"], r["theorem"]) for r in el_anchors["defs"]}
    for e in theorem_map["properties"]:
        assert (e["property_id"], e["theorem"]) in rows, e["property_id"]
    for r in el_anchors["defs"]:
        assert r["theorem"].startswith("EthTotal."), r["property_id"]
        assert r["spec_reference"].startswith("execution-specs:"), r["property_id"]
        assert isinstance(r["matched_in_text"], bool)


def test_gasper_properties_never_pick_up_an_el_anchor():
    from speca_lean4.anchors import spec_reference_for_property
    el = _load(_EL_ANCHORS)
    shared_id = next(r["property_id"] for r in el["defs"]
                     if r["property_id"].startswith("CHK-GEN-"))
    assert spec_reference_for_property(shared_id, "GasperBeaconChain.Core.k_safety'") is None


def test_emitted_01e_records_the_anchor_provenance():
    """The audit source must be self-describing: a `#symbol` reference is not
    checkable without the spec revision it was verified against."""
    doc = _load(_ROOT / "outputs" / "20260812-ethtotal" / "01e_PARTIAL_ethtotal.json")
    tables = doc.get("spec_anchor_tables")
    assert tables, "emitted 01e does not record which anchor table it used"
    el = [t for t in tables if t["reference_prefix"] == "execution-specs"]
    assert len(el) == 1
    assert len(el[0]["spec_revision"]) == 40 and el[0]["spec_fork"]
    for p in doc["properties"]:
        assert p["spec_reference"].startswith("execution-specs:")
        assert p["spec_reference_basis"] in {"named-in-text", "label-default"}
        assert p["covers"] == p["spec_reference"].rsplit("#", 1)[-1]
