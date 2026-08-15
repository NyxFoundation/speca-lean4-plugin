#!/usr/bin/env python3
"""Join inventory + triage + curation into `theorem_map_ethtotal.json`.

The three inputs have three different authorities and this keeps them separate:

  inventory (mechanical)  every declaration that exists
  triage    (mechanical)  which theorems are candidates, with the reason
  curation  (reviewed)    which candidates become properties, at what severity,
                          under which dataset label, with what audit title

Everything the audit verdict depends on — `lean_status`, the statement, the
hypothesis telescope — comes from `lake exe speca-export`, never from this
script. What this script writes is the *tuning overlay* the Python driver
expects: labels, severity calibration, covers hints, shards.

Two kinds of base entry are produced:

  curated     the reviewed set in data/ethtotal_curation.json — hand-written
              audit title and assertion, severity calibrated on the audit
              consequence. These are the ones `--cover-all` concretizes.
  derived     the remaining triage-selected theorems. Their title is derived
              from the declaration name and their assertion is the Lean
              conclusion as exported, truncated with an explicit marker —
              never invented prose. They are emitted MEDIUM: they carry real
              proof obligations, but nobody has reviewed them for bug-bounty
              severity, and claiming HIGH for an unreviewed entry would be the
              kind of severity inflation the honesty invariants exist to stop.

Usage:
    python3 tools/ethtotal-build-map.py [--health lean-ethtotal/health.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ASSERTION_MAX = 160


def _short(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _humanize(short: str) -> str:
    """Declaration name -> readable title. The formalization names results after
    what they mean (`no_credit_after_destroy`), so this is a transcription, not
    an interpretation."""
    words = short.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else short


def _truncate(s: str, cap: int = _ASSERTION_MAX) -> str:
    s = " ".join(s.split())
    if len(s) <= cap:
        return s
    return s[: cap - 4].rstrip() + " ..."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default=str(_ROOT / "data" / "ethtotal_inventory.json"))
    ap.add_argument("--triage", default=str(_ROOT / "data" / "ethtotal_triage.json"))
    ap.add_argument("--curation", default=str(_ROOT / "data" / "ethtotal_curation.json"))
    ap.add_argument("--health", default=str(_ROOT / "lean-ethtotal" / "health.json"))
    ap.add_argument("--generated", default=str(_ROOT / "data" / "ethtotal_generated_properties.json"),
                    help="stage-2 CHK-* proposals from tools/generate-properties.py "
                         "(and sharpened in place by the improve loop); skipped when absent")
    ap.add_argument("--packets", default=str(_ROOT / "data" / "ethtotal_audit_packets.json"),
                    help="proof-aware packets for existing theorem roots; skipped when absent")
    ap.add_argument("--vulns-csv", default=str(_ROOT / "data" / "ethtotal_vulns_high.csv"))
    ap.add_argument("--out", default=str(_ROOT / "theorem_map_ethtotal.json"))
    args = ap.parse_args()

    # The full 3333-theorem export is a build artifact and is not versioned;
    # the trimmed copy (tools/ethtotal-trim-health.py) is, and carries every
    # mapped theorem — so a checkout without a Lean toolchain can still rebuild
    # the map and reproduce the emit.
    health_path = Path(args.health)
    if not health_path.exists():
        fallback = health_path.with_name("health.mapped.json")
        if not fallback.exists():
            raise SystemExit(f"no health export at {health_path} or {fallback}")
        print(f"note: {health_path.name} absent — using {fallback.name}")
        health_path = fallback

    inv = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    triage = json.loads(Path(args.triage).read_text(encoding="utf-8"))
    cur = json.loads(Path(args.curation).read_text(encoding="utf-8"))
    packet_overlay = {}
    packet_path = Path(args.packets)
    if packet_path.exists():
        packet_doc = json.loads(packet_path.read_text(encoding="utf-8"))
        packet_overlay = {p["theorem"]: p for p in packet_doc.get("packets", [])}
        print(f"loaded {len(packet_overlay)} existing-theorem audit packets")
    health_doc = json.loads(health_path.read_text(encoding="utf-8"))
    health = {t["name"]: t for t in health_doc["theorems"]}
    # the export size reported in x_stats is the FULL export's, so the map is
    # byte-identical whether it was rebuilt from health.json or from the
    # trimmed copy (the trim records what it was cut from)
    exported = health_doc.get("x_trimmed_from", {}).get("theorems_in_full_export", len(health))

    decl = {d["name"]: d for d in inv["declarations"]}
    # curation may name a theorem by its short name; several EthTotal results
    # live in nested namespaces (`EthTotal.Ledger.…`, `EthTotal.Recorded.…`),
    # so resolve short names against the inventory and refuse ambiguity rather
    # than guessing which namespace was meant.
    by_short: dict[str, list[str]] = {}
    for d in inv["declarations"]:
        by_short.setdefault(d["short_name"], []).append(d["name"])

    def resolve(name: str) -> str:
        if name in decl:
            return name
        cands = by_short.get(_short(name), [])
        if len(cands) == 1:
            return cands[0]
        if not cands:
            raise SystemExit(f"curation names a theorem that does not exist: {name}")
        raise SystemExit(f"ambiguous curation target {name}: matches {cands}")
    themes = cur["themes"]
    file_themes = cur["file_themes"]

    def theme_for(name: str, explicit: str | None = None) -> dict:
        if explicit:
            return themes[explicit]
        f = decl[name]["file"]
        key = file_themes.get(f)
        if not key:
            raise SystemExit(f"no theme for source file {f} (add it to data/ethtotal_curation.json)")
        return themes[key]

    problems: list[str] = []
    entries: list[dict] = []
    seen: set[str] = set()
    counters: dict[str, int] = {}

    def prop_id(theme: dict) -> str:
        # the per-theme `code` is explicit rather than derived from the shard
        # name: initials collide (audit-record / arithmetic-representation).
        code = theme["code"]
        counters[code] = counters.get(code, 0) + 1
        return f"PROP-lean-ethtotal-{code}-{counters[code]:03d}"

    def add(name: str, severity: str, text: str, assertion: str, theme: dict,
            covers_hint: list[str], origin: str) -> None:
        if name in seen:
            return
        if name not in decl:
            problems.append(f"{name}: not in the inventory")
            return
        h = health.get(name)
        if h is None:
            problems.append(f"{name}: not in the health export — the target list is stale")
            return
        if h["lean_status"] != "proved":
            problems.append(f"{name}: lean_status={h['lean_status']} — not a usable property source")
            return
        seen.add(name)
        d = decl[name]
        entry = {
            "property_id": prop_id(theme),
            "theorem": name,
            "label": theme["label"],
            "x_layer": d["file"].removeprefix("EthTotal/"),
            "x_origin": origin,
            "text": text,
            "type": "invariant",
            "assertion": assertion,
            "severity": severity,
            "covers_hint": covers_hint,
            "bug_bounty_area": theme["bug_bounty_area"],
            "attacker_controlled": theme["attacker_controlled"],
            "entry_points": theme["entry_points"],
            "exploitability": theme["exploitability"],
            "liveness_only": False,
            "shard": theme["shard"],
        }
        if name in packet_overlay:
            entry.update(packet_overlay[name])
        entries.append(entry)

    # 1. reviewed entries
    for c in cur["curated"]:
        name = resolve(c["theorem"])
        t = theme_for(name, c.get("theme"))
        add(name, c["severity"], c["text"], c["assertion"], t,
            c.get("covers_hint", []),
            "curated (data/ethtotal_curation.json — reviewed severity, label and audit title)")

    # 2. the rest of the triage-selected set, derived from Lean output
    for f in triage["files"]:
        for name in f["selected"]:
            if name in seen:
                continue
            h = health.get(name)
            if h is None:
                problems.append(f"{name}: selected by triage but absent from the health export")
                continue
            conclusion = (h.get("conclusion") or h.get("statement") or "").strip()
            # A conclusion of `False` marks an impossibility result — the
            # Extentions layer is full of them ("this shortcut cannot be
            # correct"). Saying so beats emitting an assertion that reads
            # `False` with no context; both readings are mechanical.
            if conclusion == "False":
                title = f"Proved impossibility: {_humanize(_short(name))}"
                assertion = ("the stated hypotheses are jointly unsatisfiable "
                             "(Lean conclusion: False)")
            else:
                title = f"Proved invariant: {_humanize(_short(name))}"
                assertion = _truncate(conclusion) or \
                    f"{_short(name)} holds under its stated hypotheses"
            add(name, "MEDIUM", title, assertion,
                theme_for(name), [],
                "derived (triage-selected; title transcribed from the declaration name, "
                "assertion is the exported Lean conclusion — unreviewed for severity, so MEDIUM)")

    # 3. stage-2 checklist overlay: the generated CHK-* items, lowered verbatim
    chk_count = 0
    gen_path = Path(args.generated)
    if gen_path.exists():
        import csv
        from collections import Counter
        vulns = list(csv.DictReader(Path(args.vulns_csv).open(encoding="utf-8-sig")))
        prevalence = Counter((v["label"], v["root_cause"]) for v in vulns)
        vulns_meta = json.loads(
            Path(str(args.vulns_csv).replace(".csv", ".meta.json")).read_text(encoding="utf-8"))
        mapped = {e["theorem"] for e in entries}
        for g in json.loads(gen_path.read_text(encoding="utf-8"))["properties"]:
            name = resolve(g["theorem"])
            if name not in mapped:
                problems.append(f"{g['property_id']}: cites unmapped theorem {name}")
                continue
            t = theme_for(name)
            n = prevalence.get((g["label"], g["x_defect_class"]), 0)
            evidence = (
                f"ethereum-vuln-dataset @ {vulns_meta['source_revision'][:12]} "
                f"(slice: {Path(args.vulns_csv).name}, {vulns_meta['row_count']} critical/high rows): "
                f"defect class `{g['x_defect_class']}` on label `{g['label']}` — "
                f"{n} row(s) in the slice carry exactly this (label, root_cause) pair."
            )
            entry = dict(g)
            entry["theorem"] = name
            entry["x_layer"] = decl[name]["file"].removeprefix("EthTotal/")
            entry["x_dataset_evidence"] = evidence
            entry["bug_bounty_area"] = t["bug_bounty_area"]
            entry["attacker_controlled"] = t["attacker_controlled"]
            entry["entry_points"] = t["entry_points"]
            entry["exploitability"] = t["exploitability"]
            entry["liveness_only"] = False
            entry["covers_hint"] = entry.get("covers_hint", [])
            entries.append(entry)
            chk_count += 1

    if problems:
        for p in problems:
            print(f"ERROR: {p}")
        return 1

    by_sev: dict[str, int] = {}
    for e in entries:
        by_sev[e["severity"]] = by_sev.get(e["severity"], 0) + 1

    out = {
        "version": "0.1.0",
        "source": "NyxFoundation/eth-total-supply-safety",
        "ref": inv["rev"],
        "generated_by": "tools/ethtotal-build-map.py from data/ethtotal_{inventory,triage,curation}.json",
        "note": (
            "Theorem -> 01e property mapping for eth-total-supply-safety (the EthTotal "
            "execution-layer supply/accounting formalization), the second target of this "
            "plugin alongside gasper-lean4's theorem_map.json. Provenance is layered: the "
            "inventory enumerates all 3333 theorems, the triage buckets every one of them "
            "with a reason, and data/ethtotal_curation.json is the reviewed decision on the "
            "subset that becomes properties. Entries marked x_origin=curated carry a "
            "hand-written audit title and a severity calibrated on the EF bug-bounty model; "
            "entries marked x_origin=derived carry a title transcribed from the declaration "
            "name and an assertion taken verbatim from the exported Lean conclusion, and are "
            "MEDIUM because nobody has reviewed them for severity. Statement, hypothesis "
            "telescope, must-establish decomposition and proof status all come from "
            "`lake exe speca-export` (lean-ethtotal/health.json), never from this file. "
            "Fields prefixed x_ are documentation and are not emitted. `shard` groups "
            "properties for `emit-01e --out-dir`. Labels are ethereum-vuln-dataset labels "
            "for the value-bearing execution-layer surfaces; unlike the consensus labels "
            "they have no pyspec anchor, so spec_reference is honestly absent rather than "
            "pointed at a document that does not describe them."
        ),
        "x_stats": {
            "theorems_in_source": inv["declaration_count"],
            "theorems_exported": exported,
            "theorems_mapped": len(entries),
            "by_severity": dict(sorted(by_sev.items())),
            "curated": sum(1 for e in entries if e["x_origin"].startswith("curated")),
            "derived": sum(1 for e in entries if e["x_origin"].startswith("derived")),
            "checklist_generated": chk_count,
        },
        "properties": entries,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(entries)} entries ({len(entries) - chk_count} base + {chk_count} CHK) -> {args.out}")
    print(f"  severity: {out['x_stats']['by_severity']}")
    print(f"  curated {out['x_stats']['curated']} / derived {out['x_stats']['derived']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
