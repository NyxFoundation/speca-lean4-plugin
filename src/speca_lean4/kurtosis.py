"""Workstream E (issue #7) — the Kurtosis / speca#92 bridge.

Executable is the decidable-checker / constructive-witness layer of
gasper-lean4; it is the reproduction bridge between a proved `01e` property and
a runnable devnet assertion (design: docs/kurtosis-bridge.md).

Implemented here:

E1  `data/checker_map.json` links each theorem (hence every property lowered
    from it) to its Executable decidable Bool checker(s) (`slashedB`,
    `justifiedB`, `notSlashedB`, `goodQuorumAtB`, `qIntersectionWitnessB`),
    the proved iff-theorems certifying them, and — where one exists — the
    constructive witness (`accountable_safety_witnessB`,
    `k_accountable_safety_witnessB`, `plausible_liveness_construct_extension`)
    that builds a concrete scenario. `attach_checkers` surfaces `checker` /
    `witness` fields on the property.
E3  `emit_kurtosis` writes one `kurtosis_test` fixture SCAFFOLD per
    checker-linked property under `<out-dir>/<label>/<property_id>/`
    (devnet config placeholder + assertion stub referencing the checker) and
    populates the property's `kurtosis_test` path.
E6  label-matched findings from the ethereum-vuln-dataset
    (`data/evidence_seeds.json`: `pre_fix_code` / `files_changed` excerpts)
    are attached to the fixture as implementation-linked evidence seeding the
    reproduction target.

Honesty invariants:
- fixtures are SCAFFOLDS (`"scaffold": true`, verdict null) — nothing here
  claims a runnable devnet; bring-up and the backend handoff (E2/E5) are
  blocked on speca#92 / NyxFoundation/kurtosis-harness and are design-only.
- `kurtosis_test` is non-null ONLY where a real Executable checker exists;
  theorems absent from checker_map.json (the pure-arithmetic / definitional
  Core results) keep `kurtosis_test` null and get no fixture.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKER_MAP = _REPO_ROOT / "data" / "checker_map.json"
DEFAULT_EVIDENCE_SEEDS = _REPO_ROOT / "data" / "evidence_seeds.json"

HARNESS = "NyxFoundation/kurtosis-harness"

_ME_SUFFIX = re.compile(r"-me\d+$")


def load_checker_map(path: str | Path = DEFAULT_CHECKER_MAP) -> dict[str, dict[str, Any]]:
    """theorem name -> {checkers, correctness, witness, role} (E1)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("checkers", {})


