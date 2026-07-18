"""M2 — precision/granularity verification harness (impl plan section 4).

Two references, two measurements:

1. `bench-rq2a-20260508-speca` (the 426-file benchmark release; 16 `01e_*.json`
   files, 186 properties) — GRANULARITY. We compare, against the benchmark
   corpus: schema validity, properties-per-file, assertion/text length
   distributions (z-scores + share within the benchmark's 1-sigma band),
   severity-distribution KL divergence, and vocabulary conformance.

2. `ethereum-vuln-dataset` — RECALL, grounded in the dataset's structured
   `label` vocabulary (D6, issue #6): computed by `speca_lean4.recall` from
   the vendored slice `data/ethereum_vulns.csv` + the reviewable rule table
   `data/label_match_rules.json` + the D2 gap table `data/recall_gaps.json`.
   The old prose judgment table `data/findings_map.json` is DEPRECATED; its
   strict/lenient numbers are still reported (as `recall_prose_deprecated`)
   for continuity, but the label-grounded number is the one that counts.

All statistics are computed from the actual files — nothing here is hardcoded
from a previous run.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from .schema import (
    BENCHMARK_TYPE,
    CLASSIFICATIONS,
    ENTRY_POINTS,
    EXPLOITABILITIES,
    validate_property,
)

_SEV_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"]


def _props_of(doc: Any) -> list[dict]:
    if isinstance(doc, dict):
        return list(doc.get("properties", []))
    if isinstance(doc, list):
        return [x for x in doc if isinstance(x, dict)]
    return []


def load_benchmark(benchmark_dir: str | Path) -> dict[str, Any]:
    """Corpus statistics for every `01e_*.json` under `benchmark_dir`."""
    files = sorted(Path(benchmark_dir).glob("**/01e_*.json"))
    if not files:
        raise FileNotFoundError(f"no 01e_*.json files under {benchmark_dir}")
    per_file_counts: list[int] = []
    assertion_lens: list[int] = []
    text_lens: list[int] = []
    severity: dict[str, int] = {}
    for fp in files:
        props = _props_of(json.loads(fp.read_text(encoding="utf-8")))
        per_file_counts.append(len(props))
        for p in props:
            assertion_lens.append(len(p.get("assertion", "")))
            text_lens.append(len(p.get("text", "")))
            sev = str(p.get("severity", "")).upper()
            severity[sev] = severity.get(sev, 0) + 1
    return {
        "n_files": len(files),
        "n_properties": sum(per_file_counts),
        "props_per_file": _dist(per_file_counts),
        "assertion_len": _dist(assertion_lens),
        "text_len": _dist(text_lens),
        "severity_counts": severity,
    }


def _dist(xs: list[int]) -> dict[str, float]:
    return {
        "mean": round(statistics.mean(xs), 2),
        "stdev": round(statistics.stdev(xs), 2) if len(xs) > 1 else 0.0,
        "min": min(xs),
        "max": max(xs),
        "n": len(xs),
    }


def _z(value: float, dist: dict[str, float]) -> float | None:
    sd = dist.get("stdev") or 0.0
    if sd == 0:
        return None
    return round((value - dist["mean"]) / sd, 2)


def _within_1sigma(xs: list[int], dist: dict[str, float]) -> float:
    lo, hi = dist["mean"] - dist["stdev"], dist["mean"] + dist["stdev"]
    if not xs:
        return 0.0
    return round(sum(1 for x in xs if lo <= x <= hi) / len(xs), 3)


def _kl_divergence(ours: dict[str, int], bench: dict[str, int]) -> float:
    """D_KL(ours || bench) over severity categories, add-one smoothed (nats)."""
    cats = sorted(set(ours) | set(bench) | set(_SEV_ORDER[:3]))
    o_tot = sum(ours.get(c, 0) + 1 for c in cats)
    b_tot = sum(bench.get(c, 0) + 1 for c in cats)
    kl = 0.0
    for c in cats:
        po = (ours.get(c, 0) + 1) / o_tot
        pb = (bench.get(c, 0) + 1) / b_tot
        kl += po * math.log(po / pb)
    return round(kl, 4)


def granularity_report(our_props: list[dict], bench: dict[str, Any]) -> dict[str, Any]:
    a_lens = [len(p.get("assertion", "")) for p in our_props]
    t_lens = [len(p.get("text", "")) for p in our_props]
    sev = {}
    for p in our_props:
        s = str(p.get("severity", "")).upper()
        sev[s] = sev.get(s, 0) + 1

    invalid = {
        p.get("property_id", "?"): problems
        for p in our_props
        if (problems := validate_property(p))
    }
    vocab_bad = [
        p.get("property_id", "?")
        for p in our_props
        if p.get("type") != BENCHMARK_TYPE
        or p.get("exploitability") not in EXPLOITABILITIES
        or (p.get("reachability") or {}).get("classification") not in CLASSIFICATIONS
        or any(e not in ENTRY_POINTS for e in (p.get("reachability") or {}).get("entry_points", []))
    ]

    return {
        "n_properties": len(our_props),
        "schema_validity": round(1 - len(invalid) / len(our_props), 3) if our_props else 0.0,
        "schema_problems": invalid,
        "vocabulary_conformance": round(1 - len(vocab_bad) / len(our_props), 3) if our_props else 0.0,
        "vocabulary_nonconforming": vocab_bad,
        "props_per_file_z": _z(len(our_props), bench["props_per_file"]),
        "assertion_len": _dist(a_lens) if a_lens else None,
        "assertion_len_mean_z": _z(statistics.mean(a_lens), bench["assertion_len"]) if a_lens else None,
        "assertion_within_bench_1sigma": _within_1sigma(a_lens, bench["assertion_len"]),
        "text_len_mean_z": _z(statistics.mean(t_lens), bench["text_len"]) if t_lens else None,
        "text_within_bench_1sigma": _within_1sigma(t_lens, bench["text_len"]),
        "severity_counts": sev,
        "severity_kl_divergence_nats": _kl_divergence(sev, bench["severity_counts"]),
    }


def _id_emitted(pid: str, our_ids: set[str]) -> bool:
    """A findings_map judgment names a theorem-level base id; the B1 lowering
    may refine it into per-precondition ids (`<base>-me<i>`). Either counts."""
    return pid in our_ids or any(oid.startswith(pid + "-me") for oid in our_ids if oid)


def recall_report(our_props: list[dict], findings_map: dict[str, Any]) -> dict[str, Any]:
    """DEPRECATED (D6): recall against the prose findings_map judgment table.

    Kept for continuity/comparison only — the authoritative recall is the
    label-grounded one from `speca_lean4.recall`. The prose in/out-of-domain
    and full/partial judgments are no longer maintained."""
    our_ids = {p.get("property_id") for p in our_props}
    findings = findings_map.get("findings", [])
    in_domain = [f for f in findings if f.get("in_domain")]
    rows = []
    strict = lenient = 0
    for f in in_domain:
        mapped = [pid for pid in f.get("covered_by", []) if _id_emitted(pid, our_ids)]
        cov = f.get("coverage", "none") if mapped else "none"
        if cov == "full":
            strict += 1
            lenient += 1
        elif cov == "partial":
            lenient += 1
        rows.append({
            "id": f["id"],
            "area": f.get("area"),
            "coverage": cov,
            "covered_by": mapped,
        })
    n = len(in_domain)
    return {
        "deprecated": True,
        "note": "prose judgments retired by D6; see label_recall (data/label_match_rules.json)",
        "findings_total": len(findings),
        "findings_in_domain": n,
        "covered_full": strict,
        "covered_partial": lenient - strict,
        "recall_strict": round(strict / n, 3) if n else None,
        "recall_lenient": round(lenient / n, 3) if n else None,
        "rows": rows,
    }


def shard_granularity(ours_dir: str | Path, bench: dict[str, Any]) -> dict[str, Any]:
    """Per-file (per-shard) property-count granularity for our sharded output.

    The benchmark measures props PER FILE (mean 11.62, sd 3.72). When we emit
    one 01e file per shard, granularity should be judged the same way — one z
    per shard file, not a single z over the concatenation. Returns each shard's
    count + z and the overall props-per-file distribution across our files.
    """
    files = sorted(Path(ours_dir).glob("01e_PARTIAL_*.json"))
    counts: list[int] = []
    per_shard: list[dict[str, Any]] = []
    for fp in files:
        doc = json.loads(fp.read_text(encoding="utf-8"))
        n = len(_props_of(doc))
        counts.append(n)
        per_shard.append({
            "file": fp.name,
            "shard": doc.get("shard"),
            "n_properties": n,
            "props_per_file_z": _z(n, bench["props_per_file"]),
            "within_bench_1sigma": bool(
                bench["props_per_file"]["mean"] - bench["props_per_file"]["stdev"]
                <= n
                <= bench["props_per_file"]["mean"] + bench["props_per_file"]["stdev"]
            ),
        })
    return {
        "n_files": len(files),
        "total_properties": sum(counts),
        "per_shard": per_shard,
        "props_per_file": _dist(counts) if counts else None,
        "all_within_bench_1sigma": all(s["within_bench_1sigma"] for s in per_shard) if per_shard else False,
    }


def verify_precision(
    our_01e: str | Path,
    benchmark_dir: str | Path,
    findings_map_path: str | Path,
    ours_dir: str | Path | None = None,
    vulns_csv: str | Path | None = None,
    match_rules_path: str | Path | None = None,
    gaps_path: str | Path | None = None,
) -> dict[str, Any]:
    from . import recall as recall_mod

    ours = _props_of(json.loads(Path(our_01e).read_text(encoding="utf-8")))
    bench = load_benchmark(benchmark_dir)
    fmap = json.loads(Path(findings_map_path).read_text(encoding="utf-8"))
    report = {
        "benchmark": bench,
        "granularity": granularity_report(ours, bench),
        # D6: the authoritative recall — label-grounded, from the vendored
        # dataset slice + reviewable match rules + D2 gap table.
        "label_recall": recall_mod.label_recall_report(
            ours,
            recall_mod.load_vulns(vulns_csv or recall_mod.DEFAULT_VULNS_CSV),
            recall_mod.load_json(match_rules_path or recall_mod.DEFAULT_MATCH_RULES),
            recall_mod.load_json(gaps_path or recall_mod.DEFAULT_GAPS),
        ),
        # deprecated prose judgments, kept for continuity/comparison
        "recall_prose_deprecated": recall_report(ours, fmap),
    }
    if ours_dir is not None:
        report["shard_granularity"] = shard_granularity(ours_dir, bench)
    return report


def format_summary(report: dict[str, Any]) -> str:
    b, g = report["benchmark"], report["granularity"]
    lines = [
        f"benchmark corpus: {b['n_files']} files, {b['n_properties']} properties "
        f"(props/file {b['props_per_file']['mean']} +/- {b['props_per_file']['stdev']}, "
        f"assertion len {b['assertion_len']['mean']} +/- {b['assertion_len']['stdev']})",
        f"ours: {g['n_properties']} properties | schema validity {g['schema_validity']:.0%} "
        f"| vocabulary conformance {g['vocabulary_conformance']:.0%}",
        f"granularity: props/file z={g['props_per_file_z']}, "
        f"assertion mean z={g['assertion_len_mean_z']}, "
        f"assertion within bench 1-sigma: {g['assertion_within_bench_1sigma']:.0%}",
        f"severity: ours {g['severity_counts']} vs bench {b['severity_counts']} "
        f"| KL={g['severity_kl_divergence_nats']} nats",
    ]
    lr = report.get("label_recall")
    if lr:
        lines.append(
            f"label-grounded recall (D6, domain {lr['domain_version']}, "
            f"denominator {lr['findings_in_domain']} in-domain of "
            f"{lr['slice_rows']} vendored slice rows): {lr['label_recall']} "
            f"({lr['covered']} covered, gaps: {lr['gap_dispositions'] or 'none'})"
        )
    r = report.get("recall_prose_deprecated")
    if r:
        lines.append(
            f"[deprecated prose table] recall vs critical_high_findings "
            f"(in-domain n={r['findings_in_domain']} of {r['findings_total']}): "
            f"strict {r['recall_strict']} | lenient {r['recall_lenient']} "
            f"(full={r['covered_full']}, partial={r['covered_partial']})"
        )
    sg = report.get("shard_granularity")
    if sg:
        shard_bits = ", ".join(
            f"{s['shard']}={s['n_properties']} (z={s['props_per_file_z']}"
            f"{'' if s['within_bench_1sigma'] else ', OUT'})"
            for s in sg["per_shard"]
        )
        lines.append(
            f"sharded granularity: {sg['n_files']} files, "
            f"props/file {sg['props_per_file']['mean']} +/- {sg['props_per_file']['stdev']} "
            f"| {shard_bits} | all within bench 1-sigma: {sg['all_within_bench_1sigma']}"
        )
    return "\n".join(lines)
