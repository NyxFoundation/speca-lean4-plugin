"""`speca-lean4` — the subprocess/CLI contract that speca's `lean` provider calls.

    speca-lean4 emit-01e \
        --scope BUG_BOUNTY_SCOPE.json \
        [--map theorem_map.json] \
        [--subgraphs 01b_PARTIAL_glob ...] \
        [--gasper-ref <git-sha>] \
        (--health-json health.json | --run-lean) \
        (--out 01e_PARTIAL_lean.json | --out-dir outputs/01e_lean/)

Health source (Stage B) is one of:
  --health-json   a precomputed proof-health JSON from `lake exe speca-export`
  --run-lean      run `lake exe speca-export` in ./lean now (requires the Lean
                  toolchain; writes the target list from the theorem map)

Output is one of (or both):
  --out       single 01e_PARTIAL JSON with all properties (speca provider call)
  --out-dir   sharded: one 01e_PARTIAL_<shard>.json per theorem_map `shard`
              group, so per-file property count matches the benchmark
              granularity (M3). Shard groups: safety, finality.

speca#87's `LeanPropertyProvider.generate()` shells out to this and reads --out.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from glob import glob
from pathlib import Path
from typing import Any

from .health import index_health, load_health
from .mapping import build_properties, build_properties_by_shard

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MAP = _REPO_ROOT / "theorem_map.json"
_LEAN_DIR = _REPO_ROOT / "lean"


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_subgraphs(patterns: list[str] | None) -> list[dict] | None:
    if not patterns:
        return None
    out: list[dict] = []
    for pat in patterns:
        for fp in glob(pat):
            try:
                data = _load_json(fp)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, list):
                out.extend(x for x in data if isinstance(x, dict))
            elif isinstance(data, dict):
                out.append(data)
    return out or None


def _tail(text: str, n: int = 2000) -> str:
    """Last `n` chars of a stream, for diagnosable error messages."""
    if not text:
        return "<empty>"
    return ("..." if len(text) > n else "") + text[-n:]


def _run_lean(theorem_map: dict[str, Any]) -> dict[str, Any]:
    """Write the target list and invoke `lake exe speca-export`, returning parsed health.

    The exporter writes its health JSON to a file (`--output`), NOT to stdout:
    on a cold lake workspace, `lake exe` emits toolchain-download, dependency-
    fetch and build progress on stdout before the executable even runs
    (observed in speca run 29749878252, where the leading noise broke
    `json.loads(proc.stdout)`). stdout/stderr are treated as log channels only
    and are forwarded to stderr so CI logs keep the build evidence.
    """
    targets = [e["theorem"] for e in theorem_map.get("properties", [])]
    # mkdtemp (not auto-cleaned) on purpose: on failure the targets file and
    # any partial output stay on disk for post-mortem.
    workdir = Path(tempfile.mkdtemp(prefix="speca-lean4-run-"))
    targets_path = workdir / "speca_export.targets"
    targets_path.write_text("\n".join(targets) + "\n", encoding="utf-8")
    out_path = workdir / "health.json"
    cmd = [
        "lake", "exe", "speca-export",
        "--targets", str(targets_path),
        "--output", str(out_path),
    ]
    proc = subprocess.run(cmd, cwd=str(_LEAN_DIR), capture_output=True, text=True)
    # Forward build/toolchain noise so it is never silently discarded.
    if proc.stdout:
        print(proc.stdout, file=sys.stderr, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    diagnostics = (
        f"--- stdout (tail) ---\n{_tail(proc.stdout)}\n"
        f"--- stderr (tail) ---\n{_tail(proc.stderr)}"
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(cmd)}` (cwd={_LEAN_DIR}) failed (rc={proc.returncode})\n"
            f"{diagnostics}"
        )
    if not out_path.is_file():
        raise RuntimeError(
            f"`{' '.join(cmd)}` returned rc=0 but wrote no {out_path} — the "
            "lake invocation succeeded without running the exporter (or the "
            "exporter predates --output support)\n" + diagnostics
        )
    health_text = out_path.read_text(encoding="utf-8")
    try:
        return json.loads(health_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{out_path} (from `{' '.join(cmd)}`) is not valid JSON: {exc}\n"
            f"--- {out_path.name} (head) ---\n{health_text[:2000] or '<empty>'}\n"
            f"{diagnostics}"
        ) from exc


def cmd_emit_01e(args: argparse.Namespace) -> int:
    if not args.out and not args.out_dir:
        print("error: pass --out (single file) and/or --out-dir (sharded)", file=sys.stderr)
        return 2
    theorem_map = _load_json(args.map)
    scope = _load_json(args.scope)
    subgraphs = _load_subgraphs(args.subgraphs)

    if args.health_json:
        health = load_health(args.health_json)
    elif args.run_lean:
        health = index_health(_run_lean(theorem_map))
    else:
        print(
            "warning: no --health-json and no --run-lean; every property will be "
            "lean_status=unknown. Pass one to certify proofs.",
            file=sys.stderr,
        )
        health = {}

    gasper_source = theorem_map.get("gasper_source")
    gasper_ref = args.gasper_ref or theorem_map.get("gasper_ref")

    def _doc(props: list, shard: str | None = None) -> dict:
        d = {
            "phase": "01e",
            "provider": "lean",
            "gasper_source": gasper_source,
            "gasper_ref": gasper_ref,
        }
        if shard is not None:
            d["shard"] = shard
        d["properties"] = props
        return d

    def _summary(props: list) -> str:
        n_proved = sum(1 for p in props if p.get("lean_status") == "proved")
        n_scope = sum(1 for p in props if p.get("bug_bounty_eligible"))
        n_me = sum(1 for p in props if p.get("lean_precondition"))
        return (
            f"{len(props)} properties ({n_proved} proved, {n_scope} bug-bounty-eligible, "
            f"{n_me} must-establish-decomposed)"
        )

    def _flag_mismatches(props: list) -> None:
        """B5: surface (never silently drop) type-consistency mismatches."""
        bad = [p["property_id"] for p in props if p.get("lean_type_consistency") == "mismatch"]
        if bad:
            print(
                f"warning: type-consistency gate flagged {len(bad)} propert"
                f"{'y' if len(bad) == 1 else 'ies'}: {', '.join(bad)}",
                file=sys.stderr,
            )

    # Sharded output: one 01e_PARTIAL_<shard>.json per protocol-area group, so
    # per-file property count matches the benchmark granularity (M3).
    if args.out_dir:
        groups = build_properties_by_shard(theorem_map, health, scope, subgraphs, args.gasper_ref)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        for shard, props in groups.items():
            fp = out_dir / f"01e_PARTIAL_{shard}.json"
            fp.write_text(json.dumps(_doc(props, shard), indent=2, ensure_ascii=False), encoding="utf-8")
            total += len(props)
            _flag_mismatches(props)
            print(f"wrote {fp}: {_summary(props)}")
        print(f"total: {total} properties across {len(groups)} shard(s)")

    # Single-file output (back-compat; what speca's provider call uses).
    if args.out:
        properties = build_properties(theorem_map, health, scope, subgraphs, args.gasper_ref)
        Path(args.out).write_text(
            json.dumps(_doc(properties), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _flag_mismatches(properties)
        print(f"wrote {args.out}: {_summary(properties)}")
    return 0


def cmd_emit_kurtosis(args: argparse.Namespace) -> int:
    """Workstream E (issue #7): emit kurtosis_test fixture SCAFFOLDS.

    Builds the 01e properties (same pipeline as emit-01e), links each to its
    Executable decidable checker / witness (E1, data/checker_map.json), writes
    one fixture scaffold per checker-linked property under
    --fixtures-dir/<label>/<property_id>/ (E3), attaches label-matched
    ethereum-vuln-dataset evidence seeds (E6), and — with --out — writes the
    01e JSON with `checker`/`witness`/`kurtosis_test` populated.

    Honesty: scaffolds only. Nothing here runs a devnet; kurtosis_test stays
    null for properties without a real checker (see docs/kurtosis-bridge.md).
    """
    from .kurtosis import (
        attach_checkers, emit_kurtosis, load_checker_map, load_evidence_seeds,
    )

    theorem_map = _load_json(args.map)
    scope = _load_json(args.scope)
    subgraphs = _load_subgraphs(args.subgraphs)

    if args.health_json:
        health = load_health(args.health_json)
    elif args.run_lean:
        health = index_health(_run_lean(theorem_map))
    else:
        print(
            "warning: no --health-json and no --run-lean; every property will be "
            "lean_status=unknown. Pass one to certify proofs.",
            file=sys.stderr,
        )
        health = {}

    checker_map = load_checker_map(args.checker_map)
    seeds = load_evidence_seeds(args.evidence) if args.evidence else []

    props = build_properties(theorem_map, health, scope, subgraphs, args.gasper_ref)
    n_linked = attach_checkers(props, theorem_map, checker_map)
    written = emit_kurtosis(props, theorem_map, checker_map, args.fixtures_dir, seeds)
    n_seeded = sum(
        1 for fp in written
        if json.loads(fp.read_text(encoding="utf-8"))["evidence_seeds"]
    )
    n_null = sum(1 for p in props if not p.get("kurtosis_test"))
    print(
        f"{len(props)} properties: {n_linked} checker-linked (E1), "
        f"{len(written)} fixture scaffolds written to {args.fixtures_dir} (E3), "
        f"{n_seeded} with dataset evidence seeds (E6); "
        f"{n_null} honestly kurtosis_test=null (no Executable checker)"
    )

    if args.out:
        doc = {
            "phase": "01e",
            "provider": "lean",
            "gasper_source": theorem_map.get("gasper_source"),
            "gasper_ref": args.gasper_ref or theorem_map.get("gasper_ref"),
            "properties": props,
        }
        Path(args.out).write_text(
            json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"wrote {args.out}: 01e with checker/witness/kurtosis_test populated")
    return 0


def cmd_verify_precision(args: argparse.Namespace) -> int:
    from .precision import format_summary, verify_precision

    report = verify_precision(
        args.ours, args.benchmark_dir, args.findings_map, args.ours_dir,
        vulns_csv=args.vulns_csv, match_rules_path=args.match_rules,
        gaps_path=args.recall_gaps,
    )
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(format_summary(report))
    return 0


def cmd_verify_recall(args: argparse.Namespace) -> int:
    """D3/D6: label-grounded recall from the real emitted 01e — no benchmark
    corpus needed, so it can run in CI right after emit-01e."""
    from .recall import format_recall_summary, strict_problems, verify_recall

    report = verify_recall(args.ours, args.vulns_csv, args.match_rules, args.recall_gaps)
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(format_recall_summary(report))
    problems = strict_problems(report)
    if problems and args.strict:
        print("verify-recall --strict: FAILED", file=sys.stderr)
        return 1
    return 0


def _make_llm(cmd: str | None, what: str):
    from .judge import split_cmd, subprocess_llm

    if not cmd:
        print(
            f"error: {what} needs an LLM. Pass --llm-cmd (a command reading the "
            "prompt on stdin, writing the response on stdout — e.g. 'claude -p' "
            "on a runner where the Claude CLI is authenticated). This repo "
            "never reads an API key itself.",
            file=sys.stderr,
        )
        return None
    return subprocess_llm(split_cmd(cmd))


def _reference_distribution(args: argparse.Namespace, judge_fn) -> tuple[dict, list, str]:
    """Reference bar: reuse a previous report's reference scores when
    --ref-report is given (saves ~52 LLM calls), else judge the vendored
    solodit corpus now with the same blind rubric."""
    from .judge import checklist_items_from_solodit, judge_items, score_distribution

    if args.ref_report:
        prev = _load_json(args.ref_report)
        return prev["reference"], prev["reference_items"], prev["reference_source"]
    items = checklist_items_from_solodit(args.reference)
    scored = judge_items(items, judge_fn, args.retries, args.retry_wait)
    return score_distribution(scored), scored, str(args.reference)


def cmd_judge(args: argparse.Namespace) -> int:
    """Quality judge (speca#88 stage-2 eval). NOT recall: the verdict compares
    blind five-axis score DISTRIBUTIONS against the solodit reference bar;
    content matching enters nowhere."""
    from .judge import (
        checklist_items_from_01e, format_judge_summary, judge_items,
        meets_reference_bar, score_distribution,
    )

    judge_fn = _make_llm(args.llm_cmd, "judge")
    if judge_fn is None:
        return 2
    ours_items = checklist_items_from_01e(_load_json(args.ours), args.id_prefix)
    if not ours_items:
        print(f"error: no properties to judge in {args.ours} "
              f"(id prefix: {args.id_prefix or 'none'})", file=sys.stderr)
        return 2
    ref_dist, ref_items, ref_source = _reference_distribution(args, judge_fn)
    scored = judge_items(ours_items, judge_fn, args.retries, args.retry_wait)
    ours_dist = score_distribution(scored)
    meets, gaps = meets_reference_bar(ours_dist, ref_dist, args.axis_tolerance)
    report = {
        "reference_source": ref_source,
        "reference": ref_dist,
        "reference_items": ref_items,
        "ours_source": str(args.ours),
        "ours": ours_dist,
        "items": scored,
        "axis_tolerance": args.axis_tolerance,
        "meets_reference_bar": meets,
        "bar_gaps": gaps,
    }
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(format_judge_summary(report))
    if args.strict and not meets:
        print("judge --strict: below the reference bar", file=sys.stderr)
        return 1
    return 0


def cmd_improve(args: argparse.Namespace) -> int:
    """Improve loop (speca#88 stage-2): judge -> sharpen low scorers with the
    vuln dataset as teaching material -> re-judge, until the reference bar is
    met AND the last rounds plateau (both required)."""
    from .judge import (
        checklist_items_from_01e, format_improve_summary, improve_loop,
        load_vulns,
    )

    judge_fn = _make_llm(args.llm_cmd, "improve")
    if judge_fn is None:
        return 2
    improve_fn = _make_llm(args.improve_cmd, "improve") if args.improve_cmd else judge_fn

    doc = _load_json(args.ours)
    all_props = list(doc.get("properties", []))
    props = [
        p for p in all_props
        if not args.id_prefix or str(p.get("property_id", "")).startswith(args.id_prefix)
    ]
    if not props:
        print(f"error: no properties to improve in {args.ours} "
              f"(id prefix: {args.id_prefix or 'none'})", file=sys.stderr)
        return 2
    # sanity: the loop judges the same surface checklist_items_from_01e exposes
    assert [p["property_id"] for p in props] == [
        i["id"] for i in checklist_items_from_01e(doc, args.id_prefix)
    ]
    ref_dist, _ref_items, ref_source = _reference_distribution(args, judge_fn)

    result = improve_loop(
        props, ref_dist, load_vulns(args.vulns_csv), judge_fn, improve_fn,
        max_rounds=args.max_rounds, low_axis=args.low_axis,
        plateau_rounds=args.plateau_rounds, plateau_delta=args.plateau_delta,
        axis_tolerance=args.axis_tolerance,
        retries=args.retries, retry_wait=args.retry_wait,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = {k: v for k, v in result.items() if k != "properties"}
    log["reference_source"] = ref_source
    log["ours_source"] = str(args.ours)
    (out_dir / "score_log.json").write_text(
        json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    improved_doc = {k: v for k, v in doc.items() if k != "properties"}
    improved_doc["x_improve_note"] = (
        "proposal output of `speca-lean4 improve` (speca#88 stage-2 loop); the "
        "canonical checklist source stays theorem_map.json — landing these "
        "rewrites there is a reviewed, manual step"
    )
    improved_doc["properties"] = result["properties"]
    (out_dir / "improved_01e.json").write_text(
        json.dumps(improved_doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(format_improve_summary(result))
    print(f"wrote {out_dir / 'score_log.json'} and {out_dir / 'improved_01e.json'}")
    if args.strict and not result["converged"]:
        print("improve --strict: loop did not converge", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="speca-lean4", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("emit-01e", help="emit 01e properties from gasper-lean4 theorems")
    e.add_argument("--scope", required=True, help="path to BUG_BOUNTY_SCOPE.json")
    e.add_argument("--map", default=str(_DEFAULT_MAP), help="theorem_map.json (default: repo root)")
    e.add_argument("--subgraphs", nargs="*", help="01b subgraph JSON glob(s) for covers resolution")
    e.add_argument("--gasper-ref", help="gasper-lean4 git ref to pin (overrides theorem_map)")
    src = e.add_mutually_exclusive_group()
    src.add_argument("--health-json", help="precomputed speca-export health JSON")
    src.add_argument("--run-lean", action="store_true", help="run `lake exe speca-export` now")
    e.add_argument("--out", help="single-file output 01e_PARTIAL JSON path (speca provider call)")
    e.add_argument(
        "--out-dir",
        help="sharded output: write one 01e_PARTIAL_<shard>.json per theorem_map shard here",
    )
    e.set_defaults(func=cmd_emit_01e)

    k = sub.add_parser(
        "emit-kurtosis",
        help="emit kurtosis_test fixture scaffolds per checker-linked property (issue #7 E1/E3/E6)",
    )
    k.add_argument("--scope", required=True, help="path to BUG_BOUNTY_SCOPE.json")
    k.add_argument("--map", default=str(_DEFAULT_MAP), help="theorem_map.json (default: repo root)")
    k.add_argument(
        "--checker-map", default=str(_REPO_ROOT / "data" / "checker_map.json"),
        help="E1 theorem -> Executable checker/witness map (default: data/checker_map.json)",
    )
    k.add_argument(
        "--evidence", default=str(_REPO_ROOT / "data" / "evidence_seeds.json"),
        help="E6 ethereum-vuln-dataset evidence seeds (default: data/evidence_seeds.json; '' to skip)",
    )
    k.add_argument("--subgraphs", nargs="*", help="01b subgraph JSON glob(s) for covers resolution")
    k.add_argument("--gasper-ref", help="gasper-lean4 git ref to pin (overrides theorem_map)")
    ksrc = k.add_mutually_exclusive_group()
    ksrc.add_argument("--health-json", help="precomputed speca-export health JSON")
    ksrc.add_argument("--run-lean", action="store_true", help="run `lake exe speca-export` now")
    k.add_argument(
        "--fixtures-dir", default="outputs/kurtosis",
        help="where fixture scaffolds go: <dir>/<label>/<property_id>/ (default: outputs/kurtosis)",
    )
    k.add_argument("--out", help="also write the 01e JSON with checker/witness/kurtosis_test populated")
    k.set_defaults(func=cmd_emit_kurtosis)

    v = sub.add_parser(
        "verify-precision",
        help="measure granularity vs the rq2a 01e benchmark and label-grounded "
             "recall vs the vendored ethereum-vuln-dataset slice",
    )
    v.add_argument("--ours", required=True, help="our generated 01e JSON (single-file, for recall + vocab)")
    v.add_argument(
        "--ours-dir",
        help="directory of our sharded 01e_PARTIAL_<shard>.json files, for per-shard props/file granularity",
    )
    v.add_argument(
        "--benchmark-dir", required=True,
        help="directory containing the restored bench-rq2a-20260508-speca 01e_*.json files",
    )
    v.add_argument(
        "--findings-map", default=str(_REPO_ROOT / "data" / "findings_map.json"),
        help="DEPRECATED prose judgment table, reported for continuity only "
             "(default: data/findings_map.json)",
    )
    _add_recall_data_args(v)
    v.add_argument("--out", help="write the full JSON report here")
    v.set_defaults(func=cmd_verify_precision)

    r = sub.add_parser(
        "verify-recall",
        help="label-grounded recall (D6) of the emitted 01e vs the vendored "
             "ethereum-vuln-dataset slice; no benchmark corpus needed",
    )
    r.add_argument("--ours", required=True, help="our generated 01e JSON (single-file)")
    _add_recall_data_args(r)
    r.add_argument("--out", help="write the full JSON recall report here")
    r.add_argument(
        "--strict", action="store_true",
        help="exit non-zero on untriaged uncovered findings, stale gap entries, "
             "or rules claiming coverage via non-emitted properties",
    )
    r.set_defaults(func=cmd_verify_recall)

    j = sub.add_parser(
        "judge",
        help="LLM-as-judge quality eval of a 01e checklist (speca#88 stage-2): "
             "five-axis blind scoring calibrated against the vendored solodit "
             "reference bar. NOT recall — no content matching in the verdict.",
    )
    j.add_argument("--ours", required=True, help="the 01e JSON to judge (e.g. 01e_PARTIAL_checklist-high-angle.json)")
    j.add_argument("--id-prefix", help="only judge properties whose property_id starts with this (e.g. CHK-)")
    _add_judge_common_args(j)
    j.add_argument("--out", help="write the full JSON judge report here")
    j.add_argument(
        "--strict", action="store_true",
        help="exit non-zero when the score distribution is below the reference bar",
    )
    j.set_defaults(func=cmd_judge)

    i = sub.add_parser(
        "improve",
        help="judge -> sharpen low scorers (vuln dataset rows as teaching "
             "material) -> re-judge, until reference-bar met AND plateaued "
             "(both required); logs per-round score progression",
    )
    i.add_argument("--ours", required=True, help="the 01e JSON whose properties get improved")
    i.add_argument("--id-prefix", help="only loop over properties whose property_id starts with this (e.g. CHK-)")
    _add_judge_common_args(i)
    i.add_argument(
        "--improve-cmd",
        help="separate LLM command for the improve step (default: same as --llm-cmd)",
    )
    i.add_argument(
        "--vulns-csv", default=str(_REPO_ROOT / "data" / "ethereum_vulns.csv"),
        help="vuln dataset slice used as improve teaching material, never as an "
             "eval denominator (default: data/ethereum_vulns.csv)",
    )
    i.add_argument("--out-dir", required=True, help="write score_log.json + improved_01e.json here")
    i.add_argument("--max-rounds", type=int, default=6, help="hard cap on improve rounds (default 6)")
    i.add_argument("--low-axis", type=int, default=3, help="an item with any axis <= this is an improve candidate (default 3)")
    i.add_argument("--plateau-rounds", type=int, default=3, help="rounds that must be flat to call 頭打ち (default 3)")
    i.add_argument("--plateau-delta", type=float, default=0.05, help="max overall-mean gain still counted as flat (default 0.05)")
    i.add_argument(
        "--strict", action="store_true",
        help="exit non-zero when the loop ends without convergence",
    )
    i.set_defaults(func=cmd_improve)
    return p


def _add_judge_common_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--reference", default=str(_REPO_ROOT / "data" / "solodit_checklist.csv"),
        help="reference checklist CSV for the calibration bar "
             "(default: data/solodit_checklist.csv, vendored from speca)",
    )
    sp.add_argument(
        "--ref-report",
        help="reuse the reference scores from a previous `judge --out` report "
             "instead of re-judging the reference corpus",
    )
    sp.add_argument(
        "--llm-cmd",
        help="LLM adapter command: reads one prompt on stdin, writes the "
             "response on stdout (e.g. 'claude -p'). Required; this repo holds "
             "no API key",
    )
    sp.add_argument(
        "--axis-tolerance", type=float, default=0.25,
        help="how far one axis mean may fall below the reference axis mean "
             "while still passing (default 0.25)",
    )
    sp.add_argument(
        "--retries", type=int, default=2,
        help="attempts per item beyond the first, covering bad responses AND "
             "transient adapter failures (default 2); an item still failing "
             "after that aborts the run — never silently skipped",
    )
    sp.add_argument(
        "--retry-wait", type=float, default=5.0,
        help="seconds between attempts, letting rate-limit blips pass (default 5)",
    )


def _add_recall_data_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--vulns-csv", default=str(_REPO_ROOT / "data" / "ethereum_vulns.csv"),
        help="vendored ethereum-vuln-dataset consensus slice (default: data/ethereum_vulns.csv)",
    )
    sp.add_argument(
        "--match-rules", default=str(_REPO_ROOT / "data" / "label_match_rules.json"),
        help="domain filter + (label, root_cause) coverage rules (default: data/label_match_rules.json)",
    )
    sp.add_argument(
        "--recall-gaps", default=str(_REPO_ROOT / "data" / "recall_gaps.json"),
        help="D2 gap triage table (default: data/recall_gaps.json)",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
