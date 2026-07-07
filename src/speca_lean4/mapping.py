"""Stage C — map gasper-lean4 theorems onto `01e` properties.

`build_properties` is a pure function (theorem_map + health + scope + subgraphs)
-> list of `01e` property dicts, so it is fully unit-testable without Lean.

The theorem -> implementation-invariant "lowering" is data-driven: every field
except `covers`/`reachability`/`lean_*` comes verbatim from `theorem_map.json`.
That is where the granularity is tuned to match the fusaka `01e` benchmark
(see the impl plan §3/§4) without recompiling Lean.
"""

from __future__ import annotations

from typing import Any

from .health import TheoremHealth, status_for
from .schema import Property, Reachability


def _flatten_strings(obj: Any) -> list[str]:
    """Collect all string leaves of a nested dict/list (for permissive scope search)."""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_flatten_strings(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_flatten_strings(v))
    return out


def _area_in_scope(scope: dict[str, Any], area: str) -> bool:
    """Best-effort: is `area` (e.g. 'consensus/slashing') covered by BUG_BOUNTY_SCOPE.json?

    Conservative — returns True only if a scope string mentions the area or its
    leading component (`consensus`). Unknown scope shape -> False (safer default;
    a false negative just marks a property out-of-scope rather than over-claiming).
    """
    if not scope:
        return False
    tokens = [t for t in area.lower().replace("/", " ").split() if t]
    haystack = " ".join(_flatten_strings(scope)).lower()
    # require the domain token (first) to appear; a specific sub-token boosts confidence
    return bool(tokens) and tokens[0] in haystack


def _scope_value(scope: dict[str, Any], in_scope: bool) -> str:
    """Canonical `reachability.bug_bounty_scope` STRING (schema default: conditional)."""
    if not scope:
        return "conditional"
    return "in-scope" if in_scope else "out-of-scope"


def _resolve_covers(covers_hint: list[str], subgraphs: list[dict] | None) -> str:
    """Match a hint against 01b subgraph element ids; fall back to the first hint.

    Subgraph matching is intentionally simple for M0: first element whose id or
    label contains a hint token wins. Refined matching is future work (impl plan
    §3, `covers`). Returning the raw hint keeps output schema-valid meanwhile.
    """
    if subgraphs:
        hints = [h.lower() for h in covers_hint]
        for sg in subgraphs:
            elements = sg.get("elements") or sg.get("nodes") or []
            for el in elements:
                eid = str(el.get("id", ""))
                label = str(el.get("label", el.get("name", ""))).lower()
                if any(h in label or h in eid.lower() for h in hints):
                    return eid or label
    return covers_hint[0] if covers_hint else "UNRESOLVED"


def _lean_artifact(gasper_source: str, gasper_ref: str, module: str, theorem: str) -> str:
    short = theorem.rsplit(".", 1)[-1]
    if module:
        path = module.replace(".", "/") + ".lean"
        return f"{gasper_source}@{gasper_ref}:{path}#{short}"
    return f"{gasper_source}@{gasper_ref}#{short}"


def build_property(
    entry: dict[str, Any],
    health: dict[str, TheoremHealth],
    scope: dict[str, Any],
    subgraphs: list[dict] | None,
    gasper_source: str,
    gasper_ref: str,
) -> Property:
    theorem = entry["theorem"]
    lean_status, module = status_for(health, theorem)

    area = entry.get("bug_bounty_area", "")
    in_scope = _area_in_scope(scope, area)
    liveness_only = bool(entry.get("liveness_only", False))
    attacker_controlled = bool(entry.get("attacker_controlled", False))

    # Vocabulary aligned with bench-rq2a-20260508-speca (see schema.py):
    #   classification  external-reachable | internal
    #   exploitability  external-attack | local-attack
    #   entry_points    CallbackHandler | FunctionCall | ProgramEntry | Initialization
    reach = Reachability(
        classification="external-reachable" if attacker_controlled else "internal",
        entry_points=[str(x) for x in entry.get("entry_points", [])],
        attacker_controlled=attacker_controlled,
        bug_bounty_scope=_scope_value(scope, in_scope),
    )
    exploitability = entry.get(
        "exploitability",
        "external-attack" if attacker_controlled else "local-attack",
    )

    return Property(
        property_id=entry["property_id"],
        text=entry["text"],
        type=entry.get("type", "invariant"),
        assertion=entry["assertion"],
        severity=str(entry["severity"]).upper(),
        covers=_resolve_covers(entry.get("covers_hint", []), subgraphs),
        reachability=reach,
        bug_bounty_eligible=(in_scope and not liveness_only),
        exploitability=exploitability,
        lean_status=lean_status,
        lean_artifact=_lean_artifact(gasper_source, gasper_ref, module, theorem),
        kurtosis_test=None,  # filled by speca#88 task 5 (Kurtosis fixture generation)
    )


def build_properties(
    theorem_map: dict[str, Any],
    health: dict[str, TheoremHealth],
    scope: dict[str, Any],
    subgraphs: list[dict] | None = None,
    gasper_ref: str | None = None,
) -> list[dict[str, Any]]:
    source = theorem_map.get("gasper_source", "NyxFoundation/gasper-lean4")
    ref = gasper_ref or theorem_map.get("gasper_ref", "main")
    props: list[dict[str, Any]] = []
    for entry in theorem_map.get("properties", []):
        prop = build_property(entry, health, scope, subgraphs, source, ref)
        props.append(prop.to_dict())
    return props
