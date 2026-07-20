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
plus, from issue #7 (workstream E): checker, witness — the Executable
decidable checker / constructive witness linked via data/checker_map.json.
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
# Direct statuses come from the Lean exporter for mechanically lowered
# properties. A hand-written (`lowering: "verbatim"`) stage-2 checklist
# property never claims a proof status of its own text: it emits the derived
# `descends-from-<parent status>` instead (honesty invariant 5,
# tests/test_honesty.py) — the parent theorem's status stays readable, the
# unverified text never says plain "proved". The two vocabularies are
# disjoint, so verbatim vs mechanical is decidable from `lean_status` alone.
DIRECT_LEAN_STATUSES = {"proved", "unknown", "counterexample"}
DESCENDED_LEAN_STATUSES = {f"descends-from-{s}" for s in DIRECT_LEAN_STATUSES}
LEAN_STATUSES = DIRECT_LEAN_STATUSES | DESCENDED_LEAN_STATUSES
PROOF_PROVENANCES = {"automated", "hand-written", "unknown"}
TYPE_CONSISTENCY = {"ok", "mismatch", "unchecked"}


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
    # A3+ (issue #16): recursively expanded gasper-local definitions the
    # statement references — [{name, kind, pp}], bounded on the Lean side
    # (depth 2 / 24 defs; see lean/SpecaExport/Basic.lean). Additive next to
    # the names-only lean_referenced_defs.
    lean_referenced_defs_expanded: list[dict] | None = None
    lean_axioms: list[str] | None = None
    lean_proof_provenance: str | None = None
    lean_proof_code: str | None = None
    # B1/B2: the one must-establish precondition this property audits, and the
    # conclusion the theorem guarantees once every precondition is preserved.
    lean_precondition: str | None = None
    lean_conclusion: str | None = None
    # B5: type-consistency gate verdict ("ok" | "mismatch" | "unchecked")
    lean_type_consistency: str | None = None
    # A7: verbatim declaration source (term/tactic code and comments; since
    # A7+/issue #17 including the contiguous leading comment block)
    lean_proof_source: str | None = None
    # A7+ (issue #17): the declaration's docstring; None (key dropped) when
    # the theorem has none — absent stays absent, never fabricated
    lean_doc_string: str | None = None
    # C5: spec anchor derived from the dataset label vocabulary
    spec_reference: str | None = None
    # E1 (issue #7): Executable decidable Bool checker / constructive witness
    # for this property's theorem (from data/checker_map.json). Non-null only
    # where a REAL Executable counterpart exists.
    checker: str | None = None
    witness: str | None = None

    _ADDITIVE_FIELDS = (
        "lean_status", "lean_artifact", "kurtosis_test", "label",
        "lean_statement", "lean_hypotheses", "lean_must_establish",
        "lean_referenced_defs", "lean_referenced_defs_expanded",
        "lean_axioms", "lean_proof_provenance",
        "lean_proof_code", "lean_precondition", "lean_conclusion",
        "lean_type_consistency", "lean_proof_source", "lean_doc_string",
        "spec_reference", "checker", "witness",
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

    for key in ("lean_precondition", "lean_conclusion", "lean_proof_source",
                "lean_doc_string", "spec_reference", "kurtosis_test",
                "checker", "witness"):
        v = d.get(key)
        if v is not None and not isinstance(v, str):
            problems.append(f"{key} must be a string")

    lrde = d.get("lean_referenced_defs_expanded")
    if lrde is not None:
        if not isinstance(lrde, list):
            problems.append("lean_referenced_defs_expanded must be a list")
        else:
            for item in lrde:
                if not isinstance(item, dict) or not {"name", "kind", "pp"} <= set(item):
                    problems.append(
                        "lean_referenced_defs_expanded items must be "
                        "{name, kind, pp} objects"
                    )
                    break

    ltc = d.get("lean_type_consistency")
    if ltc is not None and ltc not in TYPE_CONSISTENCY:
        problems.append(f"lean_type_consistency {ltc!r} not in {sorted(TYPE_CONSISTENCY)}")

    return problems
