"""The `01e` property schema, mirrored on the plugin side.

The canonical contract lives in `speca` (`schemas/Property.schema.json` /
`scripts/orchestrator/schemas.py`). We keep a light, dependency-free mirror here
so the driver can emit and self-validate `01e` output without importing speca.

Core fields (must match speca exactly):
    property_id, text, type, assertion, severity, covers,
    reachability{classification, entry_points, attacker_controlled, bug_bounty_scope},
    bug_bounty_eligible, exploitability

Additive fields (Lean-provider only, never mutate a core field) per speca#88:
    lean_status, lean_artifact, kurtosis_test
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

STRIDE_TYPES = {
    "Spoofing", "Tampering", "Repudiation",
    "InformationDisclosure", "DenialOfService", "ElevationOfPrivilege",
}
SEVERITIES = {"Critical", "High", "Medium", "Low", "Informational"}
LEAN_STATUSES = {"proved", "unknown", "counterexample"}


@dataclass
class Reachability:
    classification: str
    entry_points: list[str] = field(default_factory=list)
    attacker_controlled: bool = False
    bug_bounty_scope: bool = False


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

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # drop additive fields that are unset to keep output clean
        for k in ("lean_status", "lean_artifact", "kurtosis_test"):
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

    for key in ("property_id", "text", "assertion", "exploitability"):
        v = require(key)
        if v is not None and not isinstance(v, str):
            problems.append(f"{key} must be a string")
    if not str(d.get("property_id", "")).strip():
        problems.append("property_id must be non-empty")

    t = require("type")
    if t is not None and t not in STRIDE_TYPES:
        problems.append(f"type {t!r} not in STRIDE set {sorted(STRIDE_TYPES)}")

    sev = require("severity")
    if sev is not None and sev not in SEVERITIES:
        problems.append(f"severity {sev!r} not in {sorted(SEVERITIES)}")

    if not isinstance(require("covers"), str):
        problems.append("covers must be a string (primary element id)")

    if not isinstance(d.get("bug_bounty_eligible"), bool):
        problems.append("bug_bounty_eligible must be a bool")

    r = require("reachability")
    if isinstance(r, dict):
        for key in ("classification", "entry_points", "attacker_controlled", "bug_bounty_scope"):
            if key not in r:
                problems.append(f"reachability missing field: {key}")
        if "entry_points" in r and not isinstance(r["entry_points"], list):
            problems.append("reachability.entry_points must be a list")
        for b in ("attacker_controlled", "bug_bounty_scope"):
            if b in r and not isinstance(r[b], bool):
                problems.append(f"reachability.{b} must be a bool")
    elif r is not None:
        problems.append("reachability must be an object")

    ls = d.get("lean_status")
    if ls is not None and ls not in LEAN_STATUSES:
        problems.append(f"lean_status {ls!r} not in {sorted(LEAN_STATUSES)}")

    return problems
