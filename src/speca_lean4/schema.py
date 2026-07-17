"""The `01e` property schema, mirrored on the plugin side.

The canonical contract lives in `speca` (`schemas/Property.schema.json` /
`scripts/orchestrator/schemas.py`). We keep a light, dependency-free mirror here
so the driver can emit and self-validate `01e` output without importing speca.

Core fields (must match speca exactly — note `reachability.bug_bounty_scope`
is a STRING in the canonical Pydantic model, default "conditional"):
    property_id, text, type, assertion, severity, covers,
    reachability{classification, entry_points, attacker_controlled, bug_bounty_scope},
    bug_bounty_eligible, exploitability

Value vocabulary is aligned with the reference corpus
`bench-rq2a-20260508-speca` (426-file release, 16 x 01e, 186 properties):
    type            "invariant" (all 186)
    severity        CRITICAL | HIGH | MEDIUM  (95/81/10)
    classification  external-reachable | internal  (178/8)
    exploitability  external-attack | local-attack (178/8)
    bug_bounty_scope "in-scope" (186)  -- we also emit out-of-scope/conditional
    entry_points    CallbackHandler | FunctionCall | ProgramEntry | Initialization

Additive fields (Lean-provider only, never mutate a core field) per speca#88:
    lean_status, lean_artifact, kurtosis_test
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

BENCHMARK_TYPE = "invariant"
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}
CLASSIFICATIONS = {"external-reachable", "internal"}
EXPLOITABILITIES = {"external-attack", "local-attack"}
SCOPE_VALUES = {"in-scope", "out-of-scope", "conditional"}
ENTRY_POINTS = {"CallbackHandler", "FunctionCall", "ProgramEntry", "Initialization"}
LEAN_STATUSES = {"proved", "unknown", "counterexample"}
PROOF_PROVENANCES = {"automated", "hand-written", "unknown"}


@dataclass
class Reachability:
    classification: str
    entry_points: list[str] = field(default_factory=list)
    attacker_controlled: bool = False
    bug_bounty_scope: str = "conditional"


@dataclass
class Property:
    property_id: str
    text: str
    type: str
    assertion: str
    severity: str
    covers: str
    reachability: Reachability
    bug_bounty_eligible: bool
    exploitability: str
    # additive (Lean provider)
    lean_status: str | None = None
    lean_artifact: str | None = None
    kurtosis_test: str | None = None
    label: str | None = None
    lean_statement: str | None = None
    lean_hypotheses: list[dict] | None = None
    lean_must_establish: list[str] | None = None
    lean_referenced_defs: list[str] | None = None
    lean_axioms: list[str] | None = None
    lean_proof_provenance: str | None = None
    lean_proof_code: str | None = None

    _ADDITIVE_FIELDS = (
        "lean_status", "lean_artifact", "kurtosis_test", "label",
        "lean_statement", "lean_hypotheses", "lean_must_establish",
        "lean_referenced_defs", "lean_axioms", "lean_proof_provenance",
        "lean_proof_code",
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("_ADDITIVE_FIELDS", None)
        for k in self._ADDITIVE_FIELDS:
            if d.get(k) is None:
                d.pop(k, None)
        return d


def validate_property(d: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems; empty list means valid."""
    problems: list[str] = []

    def require(key: str) -> Any:
        if key not in d:
            problems.append(f"missing required field: {key}")
            return None
        return d[key]

    for key in ("property_id", "text", "assertion"):
        v = require(key)
        if v is not None and not isinstance(v, str):
            problems.append(f"{key} must be a string")
    if not str(d.get("property_id", "")).strip():
        problems.append("property_id must be non-empty")

    t = require("type")
    if t is not None and t != BENCHMARK_TYPE:
        problems.append(f"type {t!r} != {BENCHMARK_TYPE!r} (benchmark vocabulary)")

    sev = require("severity")
    if sev is not None and sev not in SEVERITIES:
        problems.append(f"severity {sev!r} not in {sorted(SEVERITIES)}")

    ex = require("exploitability")
    if ex is not None and ex not in EXPLOITABILITIES:
        problems.append(f"exploitability {ex!r} not in {sorted(EXPLOITABILITIES)}")

    if not isinstance(require("covers"), str):
        problems.append("covers must be a string (primary element id)")

    if not isinstance(d.get("bug_bounty_eligible"), bool):
        problems.append("bug_bounty_eligible must be a bool")

    r = require("reachability")
    if isinstance(r, dict):
        for key in ("classification", "entry_points", "attacker_controlled", "bug_bounty_scope"):
            if key not in r:
                problems.append(f"reachability missing field: {key}")
        if r.get("classification") is not None and "classification" in r \
                and r["classification"] not in CLASSIFICATIONS:
            problems.append(
                f"reachability.classification {r['classification']!r} not in {sorted(CLASSIFICATIONS)}"
            )
        eps = r.get("entry_points")
        if "entry_points" in r and not isinstance(eps, list):
            problems.append("reachability.entry_points must be a list")
        elif isinstance(eps, list):
            for ep in eps:
                if ep not in ENTRY_POINTS:
                    problems.append(f"entry_point {ep!r} not in {sorted(ENTRY_POINTS)}")
        if "attacker_controlled" in r and not isinstance(r["attacker_controlled"], bool):
            problems.append("reachability.attacker_controlled must be a bool")
        bbs = r.get("bug_bounty_scope")
        if "bug_bounty_scope" in r and bbs not in SCOPE_VALUES:
            problems.append(
                f"reachability.bug_bounty_scope {bbs!r} not in {sorted(SCOPE_VALUES)} "
                "(string per canonical schema, not bool)"
            )
    elif r is not None:
        problems.append("reachability must be an object")

    ls = d.get("lean_status")
    if ls is not None and ls not in LEAN_STATUSES:
        problems.append(f"lean_status {ls!r} not in {sorted(LEAN_STATUSES)}")

    lbl = d.get("label")
    if lbl is not None and not isinstance(lbl, str):
        problems.append("label must be a string")

    lstmt = d.get("lean_statement")
    if lstmt is not None and not isinstance(lstmt, str):
        problems.append("lean_statement must be a string")

    lpp = d.get("lean_proof_provenance")
    if lpp is not None and lpp not in PROOF_PROVENANCES:
        problems.append(f"lean_proof_provenance {lpp!r} not in {sorted(PROOF_PROVENANCES)}")

    lhyp = d.get("lean_hypotheses")
    if lhyp is not None and not isinstance(lhyp, list):
        problems.append("lean_hypotheses must be a list")

    lme = d.get("lean_must_establish")
    if lme is not None and not isinstance(lme, list):
        problems.append("lean_must_establish must be a list")

    return problems
