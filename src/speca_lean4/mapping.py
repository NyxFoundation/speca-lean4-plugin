"""Stage C — lower gasper-lean4 theorems onto `01e` properties.

`build_properties` is a pure function (theorem_map + health + scope + subgraphs)
-> list of `01e` property dicts, so it is fully unit-testable without Lean.

Lowering semantics (issue #4, workstream B):

B1  A theorem lowers to N properties, one per **must-establish** hypothesis of
    its Lean statement (from the A2 telescope classification) — NOT one per
    theorem. Depend-allowed hypotheses (typeclass plumbing, model parameters,
    world/model assumptions) are context, never invariants. When the health
    data is unenriched, or the theorem has no must-establish hypothesis (e.g.
    the Iff-shaped decidable-checker theorems), it lowers 1:1 as before.
B2  Each property is a neutral audit result: "implementation must preserve
    [P]; if so, <theorem> guarantees [Q]" — where P is the pretty-printed
    must-establish hypothesis and Q the pretty-printed conclusion, both
    extracted from Lean, not hand-written.
B3  Severity derives from proof-DAG position: a top-level conclusion keeps the
    severity calibrated in theorem_map.json; a lemma inherits the maximum
    severity of the target theorems whose proofs depend on it (edges from the
    exporter's gasper-local `proof_constants`). Inheritance is upward-only —
    nothing is ever downgraded, and theorem_map severities are never edited to
    game a distribution.
B5  Type-consistency gate: the head constant of each lowered precondition
    (exported per-hypothesis by Lean) must be among the theorem's gasper-local
    referenced constants (A3). Verdict per property: "ok" | "mismatch" |
    "unchecked" (non-gasper heads such as `Ne`/`Nat.lt`, or unenriched data,
    are unchecked). Mismatches are flagged, not silently dropped.

`theorem_map.json` stays the *tuning overlay* — severity calibration, covers
hints, scope/reachability, labels, shards — layered on top of the
Lean-extracted statement/hypotheses. It no longer carries the decomposition
semantics themselves.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .health import TheoremHealth, status_for, health_for

from .schema import Property, Reachability

_GASPER_PREFIX = "GasperBeaconChain."

_SEVERITY_RANK = {"INFORMATIONAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

# C5: the ethereum-vuln-dataset `label` vocabulary is grounded in the
# consensus-specs section names (docs/label_design.md), so both the spec
# anchor and the primary pyspec symbol derive mechanically from the label —
# no prose judgment. Only the labels used by our FFG target set are mapped;
# growing the target set means growing this table, not guessing.
_LABEL_SPEC = {
    "beacon-chain:justification-and-finality":
        ("specs/phase0/beacon-chain.md", "process_justification_and_finalization"),
    "beacon-chain:slashing":
        ("specs/phase0/beacon-chain.md", "process_slashings"),
    "beacon-chain:effective-balance-updates":
        ("specs/phase0/beacon-chain.md", "process_effective_balance_updates"),
    "beacon-chain:attestation":
        ("specs/phase0/beacon-chain.md", "process_attestation"),
}


def _spec_reference(label: str | None) -> str | None:
    """C5: consensus-specs anchor derived from the dataset label."""
    if not label or label not in _LABEL_SPEC:
        return None
    doc, symbol = _LABEL_SPEC[label]
    return f"consensus-specs:{doc}#{symbol}"


def _label_symbol(label: str | None) -> str | None:
    """C5: primary pyspec `process_*` symbol for a dataset label."""
    if not label or label not in _LABEL_SPEC:
        return None
    return _LABEL_SPEC[label][1]


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


def _cap(s: str, n: int = 220) -> str:
    """Cap a pretty-printed Lean expression for use inside an assertion string.

    The full, uncapped text always travels in the dedicated lean_* field."""
    return s if len(s) <= n else s[: n - 3] + "..."


def _short(theorem: str) -> str:
    return theorem.rsplit(".", 1)[-1]


def derive_severities(
    entries: list[dict[str, Any]], health: dict[str, TheoremHealth]
) -> dict[str, str]:
    """B3: proof-DAG severity. theorem -> derived severity (upper-cased).

    Edges run dependent -> dependency: target theorem T depends on target
    lemma L when L appears among T's gasper-local proof constants. A lemma
    inherits the maximum severity of its (transitive) dependents; top-level
    conclusions (no dependents in the target set) keep their theorem_map
    severity. Upward-only: never downgrades a theorem_map severity.
    """
    sev = {e["theorem"]: str(e["severity"]).upper() for e in entries}
    targets = set(sev)
    # fixpoint over max-severity propagation (DAG-safe; bounded by rank domain)
    changed = True
    while changed:
        changed = False
        for e in entries:
            t = e["theorem"]
            th = health.get(t)
            if th is None:
                continue
            for dep in th.proof_constants:
                if dep in targets and dep != t:
                    if _SEVERITY_RANK.get(sev[t], 0) > _SEVERITY_RANK.get(sev[dep], 0):
                        sev[dep] = sev[t]
                        changed = True
    return sev


def _type_consistency(hyp: dict[str, Any], th: TheoremHealth) -> str:
    """B5: the precondition's head constant must be among the theorem's
    gasper-local referenced constants (A3). Non-gasper heads (Ne, Nat.lt, ...)
    carry no gasper subject claim and are "unchecked"."""
    head = str(hyp.get("head") or "")
    refs = set(th.referenced_constants)
    if not head or not head.startswith(_GASPER_PREFIX) or not refs:
        return "unchecked"
    return "ok" if head in refs else "mismatch"


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
    severity: str | None = None,
) -> Property:
    """Build the base (1:1, undecomposed) property for a theorem_map entry.

    `lower_entry` uses this as the template for the per-precondition
    decomposition; on unenriched health it is also the emitted fallback."""
    theorem = entry["theorem"]
    lean_status, module = status_for(health, theorem)

    th = health_for(health, theorem)
    lean_statement = None
    lean_hypotheses = None
    lean_must_establish: list[str] | None = None
    lean_referenced_defs = None
    lean_axioms = None
    lean_proof_provenance = None
    lean_proof_code = None
    lean_conclusion = None
    lean_proof_source = None

    if th.statement:
        lean_statement = th.statement
        lean_hypotheses = th.hypotheses or None
        lean_must_establish = [h["type"] for h in th.must_establish] if th.must_establish else None
        lean_referenced_defs = th.referenced_constants or None
        lean_axioms = th.gasper_axioms or None
        lean_proof_provenance = th.proof_provenance or None
        lean_proof_code = th.proof_code or None
        lean_conclusion = th.conclusion or None
        lean_proof_source = th.proof_source or None

    # B2 (no-precondition shape): a theorem with an enriched statement but no
    # must-establish hypothesis guarantees its conclusion unconditionally.
    assertion = entry["assertion"]
    if th.statement and not th.must_establish and th.conclusion:
        assertion = (
            f"{_short(theorem)} guarantees [{_cap(th.conclusion)}] with no "
            f"must-establish preconditions; audit context: {entry['assertion']}"
        )

    area = entry.get("bug_bounty_area", "")
    in_scope = _area_in_scope(scope, area)
    liveness_only = bool(entry.get("liveness_only", False))
    attacker_controlled = bool(entry.get("attacker_controlled", False))

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

    # D5: label from theorem_map entry
    label = entry.get("label")

    # C5: covers is label-grounded first — the label's pyspec symbol leads the
    # hint list, so with no subgraph match `covers` is a spec symbol, not prose.
    covers_hints = list(entry.get("covers_hint", []))
    symbol = _label_symbol(label)
    if symbol:
        covers_hints = [symbol] + [h for h in covers_hints if h != symbol]

    return Property(
        property_id=entry["property_id"],
        text=entry["text"],
        type=entry.get("type", "invariant"),
        assertion=assertion,
        severity=(severity or str(entry["severity"])).upper(),
        covers=_resolve_covers(covers_hints, subgraphs),
        reachability=reach,
        bug_bounty_eligible=(in_scope and not liveness_only),
        exploitability=exploitability,
        lean_status=lean_status,
        lean_artifact=_lean_artifact(gasper_source, gasper_ref, module, theorem),
        kurtosis_test=None,
        label=label,
        lean_statement=lean_statement,
        lean_hypotheses=lean_hypotheses,
        lean_must_establish=lean_must_establish,
        lean_referenced_defs=lean_referenced_defs,
        lean_axioms=lean_axioms,
        lean_proof_provenance=lean_proof_provenance,
        lean_proof_code=lean_proof_code,
        lean_conclusion=lean_conclusion,
        lean_proof_source=lean_proof_source,
        spec_reference=_spec_reference(label),
    )


def lower_entry(
    entry: dict[str, Any],
    health: dict[str, TheoremHealth],
    scope: dict[str, Any],
    subgraphs: list[dict] | None,
    gasper_source: str,
    gasper_ref: str,
    severity: str | None = None,
) -> list[Property]:
    """B1: lower one theorem_map entry into its `01e` properties.

    One property per must-establish hypothesis; the base 1:1 property when the
    theorem has none (or health is unenriched). The theorem-level property is
    never emitted alongside its decomposition (no lemma/theorem double-count).
    """
    base = build_property(entry, health, scope, subgraphs, gasper_source, gasper_ref, severity)
    th = health_for(health, entry["theorem"])
    mes = th.must_establish
    if not th.statement or not mes:
        return [base]

    short = _short(entry["theorem"])
    conclusion = th.conclusion or th.statement
    n = len(mes)
    props: list[Property] = []
    for i, hyp in enumerate(mes, 1):
        precondition = str(hyp.get("type", ""))
        assertion = (
            f"implementation must preserve [{_cap(precondition)}]; "
            f"if so, {short} guarantees [{_cap(conclusion)}]"
        )
        text = f"{entry['text']} [must-establish {i}/{n}: {hyp.get('name', '?')}]"
        props.append(replace(
            base,
            property_id=f"{base.property_id}-me{i}",
            text=text,
            assertion=assertion,
            lean_precondition=precondition,
            lean_conclusion=conclusion,
            lean_type_consistency=_type_consistency(hyp, th),
        ))
    return props


def build_properties(
    theorem_map: dict[str, Any],
    health: dict[str, TheoremHealth],
    scope: dict[str, Any],
    subgraphs: list[dict] | None = None,
    gasper_ref: str | None = None,
) -> list[dict[str, Any]]:
    source = theorem_map.get("gasper_source", "NyxFoundation/gasper-lean4")
    ref = gasper_ref or theorem_map.get("gasper_ref", "main")
    entries = theorem_map.get("properties", [])
    severities = derive_severities(entries, health)
    props: list[dict[str, Any]] = []
    for entry in entries:
        for prop in lower_entry(entry, health, scope, subgraphs, source, ref,
                                severities.get(entry["theorem"])):
            props.append(prop.to_dict())
    return props


# Default shard when a theorem_map entry omits `shard`.
_DEFAULT_SHARD = "misc"


def build_properties_by_shard(
    theorem_map: dict[str, Any],
    health: dict[str, TheoremHealth],
    scope: dict[str, Any],
    subgraphs: list[dict] | None = None,
    gasper_ref: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Same as `build_properties` but grouped by the entry's `shard` key.

    Returns an ordered {shard -> [property dicts]} mapping (first-seen order),
    so `emit-01e --out-dir` can write one 01e_PARTIAL_<shard>.json per shard and
    keep per-file property count aligned with the benchmark granularity. `shard`
    is a grouping key in theorem_map only; it is never written into a property.
    """
    source = theorem_map.get("gasper_source", "NyxFoundation/gasper-lean4")
    ref = gasper_ref or theorem_map.get("gasper_ref", "main")
    entries = theorem_map.get("properties", [])
    severities = derive_severities(entries, health)
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        shard = str(entry.get("shard", _DEFAULT_SHARD))
        for prop in lower_entry(entry, health, scope, subgraphs, source, ref,
                                severities.get(entry["theorem"])):
            groups.setdefault(shard, []).append(prop.to_dict())
    return groups
