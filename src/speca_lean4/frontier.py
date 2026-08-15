"""Proof-DAG evidence and audit-frontier helpers.

The Lean theorem conclusion is not sufficient audit material when a proof uses
a stronger local lemma.  This module keeps the transitive, project-local
theorem closure available to the property generator while deliberately
omitting definitions and library constants that have no health record.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from .health import TheoremHealth


def _obligations(th: TheoremHealth) -> list[dict[str, str]]:
    return [
        {
            "name": str(h.get("name", "")),
            "type": str(h.get("type", "")),
            "head": str(h.get("head", "")),
            "class": str(h.get("class", "")),
        }
        for h in th.hypotheses
    ]


def proof_closure(health: dict[str, TheoremHealth], root: str) -> list[dict[str, Any]]:
    """Return the transitive health-record closure below ``root``.

    ``proof_constants`` also contains definitions, constructors and builtins;
    those are intentionally not emitted as theorem facts because the exporter
    has no theorem-health record for them.  The resulting list is deterministic
    and records only theorem/lemma nodes that can carry a semantic conclusion.
    """
    root_th = health.get(root)
    if root_th is None:
        return []
    queue: deque[str] = deque(root_th.proof_constants)
    seen: set[str] = {root}
    names: list[str] = []
    while queue:
        name = queue.popleft()
        if name in seen:
            continue
        seen.add(name)
        th = health.get(name)
        if th is None:
            continue
        names.append(name)
        queue.extend(th.proof_constants)

    index = {name: i + 1 for i, name in enumerate(names)}
    out: list[dict[str, Any]] = []
    for name in names:
        th = health[name]
        dep_names = [d for d in th.proof_constants if d in index]
        out.append({
            "fact_id": f"L{index[name]:03d}",
            "theorem": name,
            "statement": th.statement,
            "conclusion": th.conclusion,
            "obligations": _obligations(th),
            "depends_on": [f"L{index[d]:03d}" for d in dep_names],
            "proof_constants": list(th.proof_constants),
            "lean_status": th.lean_status,
        })
    return out


def proof_evidence(root: str, health: dict[str, TheoremHealth]) -> dict[str, Any] | None:
    """Build the canonical root-plus-closure evidence payload."""
    th = health.get(root)
    if th is None or not th.statement:
        return None
    closure = proof_closure(health, root)
    reachable: set[str] = set(th.proof_constants)
    for rec in closure:
        reachable.update(rec["proof_constants"])
    theorem_records = {rec["theorem"] for rec in closure}
    omitted = sorted(x for x in reachable if x not in theorem_records and x != root)
    return {
        "theorem": root,
        "statement": th.statement,
        "conclusion": th.conclusion,
        "obligations": _obligations(th),
        "must_establish": [h for h in _obligations(th) if h["class"] == "must-establish"],
        "referenced_defs_expanded": th.referenced_defs_expanded,
        "proof_constants": list(th.proof_constants),
        "proof_source": th.proof_source,
        "doc_string": th.doc_string,
        "lean_status": th.lean_status,
        "proof_closure": closure,
        "proof_dependency_stats": {
            "theorem_records": len(closure),
            "reachable_constants": len(reachable),
            "unresolved_or_non_theorem_constants": len(omitted),
        },
        "unresolved_or_non_theorem_constants": omitted,
    }
