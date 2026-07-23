"""Stage-2 quality judge + improve loop (speca#88 confirmed direction).

eval here is NOT recall. The #88 direction comment ("重要な訂正") is explicit:
the goal is not to reproduce the vulnerability dataset's specific bugs, but to
reach the SAME QUALITY LEVEL as a professional audit checklist. So:

- eval  = LLM-as-judge scoring on five fixed axes (below), calibrated against
  the vendored solodit reference checklist (`data/solodit_checklist.csv`):
  the judge scores the reference corpus and the generated 01e corpus with the
  SAME blind rubric, and the generated score distribution must be at least as
  good as the reference distribution. No content matching against either the
  reference or the dataset enters the verdict anywhere.
- the vuln dataset (`data/ethereum_vulns.csv`) is the IMPROVE-STEP TEACHING
  MATERIAL only — never an eval denominator. (`recall.py`'s label recall is a
  side reference number, deliberately outside the judge verdict.)

Five axes (1-5 each, fixed rubric in `RUBRIC`):
  specificity              — code-level check, not a spec restatement
  implementation_readiness — targets surfaces where implementations really
                             break (arithmetic width/bounds/resources/termination)
  generality               — not glued to one client's historical bug
  actionability            — an auditor can apply it to code as written
  granularity              — one auditable concern, no redundant bundling

Loop (matches the #88 comment verbatim):
  1. generate  — reuse the existing emit-01e / CHK-15 output (NOT re-implemented)
  2. judge     — score every item on the five axes
  3. improve   — low scorers get (a) the item, (b) the judge critique,
                 (c) matching vuln-dataset rows, and are sharpened
  4. re-judge  — repeat 2-3
  5. converge  — stop only when BOTH hold: the score distribution meets the
                 reference bar AND the last `plateau_rounds` rounds are flat
                 (頭打ち). Neither condition alone stops the loop; a
                 `max_rounds` cap ends an unconverged run honestly
                 (`converged: false`, reason recorded). Per-round score
                 progression is logged.

LLM access is INJECTED (`judge_fn` / `improve_fn`: prompt str -> response
str). This module never reads an API key and never imports an LLM SDK: unit
tests inject deterministic mocks; the CLI wires a subprocess command (e.g. a
self-hosted authenticated `claude -p`) via `subprocess_llm`.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .schema import validate_property

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_CSV = _REPO_ROOT / "data" / "solodit_checklist.csv"
DEFAULT_VULNS_CSV = _REPO_ROOT / "data" / "ethereum_vulns.csv"

LLMFn = Callable[[str], str]

AXES = (
    "specificity",
    "implementation_readiness",
    "generality",
    "actionability",
    "granularity",
)
SCORE_MIN, SCORE_MAX = 1, 5

# Improve may only rewrite the checklist surface of a property; everything
# else (identity, provenance, lean_status, label, severity, reachability...)
# is immutable, so an "improvement" can never quietly upgrade its own honesty
# metadata.
MUTABLE_FIELDS = ("text", "assertion")

# Benchmark granularity band (tests/test_mapping: benchmark assertions are
# 94±15 chars, text ≤260). A rewrite may sharpen an item but must stay ONE
# auditable concern at benchmark width — an unbounded multi-check blob is a
# granularity regression, not concreteness. These caps are the deterministic
# backstop; the improve prompt also asks for terse, single-concern output.
TEXT_MAX = 260
ASSERTION_MAX = 160

# Severity model. The teaching corpus (data/ethereum_vulns_high.csv) tags each
# row with the Ethereum Foundation bug-bounty severity — network-scale impact
# reachable REMOTELY by a single message / transaction (the dataset's
# `severity_estimated`, calibrated against the bounty-graded rows). Surfacing
# the definition to the model keeps a sharpened/generated critical/high item
# aimed at that threat model, not at a locally-triggered or low-impact defect.
# Stated defensively (what to PREVENT), no exploitation detail.
EF_BOUNTY_SEVERITY = (
    "Severity follows the Ethereum Foundation bug-bounty model: a defect's "
    "severity is the network-scale impact an attacker could reach REMOTELY with "
    "a single message or transaction. Critical = whole-network halt, "
    "fund-integrity break at scale, or majority validator slashing; High = a "
    "chain split / halt / slashing affecting roughly a third of the network; "
    "Medium = a few-percent-scale version. Keep the check aimed at preventing "
    "the highest-impact, remotely-reachable failure of this invariant — not a "
    "locally-triggered or cosmetic one."
)

# Deterministic generality lint: an improved item must not hard-code a client
# or implementation name lifted from the evidence rows (that would optimize
# the generality axis's exact failure mode).
_CLIENT_NAMES = (
    "lighthouse", "prysm", "teku", "nimbus", "lodestar", "grandine",
    "geth", "erigon", "nethermind", "besu", "reth", "blst",
)
_CLIENT_RE = re.compile(
    r"\b(" + "|".join(_CLIENT_NAMES) + r")\b", re.IGNORECASE
)

RUBRIC = """Score ONE audit-checklist item. Such an item tells a security
auditor what to inspect in the implementation source code of a protocol.

