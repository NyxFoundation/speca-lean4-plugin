"""D6 — label-grounded recall against the ethereum-vuln-dataset vocabulary.

Retires the prose coverage judgments of `data/findings_map.json` (kept, but
deprecated). Recall is now computed from three reviewable data files:

1. `data/ethereum_vulns.csv` — a vendored consensus-domain slice of the
   dataset (`NyxFoundation/ethereum-vuln-dataset`, revision pinned in
   `data/ethereum_vulns.meta.json`): every row whose `label` is one of the
   consensus-specs areas the FFG target set maps to. Vendored UNFILTERED
   beyond the label so the denominator derivation is reproducible.
2. `data/label_match_rules.json` — (a) the STRUCTURAL in-domain filter
   (label + root_cause + attack_path + severity; D1 narrow-v1 domain, grown
   gradually), and (b) per-(label, root_cause) coverage rules, each naming
   the base property ids that catch the class and a rationale.
3. `data/recall_gaps.json` — the D2 gap table: every uncovered in-domain
   finding triaged `new_target` (which precondition/theorem would catch it)
   or `out_of_model` (honestly outside the FFG remit).

Honesty guards (all computed from the REAL emitted 01e, never hardcoded):
- a rule's `covered_by` ids must actually be emitted (base id or its B1
  `-me<i>` refinements) AND carry the rule's label — else NOT covered;
- an unlisted (label, root_cause) cell is NOT covered (`no_rule`);
- `verify(strict)` fails on uncovered in-domain findings missing from the
  gap table, and on stale gap entries (covered or no longer in-domain).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VULNS_CSV = _REPO_ROOT / "data" / "ethereum_vulns.csv"
DEFAULT_MATCH_RULES = _REPO_ROOT / "data" / "label_match_rules.json"
DEFAULT_GAPS = _REPO_ROOT / "data" / "recall_gaps.json"


def load_vulns(csv_path: str | Path = DEFAULT_VULNS_CSV) -> list[dict[str, str]]:
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def in_domain(row: dict[str, str], domain: dict[str, Any]) -> tuple[bool, str]:
    """Structural D1 domain filter. Returns (in_domain, reason)."""
    if row.get("label") not in domain.get("labels", []):
        return False, f"label {row.get('label')!r} outside domain labels"
    if row.get("severity") in domain.get("excluded_severities", []):
        return False, f"severity {row.get('severity')!r} excluded (informational crawl row)"
    if row.get("root_cause") not in domain.get("in_model_root_causes", []):
        return False, f"root_cause {row.get('root_cause')!r} outside the FFG-expressible causes"
    if row.get("attack_path") not in domain.get("in_model_attack_paths", []):
        return False, f"attack_path {row.get('attack_path')!r} not a consensus-state trigger"
    return True, "in-domain"


def _emitted_with_label(base_id: str, label: str, props: list[dict]) -> bool:
    """True iff base_id (or a B1 `-me<i>` refinement of it) is actually emitted
    in the real 01e AND carries `label`. The grounding guard: a rule cannot
    claim coverage through a property that was never emitted."""
    for p in props:
        pid = str(p.get("property_id", ""))
        if pid == base_id or pid.startswith(base_id + "-me"):
            if p.get("label") == label:
                return True
    return False


def _rule_for(rules: list[dict], label: str, root_cause: str) -> dict | None:
    for r in rules:
        if r.get("label") == label and r.get("root_cause") == root_cause:
            return r
    return None


def label_recall_report(
    props: list[dict],
    vulns: list[dict[str, str]],
    match_rules: dict[str, Any],
    gaps: dict[str, Any],
) -> dict[str, Any]:
    """Label-grounded recall over the vendored dataset slice.

    recall = |in-domain findings whose (label, root_cause) cell is covered by
    an emitted property| / |in-domain findings|, with the coverage decision
    refined by root_cause (rule cells) and the trigger sanity-checked by
    attack_path (domain filter).
    """
    domain = match_rules.get("domain", {})
    rules = match_rules.get("rules", [])
    gap_by_id = {g.get("finding_id"): g for g in gaps.get("gaps", [])}

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    covered_n = 0
    uncovered_ids: list[str] = []
    untriaged: list[str] = []
    unverifiable_rules: list[dict[str, Any]] = []

    for v in vulns:
        ok, reason = in_domain(v, domain)
        vid = v.get("id", "?")
        if not ok:
            excluded.append({"id": vid, "label": v.get("label", ""), "reason": reason})
            continue
        label, rc = v.get("label", ""), v.get("root_cause", "")
        rule = _rule_for(rules, label, rc)
        covered = False
        covered_by: list[str] = []
        basis = "no_rule"
        if rule is not None:
            basis = "rule"
            if rule.get("covered"):
                covered_by = [
                    b for b in rule.get("covered_by", [])
                    if _emitted_with_label(b, label, props)
                ]
                covered = bool(covered_by)
                if not covered:
                    # rule claims coverage but nothing it names is emitted
                    basis = "rule_unverifiable"
                    unverifiable_rules.append({
                        "label": label, "root_cause": rc,
                        "covered_by": rule.get("covered_by", []),
                    })
        if covered:
            covered_n += 1
        else:
            uncovered_ids.append(vid)
            if vid not in gap_by_id:
                untriaged.append(vid)
        gap = gap_by_id.get(vid)
        rows.append({
            "id": vid,
            "client": v.get("source_platform", ""),
            "severity": v.get("severity", ""),
            "title": (v.get("title", "") or "")[:120],
            "label": label,
            "root_cause": rc,
            "attack_path": v.get("attack_path", ""),
            "covered": covered,
            "covered_by": covered_by,
            "match_basis": basis,
            "gap_disposition": gap.get("disposition") if gap else None,
        })

    n = len(rows)
    stale_gaps = [
        gid for gid in gap_by_id
        if gid not in uncovered_ids
    ]
    gap_dispositions: dict[str, int] = {}
    for gid in uncovered_ids:
        g = gap_by_id.get(gid)
        if g:
            d = str(g.get("disposition", "?"))
            gap_dispositions[d] = gap_dispositions.get(d, 0) + 1

    return {
        "reference": "data/ethereum_vulns.csv (vendored ethereum-vuln-dataset slice; see data/ethereum_vulns.meta.json)",
        "domain_version": domain.get("version"),
        "slice_rows": len(vulns),
        "findings_in_domain": n,
        "covered": covered_n,
        "label_recall": round(covered_n / n, 3) if n else None,
        "uncovered": uncovered_ids,
        "gap_dispositions": gap_dispositions,
        "untriaged_uncovered": untriaged,
        "stale_gap_entries": stale_gaps,
        "unverifiable_rules": unverifiable_rules,
        "rows": rows,
        "excluded_out_of_domain": excluded,
    }


def verify_recall(
    our_01e: str | Path,
    vulns_csv: str | Path = DEFAULT_VULNS_CSV,
    match_rules_path: str | Path = DEFAULT_MATCH_RULES,
    gaps_path: str | Path = DEFAULT_GAPS,
) -> dict[str, Any]:
    doc = load_json(our_01e)
    props = list(doc.get("properties", [])) if isinstance(doc, dict) else list(doc)
    return label_recall_report(
        props, load_vulns(vulns_csv), load_json(match_rules_path), load_json(gaps_path)
    )


def strict_problems(report: dict[str, Any]) -> list[str]:
    """D2 loop enforcement: reasons the report should fail a --strict run."""
    problems: list[str] = []
    if report["untriaged_uncovered"]:
        problems.append(
            "uncovered in-domain findings missing from data/recall_gaps.json: "
            + ", ".join(report["untriaged_uncovered"])
        )
    if report["stale_gap_entries"]:
        problems.append(
            "stale data/recall_gaps.json entries (finding covered or not in-domain): "
            + ", ".join(report["stale_gap_entries"])
        )
    if report["unverifiable_rules"]:
        problems.append(
            "match rules claiming coverage via properties not present in the emitted 01e: "
            + json.dumps(report["unverifiable_rules"])
        )
    return problems


def format_recall_summary(report: dict[str, Any]) -> str:
    lines = [
        f"label-grounded recall (domain {report['domain_version']}, "
        f"denominator: {report['findings_in_domain']} in-domain of "
        f"{report['slice_rows']} vendored consensus-slice findings): "
        f"{report['label_recall']} ({report['covered']} covered)",
    ]
    for r in report["rows"]:
        mark = "covered by " + ",".join(r["covered_by"]) if r["covered"] else (
            f"UNCOVERED -> {r['gap_disposition'] or 'UNTRIAGED'}"
        )
        lines.append(
            f"  [{'x' if r['covered'] else ' '}] {r['id']} "
            f"({r['label']} / {r['root_cause']}): {mark}"
        )
    if report["gap_dispositions"]:
        lines.append(f"gap table: {report['gap_dispositions']}")
    for p in strict_problems(report):
        lines.append(f"PROBLEM: {p}")
    return "\n".join(lines)
