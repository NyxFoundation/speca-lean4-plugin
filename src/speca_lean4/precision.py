"""M2 — precision/granularity verification harness (impl plan section 4).

Two references, two measurements:

1. `bench-rq2a-20260508-speca` (the 426-file benchmark release; 16 `01e_*.json`
   files, 186 properties) — GRANULARITY. We compare, against the benchmark
   corpus: schema validity, properties-per-file, assertion/text length
   distributions (z-scores + share within the benchmark's 1-sigma band),
   severity-distribution KL divergence, and vocabulary conformance.

2. `ethereum-vuln-dataset` `docs/critical_high_findings.md` — RECALL. The
   curated judgment table lives in `data/findings_map.json` (every
   consensus-layer finding listed with an explicit in_domain flag and a
   coverage judgment, so the denominator is transparent and the numbers are
   reproducible). Recall is reported twice: strict (coverage == full) and
   lenient (full or partial). We never count an out-of-domain finding in
   either direction.

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


def recall_report(our_props: list[dict], findings_map: dict[str, Any]) -> dict[str, Any]:
    """Recall against the curated consensus-domain findings table."""
    our_ids = {p.get("property_id") for p in our_props}
    findings = findings_map.get("findings", [])
    in_domain = [f for f in findings if f.get("in_domain")]
    rows = []
    strict = lenient = 0
    for f in in_domain:
        mapped = [pid for pid in f.get("covered_by", []) if pid in our_ids]
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


def label_recall_report(our_props: list[dict], findings_map: dict[str, Any]) -> dict[str, Any]:
    """D6: Recall computed by label correspondence against the dataset vocabulary."""
    our_labels = {p.get("label") for p in our_props if p.get("label")}
    label_prop_count: dict[str, int] = {}
    for p in our_props:
        lbl = p.get("label")
        if lbl:
            label_prop_count[lbl] = label_prop_count.get(lbl, 0) + 1

    findings = findings_map.get("findings", [])
    in_domain = [f for f in findings if f.get("in_domain")]
    matched = 0
    uncovered: list[str] = []
    rows = []
    for f in in_domain:
        f_label = f.get("label") or f.get("area", "")
        has_match = f_label in our_labels
        if has_match:
            matched += 1
        else:
            if f_label and f_label not in uncovered:
                uncovered.append(f_label)
        rows.append({"id": f["id"], "label": f_label, "matched": has_match})

    n = len(in_domain)
    return {
        "findings_in_domain": n,
        "label_matched": matched,
        "label_recall": round(matched / n, 3) if n else None,
        "label_coverage": label_prop_count,
        "uncovered_labels": uncovered,
        "rows": rows,
    }


def verify_precision(
    our_01e: str | Path,
    benchmark_dir: str | Path,
    findings_map_path: str | Path,
    ours_dir: str | Path | None = None,
) -> dict[str, Any]:
    ours = _props_of(json.loads(Path(our_01e).read_text(encoding="utf-8")))
    bench = load_benchmark(benchmark_dir)
    fmap = json.loads(Path(findings_map_path).read_text(encoding="utf-8"))
    report = {
        "benchmark": bench,
        "granularity": granularity_report(ours, bench),
        "recall": recall_report(ours, fmap),
        "label_recall": label_recall_report(ours, fmap),
    }
    if ours_dir is not None:
        report["shard_granularity"] = shard_granularity(ours_dir, bench)
    return report


def format_summary(report: dict[str, Any]) -> str:
    b, g, r = report["benchmark"], report["granularity"], report["recall"]
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
        f"recall vs critical_high_findings (in-domain n={r['findings_in_domain']} "
        f"of {r['findings_total']} consensus-layer findings): "
        f"strict {r['recall_strict']} | lenient {r['recall_lenient']} "
        f"(full={r['covered_full']}, partial={r['covered_partial']})",
    ]
    lr = report.get("label_recall")
    if lr:
        lines.append(
            f"label-grounded recall (in-domain n={lr['findings_in_domain']}): "
            f"{lr['label_recall']} ({lr['label_matched']} label-matched)"
            + (f" | uncovered labels: {lr['uncovered_labels']}" if lr["uncovered_labels"] else "")
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