def load_evidence_seeds(path: str | Path = DEFAULT_EVIDENCE_SEEDS) -> list[dict[str, Any]]:
    """Curated ethereum-vuln-dataset seeds (E6)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("seeds", [])


def base_property_id(property_id: str) -> str:
    """Strip the B1 must-establish suffix: PROP-x-me3 -> PROP-x."""
    return _ME_SUFFIX.sub("", property_id)


def theorem_index(theorem_map: dict[str, Any]) -> dict[str, str]:
    """theorem_map -> {base property_id: theorem}."""
    return {
        e["property_id"]: e["theorem"]
        for e in theorem_map.get("properties", [])
    }


def safe_label(label: str) -> str:
    """Filesystem-safe form of a dataset label (':' is not portable in paths)."""
    return label.replace(":", "--")


def attach_checkers(
    props: list[dict[str, Any]],
    theorem_map: dict[str, Any],
    checker_map: dict[str, dict[str, Any]],
) -> int:
    """E1: surface `checker` / `witness` on every property whose theorem has a
    real Executable counterpart. In place; returns the number linked.

    `checker` is the primary decidable Bool checker (first of the entry's
    `checkers`); `witness` the constructive witness when one exists. Properties
    of theorems absent from the map are left untouched (no checker claim).
    """
    by_base = theorem_index(theorem_map)
    linked = 0
    for p in props:
        theorem = by_base.get(base_property_id(p["property_id"]))
        entry = checker_map.get(theorem) if theorem else None
        if not entry or not entry.get("checkers"):
            continue
        p["checker"] = entry["checkers"][0]
        if entry.get("witness"):
            p["witness"] = entry["witness"]
        linked += 1
    return linked


def _seeds_for_label(seeds: list[dict[str, Any]], label: str | None) -> list[dict[str, Any]]:
    return [s for s in seeds if label and s.get("label") == label]


def _devnet_scaffold(prop: dict[str, Any]) -> dict[str, Any]:
    """E3 devnet config PLACEHOLDER. Explicitly not runnable (E2 is blocked)."""
    return {
        "scaffold": True,
        "status": (
            "SCAFFOLD — placeholder only. Devnet bring-up (client matrix, network "
            "params, scenario driving from the constructive witness) is speca#92 / "
            "kurtosis-harness territory (issue #7 E2, blocked); design in "
            "docs/kurtosis-bridge.md."
        ),
        "harness": HARNESS,
        "property_id": prop["property_id"],
        "label": prop.get("label"),
        "devnet": {
            "participants": None,
            "network_params": None,
            "scenario": None
        },
    }


def _assertion_scaffold(
    prop: dict[str, Any],
    theorem: str,
    entry: dict[str, Any],
    seeds: list[dict[str, Any]],
) -> dict[str, Any]:
    """E3 assertion STUB: references the Executable checker and carries the
    E5 handoff record shape (verdict null — nothing has run)."""
    return {
        "scaffold": True,
        "status": (
            "SCAFFOLD — assertion stub, not an executed test. The checker names a "
            "real, proved decidable function in gasper-lean4 Executable; wiring it "
            "to observed devnet state is the speca#92 backend's job (E5, blocked)."
        ),
        "property_id": prop["property_id"],
        "theorem": theorem,
        "label": prop.get("label"),
        "severity": prop.get("severity"),
        "lean_status": prop.get("lean_status"),
        "lean_artifact": prop.get("lean_artifact"),
        "assertion": prop.get("assertion"),
        "checker": {
            "primary": entry["checkers"][0],
            "all": entry["checkers"],
            "correctness": entry.get("correctness", []),
            "witness": entry.get("witness"),
            "role": entry.get("role", ""),
        },
        "handoff": {
            "property_id": prop["property_id"],
            "verdict": None,
            "harness": HARNESS,
            "artifact_path": None,
            "logs_path": None,
        },
        "evidence_seeds": seeds,
    }


def emit_kurtosis(
    props: list[dict[str, Any]],
    theorem_map: dict[str, Any],
    checker_map: dict[str, dict[str, Any]],
    out_dir: str | Path,
    seeds: list[dict[str, Any]] | None = None,
) -> list[Path]:
    """E3: write one fixture scaffold per checker-linked property under
    `<out_dir>/<safe_label>/<property_id>/` and set the property's
    `kurtosis_test` path. Returns the written assertion-stub paths.

    Properties without a real checker are skipped and keep kurtosis_test null.
    """
    out_dir = Path(out_dir)
    by_base = theorem_index(theorem_map)
    seeds = seeds or []
    written: list[Path] = []
    for p in props:
        theorem = by_base.get(base_property_id(p["property_id"]))
        entry = checker_map.get(theorem) if theorem else None
        if not entry or not entry.get("checkers"):
            continue  # honest: no checker -> no fixture, kurtosis_test stays null
        label_dir = safe_label(p.get("label") or "unlabeled")
        fdir = out_dir / label_dir / p["property_id"]
        fdir.mkdir(parents=True, exist_ok=True)

        devnet_fp = fdir / "devnet.scaffold.json"
        devnet_fp.write_text(
            json.dumps(_devnet_scaffold(p), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        assertion_fp = fdir / "assertion.scaffold.json"
        assertion_fp.write_text(
            json.dumps(
                _assertion_scaffold(p, theorem, entry, _seeds_for_label(seeds, p.get("label"))),
                indent=2, ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )
        p["kurtosis_test"] = _record_path(assertion_fp)
        written.append(assertion_fp)
    return written


def _record_path(fp: Path) -> str:
    """POSIX path recorded in `kurtosis_test` — cwd-relative when possible."""
    try:
        return fp.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return fp.as_posix()
