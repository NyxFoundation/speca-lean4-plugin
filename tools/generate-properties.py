#!/usr/bin/env python3
"""Define NEW critical/high checklist properties from Lean theorems (speca#88).

The improve loop only sharpens the existing CHK-* items. This step is the other
half of "since we formalized it in Lean, define NEW critical/high properties":
it pairs each proved gasper theorem with a critical/high *defect class* from
ethereum-vuln-dataset that no existing CHK targets, and asks the model to write
one NEW concrete, general, DEFENSIVE checklist item guarding that invariant
against that defect class. The Lean theorem gives "what must hold", the dataset
class gives "how real clients concretely break", and the pairing yields a novel
critical/high check — NOT a reproduction of a specific past bug.

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
    ASSERTION_MAX, TEXT_MAX, _CLIENT_RE, _extract_json,
    build_judge_prompt, split_cmd, subprocess_llm, statistics as _stats,
)

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
    """theorem -> {labels, covers_hint} from the CHK entries' parent theorems."""
    out: dict[str, dict] = {}
    for p in theorem_map["properties"]:
        if not str(p.get("property_id", "")).startswith("CHK-"):
            continue
        t = p["theorem"]
        d = out.setdefault(t, {"labels": set(), "covers_hint": set(), "x_layer": p.get("x_layer", "")})
        d["labels"].add(p.get("label", ""))
        d["covers_hint"].update(p.get("covers_hint", []) or [])
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


def build_generate_prompt(c: dict) -> str:
    thm = c["theorem"].split(".")[-1]
    hints = ", ".join(c["covers_hint"][:6]) or "the relevant handlers"
    return (
        "You are DEFINING one NEW DEFENSIVE security audit-checklist item for a "
        "protocol implementation. It must let an auditor confirm a machine-proved "
        "invariant cannot be broken by a specific class of implementation defect.\n\n"
        f"Proved invariant (Lean theorem): {thm}\n"
        f"Protocol area (label): {c['label']}\n"
        f"Relevant code surface: {hints}\n"
        f"Implementation defect CLASS to guard against (category only): "
        f"{c['root_cause']}\n\n"
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
    ap.add_argument("--gen-cmd", required=True, help="LLM adapter for generation")
    ap.add_argument("--judge-cmd", required=True, help="LLM adapter for judging")
    ap.add_argument("--max-new", type=int, default=6)
    ap.add_argument("--floor", type=float, default=3.5, help="min judged overall to keep")
    ap.add_argument("--out", default=str(_ROOT / "data" / "generated_properties.json"))
    args = ap.parse_args()

    tmap = json.loads(Path(args.map).read_text(encoding="utf-8"))
    theorems = load_theorems(tmap)
    with open(args.vulns_csv, encoding="utf-8-sig") as f:
        vulns = list(csv.DictReader(f))
    cands = candidates(theorems, vulns, args.max_new)
    print(f"{len(cands)} candidate (theorem x uncovered critical/high class) pairs")

    gen = subprocess_llm(split_cmd(args.gen_cmd), timeout=180)
    judge = subprocess_llm(split_cmd(args.judge_cmd), timeout=180)

    kept, seq = [], 1
    for c in cands:
        thm = c["theorem"].split(".")[-1]
        try:
            obj = _extract_json(gen(build_generate_prompt(c)))
        except Exception as e:
            print(f"  gen fail [{thm}/{c['root_cause']}]: {str(e)[:80]}"); continue
        prop, why = validate_generated(obj)
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
        kept.append({
            "property_id": f"CHK-GEN-{seq:02d}",
            "theorem": c["theorem"], "label": c["label"],
            "x_layer": c["x_layer"], "lowering": "verbatim",
            "text": prop["text"], "type": "invariant", "assertion": prop["assertion"],
            "severity": _SEV_FROM_CLASS[c["severity"]],
            "x_origin": "generated (stage-2 new-property step, tools/generate-properties.py)",
            "x_defect_class": c["root_cause"],
            "x_judged_overall": overall,
            "shard": "checklist-generated",
        })
        seq += 1

    Path(args.out).write_text(json.dumps({"properties": kept}, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print(f"kept {len(kept)} new properties -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
