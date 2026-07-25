#!/usr/bin/env python3
"""Refine causally selected Lean -> implementation obligations into 01e text.

Candidate selection now defaults to ``data/projection_map.json``.  The reviewed
map supplies the causal chain from theorem to owned input/boundary obligation;
the LLM only rewrites that selected obligation into concise audit text.  The old
label-prevalence pairing remains behind ``--legacy-label-pairing`` for historical
reproduction and must not be used for production checklist generation.

Same guards as the improve loop: defensive framing + class-only evidence
(speca#143 safeguard), generality lint (no client names), length/granularity
caps, and honest provenance (lowering=verbatim, lean_status=descends-from-<parent>).
Each candidate is judged; only those clearing a floor are kept. Output is a
PROPOSAL (data/generated_properties.json) for review before theorem_map entry.

Usage:
  uv run python tools/generate-properties.py \
     --gen-cmd "claude -p" --judge-cmd "bash tools/llm-hermes.sh" \
     --max-new 6 --floor 3.5 --out data/generated_properties.json
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from speca_lean4.judge import (
    ASSERTION_MAX, EF_BOUNTY_SEVERITY, TEXT_MAX, _CLIENT_RE, _extract_json,
    build_judge_prompt, split_cmd, subprocess_llm, statistics as _stats,
)
from speca_lean4.projection import load_projection_map

_ROOT = Path(__file__).resolve().parents[1]

# critical/high defect classes an existing CHK already targets, by (label,
# root_cause). Kept deliberately small and explicit — a generated candidate on
# one of these is skipped so we only ever propose genuinely NEW coverage.
_COVERED = {
    ("beacon-chain:slashing", "integer_overflow_underflow"),   # CHK-SL-01
    ("beacon-chain:attestation", "missing_input_validation"),  # CHK-QW-02 (index bounds)
    ("p2p-interface", "resource_exhaustion"),                  # CHK-LV-01
}

_SEV_FROM_CLASS = {"Critical": "CRITICAL", "High": "HIGH"}


def load_theorems(theorem_map: dict) -> dict[str, dict]:
    """theorem -> {labels, covers_hint, x_layer, severity, has_chk} from ALL entries.

    Previously this skipped every non-CHK entry, so theorems that had ONLY the
    abstract PROP-lean-*/-me* form (no concrete CHK twin) were invisible to the
    generator — which is exactly why the core critical/high safety lemmas
    (k_slash_surround_case_general, k_non_equal_height_case, …) never got
    concretized. Now every theorem entry is loaded; ``has_chk`` marks the ones a
    concrete checklist already covers so we only generate for the rest.
    """
    out: dict[str, dict] = {}
    for p in theorem_map["properties"]:
        t = p.get("theorem")
        if not t:
            continue
        d = out.setdefault(t, {"labels": set(), "covers_hint": set(),
                               "x_layer": p.get("x_layer", ""), "severity": None,
                               "has_chk": False})
        d["labels"].add(p.get("label", ""))
        d["covers_hint"].update(p.get("covers_hint", []) or [])
        if p.get("severity") and not d["severity"]:
            d["severity"] = p.get("severity")
        if str(p.get("property_id", "")).startswith("CHK-"):
            d["has_chk"] = True
    return out


def coverage_candidates(theorems: dict[str, dict], vulns: list[dict]) -> list[dict]:
    """One candidate per CRITICAL/HIGH theorem with NO concrete CHK twin.

    Theorem-driven and UNCAPPED — guarantees every high-severity proved invariant
    gets a concrete checklist item (the fix for "concretize everything"). The
    defect class is the most dataset-prevalent vuln class matching the theorem's
    protocol label; if none matches, a generic invariant-violation class is used
    so a candidate is still produced (never silently skipped).
    """
    prevalence = Counter((v["label"], v["root_cause"]) for v in vulns
                         if v.get("severity") in ("Critical", "High"))
    best_class: dict[str, str] = {}
    for (label, rc), _ in prevalence.most_common():
        best_class.setdefault(label, rc)
    out: list[dict] = []
    for t, d in sorted(theorems.items()):
        if d.get("has_chk"):
            continue
        sev = (d.get("severity") or "").upper()
        if sev not in ("CRITICAL", "HIGH"):
            continue
        rc = next((best_class[lab] for lab in d["labels"] if lab in best_class),
                  "logic_error_invariant_violation")
        out.append({"theorem": t,
                    "label": next(iter(sorted(l for l in d["labels"] if l)), ""),
                    "root_cause": rc,
                    "severity": "Critical" if sev == "CRITICAL" else "High",
                    "prevalence": 0,
                    "covers_hint": sorted(d["covers_hint"]),
                    "x_layer": d["x_layer"]})
    return out


def candidates(theorems: dict[str, dict], vulns: list[dict], max_new: int) -> list[dict]:
    """(theorem, label, root_cause) pairs: a critical/high class prevalent in a
    theorem's label that no existing CHK covers. Ranked by dataset prevalence."""
    prevalence = Counter((v["label"], v["root_cause"]) for v in vulns
                         if v.get("severity") in ("Critical", "High"))
    sev_of = {}
    for v in vulns:
        key = (v["label"], v["root_cause"])
        if v.get("severity") in ("Critical", "High"):
            sev_of.setdefault(key, v["severity"])
    label_to_thms: dict[str, list[str]] = {}
    for t, d in theorems.items():
        for lab in d["labels"]:
            label_to_thms.setdefault(lab, []).append(t)
    out: list[dict] = []
    for (label, rc), n in prevalence.most_common():
        if (label, rc) in _COVERED:
            continue
        for t in label_to_thms.get(label, []):
            out.append({"theorem": t, "label": label, "root_cause": rc,
                        "severity": sev_of[(label, rc)], "prevalence": n,
                        "covers_hint": sorted(theorems[t]["covers_hint"]),
                        "x_layer": theorems[t]["x_layer"]})
    # one candidate per (theorem, root_cause), highest prevalence first
    seen, uniq = set(), []
    for c in sorted(out, key=lambda c: -c["prevalence"]):
        k = (c["theorem"], c["root_cause"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq[:max_new]


def causal_candidates(projection_map: dict, target_layer: str) -> list[dict]:
    """Reviewed obligations, never inferred from dataset prevalence."""
    out = []
    for item in projection_map["obligations"]:
        if item.get("target_layer") != target_layer:
            continue
        query = item.get("dataset_match", {})
        out.append({
            "obligation_id": item["obligation_id"],
            "theorem": item["source_theorems"][0],
            "source_theorems": list(item["source_theorems"]),
            "owned_inputs": list(item["owned_inputs"]),
            "causal_rationale": item["causal_rationale"],
            "implementation_surfaces": list(item.get("implementation_surfaces", [])),
            "spec_references": list(item["spec_references"]),
            "label": item.get("label", ""),
            "root_cause": (query.get("root_causes") or ["logic_error_invariant_violation"])[0],
            "severity": str(item["severity"]).title(),
            "prevalence": 0,
            "covers_hint": list(item.get("implementation_surfaces", [])),
            "x_layer": target_layer,
            "seed_text": item["text"],
            "seed_assertion": item["assertion"],
        })
    return out


def build_generate_prompt(c: dict) -> str:
    thm = c["theorem"].split(".")[-1]
    hints = ", ".join(c["covers_hint"][:6]) or "the relevant handlers"
    causal = ""
    if c.get("obligation_id"):
        causal = (
            f"Causal obligation: {c['obligation_id']}\n"
            f"Source theorems: {', '.join(c['source_theorems'])}\n"
            f"Owned model inputs: {', '.join(c['owned_inputs'])}\n"
            f"Why this affects the theorem: {c['causal_rationale']}\n"
            f"Specification anchors: {', '.join(c['spec_references'])}\n"
            f"Reviewed seed check: {c['seed_text']}\n"
            f"Reviewed seed assertion: {c['seed_assertion']}\n"
        )
    return (
        "You are DEFINING one NEW DEFENSIVE security audit-checklist item for a "
        "protocol implementation. It must let an auditor confirm a machine-proved "
        "invariant cannot be broken by a specific class of implementation defect.\n\n"
        f"Proved invariant (Lean theorem): {thm}\n"
        f"Protocol area (label): {c['label']}\n"
        f"Relevant code surface: {hints}\n"
        f"{causal}"
        f"Implementation defect CLASS to guard against (category only): "
        f"{c['root_cause']} (bug-bounty severity: {c['severity']})\n\n"
        f"{EF_BOUNTY_SEVERITY}\n\n"
        "Write ONE concrete, general, code-level checklist item: what an auditor "
        "inspects in the implementation source so this invariant holds against "
        "this defect class. Rules:\n"
        "- ONE auditable concern; general — NEVER name a specific client.\n"
        f"- TEXT: one imperative checklist sentence, <= {TEXT_MAX} chars.\n"
        f"- ASSERTION: a compact machine-readable condition, <= {ASSERTION_MAX} chars.\n"
        "Return STRICT JSON only: {\"text\": \"...\", \"assertion\": \"...\"}"
    )


def validate_generated(obj: dict) -> tuple[dict | None, str]:
    text, assertion = obj.get("text", ""), obj.get("assertion", "")
    if not (isinstance(text, str) and text.strip() and isinstance(assertion, str) and assertion.strip()):
        return None, "empty text/assertion"
    text, assertion = text.strip(), assertion.strip()
    for v in (text, assertion):
        m = _CLIENT_RE.search(v)
        if m:
            return None, f"client name {m.group(0)!r} (generality)"
    if len(text) > TEXT_MAX:
        return None, f"text {len(text)}>{TEXT_MAX}"
    if len(assertion) > ASSERTION_MAX:
        return None, f"assertion {len(assertion)}>{ASSERTION_MAX}"
    return {"text": text, "assertion": assertion}, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=str(_ROOT / "theorem_map.json"))
    ap.add_argument("--vulns-csv", default=str(_ROOT / "data" / "ethereum_vulns_high.csv"))
    ap.add_argument(
        "--projection-map", default=str(_ROOT / "data" / "projection_map.json"),
        help="reviewed causal projection map (default: data/projection_map.json)",
    )
    ap.add_argument(
        "--target-layer", choices=("cl", "el"), default="cl",
        help="projection layer used for causal candidate selection (default: cl)",
    )
    ap.add_argument(
        "--legacy-label-pairing", action="store_true",
        help="reproduce the deprecated theorem-label x prevalent-defect heuristic",
    )
    ap.add_argument("--gen-cmd", required=True, help="LLM adapter for generation")
    ap.add_argument("--judge-cmd", required=True, help="LLM adapter for judging")
    ap.add_argument("--max-new", type=int, default=6)
    ap.add_argument("--cover-all", action="store_true",
                    help="concretize EVERY critical/high theorem with no concrete CHK twin "
                         "(theorem-driven, uncapped) instead of the top-N-by-prevalence set")
    ap.add_argument("--floor", type=float, default=3.5, help="min judged overall to keep")
    ap.add_argument("--out", default=str(_ROOT / "data" / "generated_properties.json"))
    args = ap.parse_args()

    tmap = json.loads(Path(args.map).read_text(encoding="utf-8"))
    theorems = load_theorems(tmap)
    with open(args.vulns_csv, encoding="utf-8-sig") as f:
        vulns = list(csv.DictReader(f))
    if not args.legacy_label_pairing:
        cands = causal_candidates(
            load_projection_map(args.projection_map), args.target_layer
        )
        print(
            f"{len(cands)} reviewed causal obligation(s) for "
            f"target_layer={args.target_layer}"
        )
    elif args.cover_all:
        cands = coverage_candidates(theorems, vulns)
        print(f"{len(cands)} critical/high theorem(s) with no concrete CHK twin -> concretizing all (legacy)")
    else:
        cands = candidates(theorems, vulns, args.max_new)
        print(f"{len(cands)} candidate (theorem x uncovered critical/high class) pairs")

    gen = subprocess_llm(split_cmd(args.gen_cmd), timeout=180)
    judge = subprocess_llm(split_cmd(args.judge_cmd), timeout=180)

    kept, seq = [], 1
    for c in cands:
        thm = c["theorem"].split(".")[-1]
        # generate with a retry when the ONLY problem is length — re-prompt tersely
        # rather than dropping the theorem (important for the critical/high ones).
        prompt = build_generate_prompt(c)
        prop, why = None, "gen fail"
        for attempt in range(3):
            try:
                obj = _extract_json(gen(prompt))
            except Exception as e:
                why = f"gen fail: {str(e)[:80]}"; break
            prop, why = validate_generated(obj)
            if prop:
                break
            if ">" in why and "chars" not in why and "name" not in why:
                # length overflow -> ask for a terser rewrite and retry
                prompt = (build_generate_prompt(c) +
                          f"\n\nSTRICT RETRY: your previous answer was REJECTED for being too long "
                          f"({why}). Return TEXT <= {TEXT_MAX} chars and ASSERTION <= {ASSERTION_MAX} "
                          f"chars — be terse, drop examples, keep the one core check.")
                continue
            break
        if not prop:
            print(f"  rejected [{thm}/{c['root_cause']}]: {why}"); continue
        # judge the new item blind, same rubric as everything else
        try:
            jr = _extract_json(judge(build_judge_prompt(
                {"id": "GEN", "check": prop["text"], "detail": prop["assertion"]})))
            overall = round(_stats.mean(int(jr["scores"][a]) for a in jr["scores"]), 3)
        except Exception as e:
            print(f"  judge fail [{thm}/{c['root_cause']}]: {str(e)[:80]}"); continue
        status = "KEEP" if overall >= args.floor else "drop"
        print(f"  {status} CHK-GEN-{seq:02d} [{thm}/{c['root_cause']}] overall={overall}")
        if overall < args.floor:
            continue
        prop_id = c.get("obligation_id") or f"CHK-GEN-{seq:02d}"
        kept.append({
            "property_id": prop_id,
            "theorem": c["theorem"], "label": c["label"],
            "x_layer": c["x_layer"], "lowering": "verbatim",
            "text": prop["text"], "type": "invariant", "assertion": prop["assertion"],
            "severity": _SEV_FROM_CLASS.get(c["severity"], c["severity"].upper()),
            "x_origin": "generated (stage-2 new-property step, tools/generate-properties.py)",
            "x_defect_class": c["root_cause"],
            "x_judged_overall": overall,
            "shard": "checklist-generated",
        })
        if c.get("obligation_id"):
            kept[-1].update({
                "target_layer": args.target_layer,
                "source_theorems": c["source_theorems"],
                "owned_inputs": c["owned_inputs"],
                "causal_rationale": c["causal_rationale"],
                "spec_references": c["spec_references"],
            })
        seq += 1

    Path(args.out).write_text(json.dumps({"properties": kept}, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print(f"kept {len(kept)} new properties -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