Score five axes, each an integer 1-5. Anchors:

specificity — is it a code-level check, not a specification restatement?
  1: restates a spec/theorem sentence in prose; nothing points at code.
  3: names the code area, but the condition to check stays abstract.
  5: names the exact code-level condition (field, arithmetic operation,
     boundary, comparison set) that must hold.

implementation_readiness — does it target a surface where implementations
actually break (arithmetic width, overflow/underflow, bounds/indexing,
resource caps, termination, type fidelity, boundary conditions)?
  1: an abstract property no concrete implementation would ever fail.
  3: mentions a real failure surface but does not pin the failure mode.
  5: pins a concrete failure mode on a concrete surface (e.g. "u64 value
     above 2^53 in a lossy numeric type", "index used before bounds check").

generality — does it apply beyond one specific historical incident?
  1: only re-describes one bug in one codebase; useless elsewhere.
  3: generalizes the incident but keeps incidental specifics.
  5: any implementation of this protocol area can be audited against it.

actionability — can an auditor apply it to code as written?
  1: the auditor must reformulate it before it is checkable.
  3: checkable, but where to look / what failure looks like is left implicit.
  5: says what to locate and what the violation looks like; directly usable.

granularity — is it one auditable concern at auditable width?
  1: several unrelated checks bundled, or a vague catch-all.
  3: mostly one concern, with some bundling or overlap.
  5: exactly one concern, neither trivially narrow nor a grab-bag.

Return STRICT JSON only (no markdown, no surrounding prose):
{"scores": {"specificity": n, "implementation_readiness": n, "generality": n,
"actionability": n, "granularity": n}, "critique": "<=60 words naming the weakest axes and why"}"""


class JudgeError(RuntimeError):
    """A judge/improve LLM response could not be used (after retries)."""


# --------------------------------------------------------------- item loading

def checklist_items_from_01e(doc: Any, id_prefix: str | None = None) -> list[dict[str, str]]:
    """Normalize emitted 01e properties to blind judge items.

    Only the checklist surface (`text` + `assertion`) is exposed to the judge:
    provenance fields (x_dataset_evidence and friends) never reach the prompt,
    so the verdict cannot reward dataset-content matching, and the judge
    cannot tell a generated item from a reference item by shape.
    """
    props = doc.get("properties", []) if isinstance(doc, dict) else list(doc)
    items = []
    for p in props:
        pid = str(p.get("property_id", ""))
        if id_prefix and not pid.startswith(id_prefix):
            continue
        items.append({
            "id": pid,
            "check": str(p.get("text", "")),
            "detail": str(p.get("assertion", "")),
        })
    return items


def checklist_items_from_solodit(csv_path: str | Path = DEFAULT_REFERENCE_CSV) -> list[dict[str, str]]:
    """Normalize the vendored solodit reference rows to the same blind shape."""
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [
        {
            "id": str(r.get("id", "")),
            "check": str(r.get("question", "")),
            "detail": str(r.get("description", "")),
        }
        for r in rows
    ]


# ------------------------------------------------------------------- judging

def build_judge_prompt(item: dict[str, str]) -> str:
    """Rubric + the item's checklist surface. Deliberately blind: no ids, no
    corpus identity, no provenance — identical framing for reference and
    generated items so the calibration is fair."""
    return (
        f"{RUBRIC}\n\n"
        f"Item to score:\n"
        f"CHECK: {item['check']}\n"
        f"DETAIL: {item['detail']}\n"
    )


def _extract_json(text: str) -> dict[str, Any]:
    """First JSON object anywhere in `text` (LLMs love to wrap JSON in prose)."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise JudgeError(f"no JSON object in response: {text[:200]!r}")


def parse_judge_response(text: str) -> dict[str, Any]:
    """Validate a judge response into {"scores": {axis: int}, "critique": str}.

    Every axis must be present and an integer in [1, 5] — a missing or
    out-of-range axis is an error, never silently clamped or defaulted.
    """
    obj = _extract_json(text)
    raw = obj.get("scores")
    if not isinstance(raw, dict):
        raise JudgeError(f"response has no 'scores' object: {obj!r}")
    scores: dict[str, int] = {}
    for ax in AXES:
        v = raw.get(ax)
        if isinstance(v, bool) or not isinstance(v, int):
            raise JudgeError(f"axis {ax!r} missing or not an integer: {v!r}")
        if not SCORE_MIN <= v <= SCORE_MAX:
            raise JudgeError(f"axis {ax!r} out of range [1,5]: {v}")
        scores[ax] = v
    critique = obj.get("critique")
    if not isinstance(critique, str) or not critique.strip():
        raise JudgeError("response has no non-empty 'critique' string")
    return {"scores": scores, "critique": critique.strip()}


def judge_item(
    item: dict[str, str], judge_fn: LLMFn, retries: int = 1, retry_wait: float = 0.0
) -> dict[str, Any]:
    """`retries` covers BOTH bad responses and transient adapter failures
    (e.g. a real CLI intermittently exiting non-zero mid-run); `retry_wait`
    seconds between attempts lets rate-limit blips pass. After the retries
    the error surfaces — an unscorable item is never silently skipped."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        if attempt and retry_wait > 0:
            time.sleep(retry_wait)
        try:
            parsed = parse_judge_response(judge_fn(build_judge_prompt(item)))
            return {
                "id": item["id"],
                "scores": parsed["scores"],
                "overall": round(statistics.mean(parsed["scores"].values()), 3),
                "critique": parsed["critique"],
            }
        except JudgeError as exc:
            last = exc
    raise JudgeError(f"item {item['id']}: {last}")


def judge_items(
    items: list[dict[str, str]], judge_fn: LLMFn, retries: int = 1, retry_wait: float = 0.0
) -> list[dict[str, Any]]:
    if not items:
        raise JudgeError("no items to judge")
    return [judge_item(it, judge_fn, retries, retry_wait) for it in items]


# ----------------------------------------------------- distributions and bar

def score_distribution(scored: list[dict[str, Any]]) -> dict[str, Any]:
    overalls = [s["overall"] for s in scored]
    return {
        "n": len(scored),
        "axis_means": {
            ax: round(statistics.mean(s["scores"][ax] for s in scored), 3)
            for ax in AXES
        },
        "overall_mean": round(statistics.mean(overalls), 3),
        "overall_median": round(statistics.median(overalls), 3),
        "overall_min": round(min(overalls), 3),
    }


def meets_reference_bar(
    ours: dict[str, Any], reference: dict[str, Any], axis_tolerance: float = 0.25
) -> tuple[bool, list[str]]:
    """同等以上: our overall mean >= the reference overall mean, AND no axis
    mean falls more than `axis_tolerance` below its reference axis mean (so a
    single pumped axis cannot buy the verdict). Distribution-level only —
    content similarity plays no part."""
    gaps: list[str] = []
    if ours["overall_mean"] < reference["overall_mean"]:
        gaps.append(
            f"overall_mean {ours['overall_mean']} < reference {reference['overall_mean']}"
        )
    for ax in AXES:
        lo = reference["axis_means"][ax] - axis_tolerance
        if ours["axis_means"][ax] < lo:
            gaps.append(
                f"{ax} mean {ours['axis_means'][ax]} < reference "
                f"{reference['axis_means'][ax]} - tolerance {axis_tolerance}"
            )
    return (not gaps), gaps


def plateaued(history: list[float], rounds: int = 3, delta: float = 0.05) -> bool:
    """頭打ち: over the last `rounds` recorded rounds, no round improved on the
    earliest of that window by more than `delta`. Needs at least `rounds`
    entries — a fresh run can never claim a plateau."""
    if len(history) < rounds:
        return False
    window = history[-rounds:]
    return max(window) - window[0] <= delta


# ------------------------------------------------------------------- improve

def select_low_items(
    scored: list[dict[str, Any]], reference: dict[str, Any], low_axis: int = 3
) -> list[dict[str, Any]]:
    """An item needs improvement if its overall is below the reference overall
    mean, or any single axis is at/below `low_axis`."""
    bar = reference["overall_mean"]
    return [
        s for s in scored
        if s["overall"] < bar or min(s["scores"].values()) <= low_axis
    ]


_SEV_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def load_vulns(csv_path: str | Path = DEFAULT_VULNS_CSV) -> list[dict[str, str]]:
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def select_evidence(
    label: str, vulns: list[dict[str, str]], n: int = 3
) -> list[dict[str, str]]:
    """Teaching-material rows for one item's failure class: same dataset
    `label` first; if the label has no rows (e.g. fork-choice is outside the
    vendored consensus slice), fall back to Critical/High rows of any label so
    the improver still sees how real clients break. Deterministic order."""
    same = [v for v in vulns if v.get("label") == label]
    pool = same or [v for v in vulns if v.get("severity") in ("Critical", "High")] or list(vulns)
    pool = sorted(pool, key=lambda v: (_SEV_RANK.get(v.get("severity", ""), 9), v.get("id", "")))
    # Class-level fields only. The concrete-incident fields (`title`,
    # `attack_path`) are deliberately NOT surfaced to the improve LLM: the loop
    # sharpens a *defensive* checklist item from the failure CLASS, and feeding
    # a specific exploit's title/attack-path reads as offensive tasking, which
    # trips the model's cyber safeguard and aborts the loop (speca#143). `id`
    # is a corpus hash kept only for traceability.
    keep = ("id", "severity", "label", "root_cause")
    return [{k: v.get(k, "") for k in keep} for v in pool[:n]]


def build_improve_prompt(
    prop: dict[str, Any], scored: dict[str, Any], evidence: list[dict[str, str]]
) -> str:
    ev_lines = "\n".join(
        f"- [{e['id']}] {e['severity']} — {e['label']} / {e['root_cause']}"
        for e in evidence
    )
    return (
        # Defensive framing up front, and only failure-CLASS signals below (no
        # exploit title / attack-path): a specific-incident framing tripped the
        # model cyber safeguard and aborted the loop (speca#143).
        "You are sharpening ONE audit-checklist item — a DEFENSIVE review "
        "control a security auditor applies to implementation source code to "
        "DETECT and PREVENT a class of defect.\n\n"
        "Current item:\n"
        f"TEXT: {prop.get('text', '')}\n"
        f"ASSERTION: {prop.get('assertion', '')}\n\n"
        f"Judge scores (1-5): {json.dumps(scored['scores'])}\n"
        f"Judge critique: {scored['critique']}\n\n"
        f"{EF_BOUNTY_SEVERITY}\n\n"
        "Defect CLASSES seen historically in this area (categories only, for "
        "audit coverage — arithmetic width, bounds/indexing, resource caps, "
        "termination, type fidelity), each tagged with its bug-bounty severity:\n"
        f"{ev_lines}\n\n"
        "Rewrite the item to raise the weak axes. Rules:\n"
        "- Keep the same underlying invariant; sharpen it to the code-level "
        "condition and concrete failure mode an implementation would hit.\n"
        "- Stay general: NEVER name a specific client or implementation "
        "(e.g. a client name from the evidence) in the rewritten item.\n"
        "- ONE auditable concern only. Do NOT bundle several checks; if the "
        "item covers multiple, keep the single most important one. Concrete is "
        "not the same as long.\n"
        f"- TEXT: one imperative, code-level checklist sentence, <= {TEXT_MAX} "
        "characters.\n"
        f"- ASSERTION: a compact machine-readable condition sketch, "
        f"<= {ASSERTION_MAX} characters.\n"
        "Return STRICT JSON only: {\"text\": \"...\", \"assertion\": \"...\"}"
    )


def apply_improvement(prop: dict[str, Any], response_text: str) -> tuple[dict[str, Any] | None, str]:
    """Validate an improve response against `prop`. Returns (new_prop, reason);
    new_prop is None when the improvement is rejected (original kept).

    Guards (all deterministic):
    - only MUTABLE_FIELDS are taken from the response; at least one must be a
      non-empty string;
    - the merged property must still pass schema.validate_property;
    - the generality lint: no client/implementation name may enter the item;
    - every immutable field is byte-identical afterwards by construction.
    """
    try:
        obj = _extract_json(response_text)
    except JudgeError as exc:
        return None, f"rejected: {exc}"
    changes: dict[str, str] = {}
    for k in MUTABLE_FIELDS:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            changes[k] = v.strip()
    if not changes:
        return None, "rejected: response contains no usable mutable field (text/assertion)"
    ignored = sorted(set(obj) - set(MUTABLE_FIELDS))
    for v in changes.values():
        m = _CLIENT_RE.search(v)
        if m:
            return None, f"rejected: client name {m.group(0)!r} in rewritten item (generality lint)"
    # granularity backstop: keep the sharpened item at benchmark width (one
    # auditable concern), never let it grow into an unbounded multi-check blob
    if "text" in changes and len(changes["text"]) > TEXT_MAX:
        return None, f"rejected: text {len(changes['text'])} chars > {TEXT_MAX} (granularity/length cap)"
    if "assertion" in changes and len(changes["assertion"]) > ASSERTION_MAX:
        return None, (
            f"rejected: assertion {len(changes['assertion'])} chars > "
            f"{ASSERTION_MAX} (granularity/length cap)"
        )
    new_prop = dict(prop)
    new_prop.update(changes)
    problems = validate_property(new_prop)
    if problems:
        return None, f"rejected: merged property fails schema: {problems}"
    reason = "accepted"
    if ignored:
        reason += f" (ignored non-mutable keys: {', '.join(ignored)})"
    return new_prop, reason


# ---------------------------------------------------------------------- loop

def improve_loop(
    props: list[dict[str, Any]],
    reference: dict[str, Any],
    vulns: list[dict[str, str]],
    judge_fn: LLMFn,
    improve_fn: LLMFn,
    *,
    max_rounds: int = 6,
    low_axis: int = 3,
    plateau_rounds: int = 3,
    plateau_delta: float = 0.05,
    axis_tolerance: float = 0.25,
    evidence_n: int = 3,
    retries: int = 1,
    retry_wait: float = 0.0,
) -> dict[str, Any]:
    """Judge -> improve -> re-judge until convergence.

    Convergence needs BOTH: `meets_reference_bar` AND `plateaued` over the
    last `plateau_rounds` rounds. Bar-met-but-still-climbing keeps going;
    plateaued-below-bar keeps going until `max_rounds`, then stops with
    `converged: false` and the reason recorded — never dressed up as success.

    Returns {"rounds": [...], "history_overall_mean": [...], "converged":
    bool, "stop_reason": str, "properties": final props}.
    """
    if not props:
        raise JudgeError("no properties to improve")
    props = [dict(p) for p in props]
    by_id = {str(p.get("property_id", "")): p for p in props}
    if len(by_id) != len(props):
        raise JudgeError("duplicate or missing property_id among input properties")

    def _judge_all(only_ids: set[str] | None, prev: dict[str, dict] | None) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for pid, p in by_id.items():
            if only_ids is not None and pid not in only_ids and prev is not None:
                out[pid] = prev[pid]
                continue
            item = {"id": pid, "check": str(p.get("text", "")), "detail": str(p.get("assertion", ""))}
            out[pid] = judge_item(item, judge_fn, retries, retry_wait)
        return out

    scored = _judge_all(None, None)
    dist = score_distribution(list(scored.values()))
    history = [dist["overall_mean"]]
    meets, gaps = meets_reference_bar(dist, reference, axis_tolerance)
    rounds: list[dict[str, Any]] = [{
        "round": 0,
        "distribution": dist,
        "meets_reference_bar": meets,
        "bar_gaps": gaps,
        "n_improve_candidates": 0,
        "improvements": [],
        "items": sorted(scored.values(), key=lambda s: s["id"]),
    }]

    converged = False
    stop_reason = ""
    for rnd in range(1, max_rounds + 1):
        meets, _ = meets_reference_bar(dist, reference, axis_tolerance)
        if meets and plateaued(history, plateau_rounds, plateau_delta):
            converged = True
            stop_reason = "reference_bar_met_and_plateaued"
            break

        low = select_low_items(list(scored.values()), reference, low_axis)
        improvements: list[dict[str, str]] = []
        changed: set[str] = set()
        for s in sorted(low, key=lambda s: s["id"]):
            pid = s["id"]
            prop = by_id[pid]
            evidence = select_evidence(str(prop.get("label", "")), vulns, evidence_n)
            new_prop, reason = apply_improvement(
                prop, improve_fn(build_improve_prompt(prop, s, evidence))
            )
            improvements.append({"id": pid, "result": reason})
            if new_prop is not None and any(
                new_prop.get(k) != prop.get(k) for k in MUTABLE_FIELDS
            ):
                by_id[pid] = new_prop
                changed.add(pid)

        scored = _judge_all(changed, scored)
        dist = score_distribution(list(scored.values()))
        history.append(dist["overall_mean"])
        meets, gaps = meets_reference_bar(dist, reference, axis_tolerance)
        rounds.append({
            "round": rnd,
            "distribution": dist,
            "meets_reference_bar": meets,
            "bar_gaps": gaps,
            "n_improve_candidates": len(low),
            "improvements": improvements,
            "items": sorted(scored.values(), key=lambda s: s["id"]),
        })
    else:
        meets, _ = meets_reference_bar(dist, reference, axis_tolerance)
        if meets and plateaued(history, plateau_rounds, plateau_delta):
            converged = True
            stop_reason = "reference_bar_met_and_plateaued"
        else:
            stop_reason = "max_rounds_reached_without_convergence"

    return {
        "reference": reference,
        "params": {
            "max_rounds": max_rounds,
            "low_axis": low_axis,
            "plateau_rounds": plateau_rounds,
            "plateau_delta": plateau_delta,
            "axis_tolerance": axis_tolerance,
        },
        "rounds": rounds,
        "history_overall_mean": history,
        "converged": converged,
        "stop_reason": stop_reason,
        "properties": [by_id[str(p["property_id"])] for p in props],
    }


# ------------------------------------------------------------ LLM subprocess

def split_cmd(cmd: str) -> list[str]:
    """Split an --llm-cmd string portably. POSIX shlex eats Windows path
    backslashes, so on nt we split in non-POSIX mode and strip quotes."""
    import os
    import shlex
    if os.name == "nt":
        return [t.strip('"') for t in shlex.split(cmd, posix=False)]
    return shlex.split(cmd)


def subprocess_llm(cmd: list[str], timeout: int = 600) -> LLMFn:
    """LLM adapter: run `cmd`, prompt on stdin, response on stdout.

    This is the ONLY place an actual LLM binding exists, and it is still just
    a subprocess: e.g. `claude -p` on a self-hosted runner where the CLI is
    already authenticated. No API key is read or forwarded here.
    """
    def call(prompt: str) -> str:
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                encoding="utf-8", timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            # surface as JudgeError so judge_item's retries cover a hung
            # adapter process the same as a non-zero exit
            raise JudgeError(
                f"llm command {' '.join(cmd)!r} hit the {timeout}s timeout"
            ) from exc
        if proc.returncode != 0:
            raise JudgeError(
                f"llm command {' '.join(cmd)!r} failed (rc={proc.returncode}); "
                f"stderr tail: {(proc.stderr or '<empty>')[-500:]} "
                f"stdout tail: {(proc.stdout or '<empty>')[-200:]}"
            )
        return proc.stdout
    return call


# ---------------------------------------------------------------- formatting

def format_judge_summary(report: dict[str, Any]) -> str:
    ref, ours = report["reference"], report["ours"]
    lines = [
        f"reference bar ({report['reference_source']}, n={ref['n']}): "
        f"overall mean {ref['overall_mean']}, axes {ref['axis_means']}",
        f"ours ({report['ours_source']}, n={ours['n']}): "
        f"overall mean {ours['overall_mean']}, axes {ours['axis_means']}",
        f"meets reference bar (axis tolerance {report['axis_tolerance']}): "
        f"{report['meets_reference_bar']}",
    ]
    for g in report["bar_gaps"]:
        lines.append(f"  GAP: {g}")
    for s in report["items"]:
        lines.append(f"  {s['id']}: overall {s['overall']} {s['scores']}")
    return "\n".join(lines)


def format_improve_summary(result: dict[str, Any]) -> str:
    lines = [
        f"improve loop: {len(result['rounds'])} round(s), converged={result['converged']} "
        f"({result['stop_reason']})",
        f"overall-mean progression: {result['history_overall_mean']}",
    ]
    for r in result["rounds"]:
        lines.append(
            f"  round {r['round']}: overall {r['distribution']['overall_mean']} "
            f"meets_bar={r['meets_reference_bar']} "
            f"improved {sum(1 for i in r['improvements'] if i['result'].startswith('accepted'))}"
            f"/{r['n_improve_candidates']} candidates"
        )
    return "\n".join(lines)
