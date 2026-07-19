"""Stage B — parse the `speca-export` proof-health JSON into a name -> record map.

The Lean executable emits:

    {
      "project": "GasperBeaconChain",
      "plugin": "speca-lean4-plugin",
      "theorems": [
        {"name": "...", "resolved": true, "lean_status": "proved",
         "sorry_free": true, "choice_free": true, "native_free": true,
         "module": "GasperBeaconChain.Executable.Slashing"},
        ...
      ]
    }

`lean_status` is decided in Lean (`proved` iff resolved and sorry-free). Here we
only index it and expose a helper that falls back to `unknown` for any theorem
the exporter did not report (e.g. a name typo in theorem_map.json — surfaced,
never silently dropped).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TheoremHealth(dict):
    """A single proof-health record (thin dict wrapper for attribute-ish access)."""

    @property
    def lean_status(self) -> str:
        # Honesty guard (H1, issue #10): an unresolved record can never certify
        # "proved", whatever its lean_status field claims. The Lean exporter
        # only emits proved for resolved theorems; this guards doctored or
        # hand-edited health inputs on the Python side too.
        if not self.resolved:
            return "unknown"
        return self.get("lean_status", "unknown")

    @property
    def module(self) -> str:
        return self.get("module", "")

    @property
    def resolved(self) -> bool:
        return bool(self.get("resolved", False))

    @property
    def statement(self) -> str:
        return self.get("statement", "")

    @property
    def conclusion(self) -> str:
        """Pretty-printed telescope body — the Q the theorem guarantees."""
        return self.get("conclusion", "")

    @property
    def hypotheses(self) -> list[dict]:
        return self.get("hypotheses", [])

    @property
    def must_establish(self) -> list[dict]:
        return [h for h in self.hypotheses if h.get("class") == "must-establish"]

    @property
    def depend_allowed(self) -> list[dict]:
        return [h for h in self.hypotheses if h.get("class") == "depend-allowed"]

    @property
    def referenced_constants(self) -> list[str]:
        return self.get("referenced_constants", [])

    @property
    def referenced_defs_expanded(self) -> list[dict]:
        """A3+ (issue #16): recursively expanded gasper-local definitions,
        [{name, kind, pp}]. Bounded on the Lean side (depth/total caps in
        SpecaExport.Basic); [] on pre-#16 health data."""
        return self.get("referenced_defs_expanded", [])

    @property
    def gasper_axioms(self) -> list[str]:
        return self.get("gasper_axioms", [])

    @property
    def proof_provenance(self) -> str:
        return self.get("proof_provenance", "unknown")

    @property
    def proof_code(self) -> str:
        return self.get("proof_code", "")

    @property
    def proof_constants(self) -> list[str]:
        """Gasper-local constants used by the proof term (proof-DAG edges, B3)."""
        return self.get("proof_constants", [])

    @property
    def proof_source(self) -> str:
        """Verbatim declaration source slice (A7); "" when unavailable.

        Since A7+ (issue #17) the slice includes the contiguous leading
        comment block (docstring + adjacent comments) above the declaration."""
        return self.get("proof_source", "")

    @property
    def doc_string(self) -> str:
        """A7+ (issue #17): the declaration's docstring; "" when the theorem
        has none (honest — never fabricated) or on pre-#17 health data."""
        return self.get("doc_string", "")


def load_health(path: str | Path) -> dict[str, TheoremHealth]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return index_health(data)


def index_health(data: dict[str, Any]) -> dict[str, TheoremHealth]:
    out: dict[str, TheoremHealth] = {}
    for rec in data.get("theorems", []):
        name = rec.get("name")
        if name:
            out[name] = TheoremHealth(rec)
    return out


def status_for(health: dict[str, TheoremHealth], theorem: str) -> tuple[str, str]:
    """Return (lean_status, module) for a theorem, defaulting to unknown/"" if absent."""
    rec = health.get(theorem)
    if rec is None:
        return "unknown", ""
    return rec.lean_status, rec.module


def unresolved_targets(
    health: dict[str, TheoremHealth], theorems: list[str]
) -> list[str]:
    """H1/CI gate: target names with no resolved health record.

    A non-empty result means at least one theorem_map target did not resolve in
    Lean (typo, rename, or removed declaration). The CI lean job fails on this
    (ci.yml smoke step asserts every target resolved); on the Python side the
    corresponding properties are emitted lean_status=unknown, never dropped and
    never upgraded.
    """
    out: list[str] = []
    for t in theorems:
        rec = health.get(t)
        if rec is None or not rec.resolved:
            out.append(t)
    return out


def health_for(health: dict[str, TheoremHealth], theorem: str) -> TheoremHealth:
    """Return the full TheoremHealth record, defaulting gracefully for missing theorems."""
    rec = health.get(theorem)
    if rec is None:
        return TheoremHealth({"lean_status": "unknown", "module": ""})
    return rec
