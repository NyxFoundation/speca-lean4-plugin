"""`speca-lean4` — the subprocess/CLI contract that speca's `lean` provider calls.

    speca-lean4 emit-01e \
        --scope BUG_BOUNTY_SCOPE.json \
        [--map theorem_map.json] \
        [--subgraphs 01b_PARTIAL_glob ...] \
        [--gasper-ref <git-sha>] \
        (--health-json health.json | --run-lean) \
        --out 01e_PARTIAL_lean.json

Health source (Stage B) is one of:
  --health-json   a precomputed proof-health JSON from `lake exe speca-export`
  --run-lean      run `lake exe speca-export` in ./lean now (requires the Lean
                  toolchain; writes the target list from the theorem map)

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
from .mapping import build_properties

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


def _run_lean(theorem_map: dict[str, Any]) -> dict[str, Any]:
    """Write the target list and invoke `lake exe speca-export`, returning parsed health."""
    targets = [e["theorem"] for e in theorem_map.get("properties", [])]
    with tempfile.NamedTemporaryFile("w", suffix=".targets", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(targets) + "\n")
        targets_path = fh.name
    proc = subprocess.run(
        ["lake", "exe", "speca-export", "--targets", targets_path],
        cwd=str(_LEAN_DIR), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"lake exe speca-export failed (rc={proc.returncode}):\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def cmd_emit_01e(args: argparse.Namespace) -> int:
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

    properties = build_properties(theorem_map, health, scope, subgraphs, args.gasper_ref)

    out = {
        "phase": "01e",
        "provider": "lean",
        "gasper_source": theorem_map.get("gasper_source"),
        "gasper_ref": args.gasper_ref or theorem_map.get("gasper_ref"),
        "properties": properties,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    n_proved = sum(1 for p in properties if p.get("lean_status") == "proved")
    n_scope = sum(1 for p in properties if p.get("bug_bounty_eligible"))
    print(
        f"wrote {len(properties)} properties to {args.out} "
        f"({n_proved} proved, {n_scope} bug-bounty-eligible)"
    )
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
    e.add_argument("--out", required=True, help="output 01e_PARTIAL JSON path")
    e.set_defaults(func=cmd_emit_01e)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
