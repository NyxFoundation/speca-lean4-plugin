"""C3/C4 (issue #5) — the def -> spec-symbol -> client-code-symbol anchor table.

`data/anchor_map.json` is the single source of truth for spec/code anchoring:

- ``labels``   maps each ethereum-vuln-dataset label (consensus-specs section
  name, ``docs/label_design.md``) to its consensus-specs doc, its primary
  pyspec ``process_*`` symbol, and a best-effort list of client-code symbols.
  Client rows are honest: ``status`` is either ``verified-<date>`` (confirmed
  by GitHub code search on that date) or ``todo`` (unmapped, never fabricated).
- ``defs``     maps each gasper-lean4 target theorem (one row per
  ``theorem_map.json`` entry) to its label, spec symbol, and spec reference.
  Per-def client-code resolution is label-level for now: finer anchoring needs
  the ``@[speca_spec]`` annotations in gasper-lean4 (C1/C2 — blocked on
  issue #9 G2; see ``docs/spec-annotation.md``).

C4: `mapping.py` derives ``spec_reference`` and the ``covers`` fallback from
this table (falling back to its small inline C5 table only when the data file
is unavailable, e.g. a non-editable install without the repo checkout) — never
from prose guesses.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANCHOR_MAP = _REPO_ROOT / "data" / "anchor_map.json"


def anchor_map_path() -> Path:
    """Default location of the anchor table (repo checkout layout)."""
    return _ANCHOR_MAP


@lru_cache(maxsize=8)
def _load(path_str: str) -> dict[str, Any] | None:
    p = Path(path_str)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_anchor_map(path: str | Path | None = None) -> dict[str, Any] | None:
    """Load the anchor table; None when the data file is unavailable."""
    return _load(str(path or _ANCHOR_MAP))


def spec_anchor(label: str | None, path: str | Path | None = None) -> tuple[str, str] | None:
    """(spec_doc, spec_symbol) for a dataset label, from the anchor table."""
    m = load_anchor_map(path)
    if not m or not label:
        return None
    row = (m.get("labels") or {}).get(label)
    if not row:
        return None
    return str(row["spec_doc"]), str(row["spec_symbol"])


def spec_reference(label: str | None, path: str | Path | None = None) -> str | None:
    """Canonical ``consensus-specs:<doc>#<symbol>`` anchor for a label."""
    a = spec_anchor(label, path)
    if a is None:
        return None
    return f"consensus-specs:{a[0]}#{a[1]}"


def spec_symbol(label: str | None, path: str | Path | None = None) -> str | None:
    """Primary pyspec ``process_*`` symbol for a label."""
    a = spec_anchor(label, path)
    return a[1] if a else None


def client_symbols(
    label: str | None,
    verified_only: bool = False,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Best-effort client-code rows for a label ([] when unknown).

    Each row: {client, repo, symbol, path, status, note}. ``status`` is
    ``verified-<date>`` or ``todo`` — callers that need a real symbol should
    pass ``verified_only=True`` and treat [] as honestly-unmapped.
    """
    m = load_anchor_map(path)
    if not m or not label:
        return []
    row = (m.get("labels") or {}).get(label) or {}
    out = [dict(c) for c in row.get("client_code", [])]
    if verified_only:
        out = [c for c in out if str(c.get("status", "")).startswith("verified")]
    return out


def anchor_for_def(lean_def: str, path: str | Path | None = None) -> dict[str, Any] | None:
    """The ``defs`` row for a fully-qualified gasper-lean4 theorem name."""
    m = load_anchor_map(path)
    if not m:
        return None
    for row in m.get("defs", []):
        if row.get("lean_def") == lean_def:
            return dict(row)
    return None
