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
        return self.get("lean_status", "unknown")

    @property
    def module(self) -> str:
        return self.get("module", "")

    @property
    def resolved(self) -> bool:
        return bool(self.get("resolved", False))


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
