"""Tests for the speca#88 stage-2 quality judge + improve loop.

Everything here runs WITHOUT an LLM: the pure logic (prompt construction,
response parsing, distribution math, bar verdict, plateau/convergence, the
improve guards) is exercised with deterministic injected functions, and the
CLI wiring with the `tests/fixtures/mock_llm.py` subprocess stand-in. The
design point under test throughout: eval is a QUALITY-distribution
comparison, never content matching (not recall).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from speca_lean4.judge import (
    AXES,
    JudgeError,
    apply_improvement,
    build_improve_prompt,
    build_judge_prompt,
    checklist_items_from_01e,
    checklist_items_from_solodit,
    improve_loop,
    judge_item,
    judge_items,
    meets_reference_bar,
    parse_judge_response,
    plateaued,
    score_distribution,
    select_evidence,
    select_low_items,
    split_cmd,
)

_ROOT = Path(__file__).resolve().parents[1]
_FIX = Path(__file__).resolve().parent / "fixtures"
_DATA = _ROOT / "data"


def _scores(v: int) -> dict[str, int]:
    return {ax: v for ax in AXES}


def _judge_json(v: int, critique: str = "flat") -> str:
    return json.dumps({"scores": _scores(v), "critique": critique})


def _dist(v: float) -> dict:
    return {
        "n": 1,
        "axis_means": {ax: v for ax in AXES},
        "overall_mean": v,
        "overall_median": v,
        "overall_min": v,
    }


_PROP = {
    "property_id": "CHK-T-01",
    "text": "Slashing comparisons must use exact uint64 fields",
    "assertion": "forall f in slashing_fields: exact_uint64(f)",
    "type": "invariant",
    "severity": "HIGH",
    "covers": "process_slashings",
    "reachability": {
        "classification": "external-reachable",
        "entry_points": ["CallbackHandler"],
        "attacker_controlled": True,
        "bug_bounty_scope": "in-scope",
    },
    "bug_bounty_eligible": True,
    "exploitability": "external-attack",
    "lean_status": "descends-from-proved",
    "label": "beacon-chain:slashing",
}


def _prop(pid: str, text: str = "check something concrete", label: str = "beacon-chain:slashing") -> dict:
    p = dict(_PROP)
    p["property_id"] = pid
    p["text"] = text
    p["label"] = label
    return p


# ------------------------------------------------------------ prompt hygiene

def test_judge_prompt_is_blind_and_axis_complete():
    item = {"id": "CHK-X-01", "check": "the check", "detail": "the assertion"}
    prompt = build_judge_prompt(item)
    for ax in AXES:
        assert ax in prompt
    assert "the check" in prompt and "the assertion" in prompt
    # blind: no item id, no corpus identity, no dataset mention -> the verdict
    # cannot reward content matching or source recognition (eval != recall)
    assert "CHK-X-01" not in prompt
    for leak in ("solodit", "ethereum_vulns", "ethereum-vuln-dataset", "recall", "01e"):
        assert leak not in prompt.lower(), leak


def test_reference_and_generated_items_share_one_prompt_shape():
    sol = checklist_items_from_solodit(_DATA / "solodit_checklist.csv")[0]
    gen = {"id": "CHK-A", "check": "c", "detail": "d"}
    p1, p2 = build_judge_prompt(sol), build_judge_prompt(gen)
    # identical framing apart from the item content itself
    assert p1.split("Item to score:")[0] == p2.split("Item to score:")[0]


def test_01e_items_expose_only_the_checklist_surface():
    doc = {"properties": [dict(_PROP, x_dataset_evidence="SECRET-EVIDENCE")]}
    items = checklist_items_from_01e(doc)
    assert items == [{
        "id": "CHK-T-01",
        "check": _PROP["text"],
        "detail": _PROP["assertion"],
    }]
    assert "SECRET-EVIDENCE" not in build_judge_prompt(items[0])


def test_01e_id_prefix_filter():
    doc = {"properties": [_prop("CHK-A-01"), _prop("PROP-lean-1")]}
    assert [i["id"] for i in checklist_items_from_01e(doc, "CHK-")] == ["CHK-A-01"]
    assert len(checklist_items_from_01e(doc)) == 2


# ------------------------------------------------------------------ parsing

def test_parse_judge_response_strict_json():
    parsed = parse_judge_response(_judge_json(4, "ok"))
    assert parsed["scores"] == _scores(4)
    assert parsed["critique"] == "ok"


def test_parse_judge_response_json_embedded_in_prose():
    parsed = parse_judge_response("Sure! Here is my score:\n" + _judge_json(3) + "\nHope this helps.")
    assert parsed["scores"]["specificity"] == 3


@pytest.mark.parametrize("bad", [
    "no json at all",
    json.dumps({"scores": {ax: 4 for ax in AXES if ax != "granularity"}, "critique": "x"}),
    json.dumps({"scores": dict(_scores(4), specificity=0), "critique": "x"}),
    json.dumps({"scores": dict(_scores(4), specificity=6), "critique": "x"}),
    json.dumps({"scores": dict(_scores(4), specificity=True), "critique": "x"}),
    json.dumps({"scores": dict(_scores(4), specificity=4.5), "critique": "x"}),
    json.dumps({"scores": _scores(4), "critique": "  "}),
    json.dumps({"scores": _scores(4)}),
])
def test_parse_judge_response_rejects(bad):
    with pytest.raises(JudgeError):
        parse_judge_response(bad)


def test_judge_item_retries_then_fails_honestly():
    calls = []

    def flaky(prompt):
        calls.append(prompt)
        return "garbage" if len(calls) == 1 else _judge_json(5)

    s = judge_item({"id": "a", "check": "c", "detail": "d"}, flaky, retries=1)
    assert s["overall"] == 5.0 and len(calls) == 2

    with pytest.raises(JudgeError, match="always-bad"):
        judge_item({"id": "always-bad", "check": "c", "detail": "d"},
                   lambda p: "garbage", retries=1)


def test_judge_item_retries_transient_adapter_failures_too():
    """A real adapter (e.g. `claude -p`) can exit non-zero intermittently
    mid-run; that must be retried like a bad response, not kill the run."""
    calls = []

    def flaky_adapter(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            raise JudgeError("llm command failed (rc=1)")
        return _judge_json(4)

    s = judge_item({"id": "a", "check": "c", "detail": "d"}, flaky_adapter,
                   retries=1, retry_wait=0.0)
    assert s["overall"] == 4.0 and len(calls) == 2


def test_judge_items_empty_is_an_error():
    with pytest.raises(JudgeError):
        judge_items([], lambda p: _judge_json(4))


# ------------------------------------------------- distribution + bar verdict

def test_score_distribution_math():
    scored = [
        {"id": "a", "scores": _scores(3), "overall": 3.0, "critique": "x"},
        {"id": "b", "scores": _scores(5), "overall": 5.0, "critique": "x"},
    ]
    d = score_distribution(scored)
    assert d["n"] == 2
    assert d["overall_mean"] == 4.0
    assert d["overall_median"] == 4.0
    assert d["overall_min"] == 3.0
    assert d["axis_means"] == {ax: 4.0 for ax in AXES}


def test_meets_reference_bar_equal_passes():
    ok, gaps = meets_reference_bar(_dist(4.0), _dist(4.0))
    assert ok and gaps == []


def test_meets_reference_bar_overall_below_fails():
    ok, gaps = meets_reference_bar(_dist(3.9), _dist(4.0))
    assert not ok and any("overall_mean" in g for g in gaps)


def test_meets_reference_bar_axis_tolerance():
    ours = _dist(4.2)
    ours["axis_means"] = dict(ours["axis_means"], generality=3.8)
    ok, _ = meets_reference_bar(ours, _dist(4.0), axis_tolerance=0.25)
    assert ok  # 3.8 >= 4.0 - 0.25
    ours["axis_means"] = dict(ours["axis_means"], generality=3.7)
    ok, gaps = meets_reference_bar(ours, _dist(4.0), axis_tolerance=0.25)
    assert not ok and any("generality" in g for g in gaps)


def test_one_pumped_axis_cannot_buy_the_verdict():
    ours = _dist(4.5)  # overall above the bar...
    ours["axis_means"] = dict(_dist(4.5)["axis_means"], actionability=3.0)
    ok, gaps = meets_reference_bar(ours, _dist(4.0))
    assert not ok and any("actionability" in g for g in gaps)


def test_plateaued():
    assert not plateaued([4.0])                       # too short to claim 頭打ち
    assert not plateaued([4.0, 4.0])
    assert plateaued([4.0, 4.0, 4.0])
    assert plateaued([3.0, 4.0, 4.0, 4.04])           # window is the LAST 3
    assert not plateaued([4.0, 4.0, 4.2])             # still climbing
    assert not plateaued([3.0, 3.5, 4.0])
    assert plateaued([4.2, 4.0, 4.1])                 # dip-and-recover is flat


# ------------------------------------------------------------------- improve

def test_select_low_items():
    ref = _dist(4.0)
    a = {"id": "a", "scores": _scores(5), "overall": 5.0, "critique": "x"}
    b = {"id": "b", "scores": _scores(4), "overall": 4.0, "critique": "x"}       # at bar, no low axis
    c = {"id": "c", "scores": dict(_scores(5), generality=3), "overall": 4.6, "critique": "x"}
    d = {"id": "d", "scores": _scores(4), "overall": 3.9, "critique": "x"}
    low = select_low_items([a, b, c, d], ref, low_axis=3)
    assert [s["id"] for s in low] == ["c", "d"]


def test_select_evidence_label_match_then_fallback():
    vulns = [
        {"id": "V3", "severity": "High", "label": "beacon-chain:slashing",
         "root_cause": "integer_overflow_underflow", "attack_path": "malicious_block", "title": "t3"},
        {"id": "V1", "severity": "Critical", "label": "beacon-chain:slashing",
         "root_cause": "type_confusion", "attack_path": "malicious_block", "title": "t1"},
        {"id": "V2", "severity": "Critical", "label": "beacon-chain:justification-and-finality",
         "root_cause": "consensus_divergence", "attack_path": "crafted_state", "title": "t2"},
        {"id": "V4", "severity": "Low", "label": "beacon-chain:slashing",
         "root_cause": "x", "attack_path": "y", "title": "t4"},
    ]
    ev = select_evidence("beacon-chain:slashing", vulns, n=2)
    assert [e["id"] for e in ev] == ["V1", "V3"]      # severity then id, capped
    # label with no rows: falls back to Critical/High rows of any label
    ev = select_evidence("fork-choice", vulns, n=3)
    assert [e["id"] for e in ev] == ["V1", "V2", "V3"]
    # class-level fields only; concrete-incident fields (title/attack_path) are
    # deliberately dropped so the improve prompt cannot read as offensive (#143)
    assert set(ev[0]) == {"id", "severity", "label", "root_cause"}


def test_evidence_selection_is_deterministic_on_real_data():
    from speca_lean4.judge import load_vulns
    vulns = load_vulns(_DATA / "ethereum_vulns.csv")
    assert select_evidence("beacon-chain:slashing", vulns) == \
        select_evidence("beacon-chain:slashing", vulns)


def test_improve_prompt_carries_item_critique_and_evidence():
    scored = {"id": "CHK-T-01", "scores": dict(_scores(4), specificity=2),
              "overall": 3.6, "critique": "too abstract"}
    ev = [{"id": "V1", "severity": "Critical", "title": "u64 as float", "label": "l",
           "root_cause": "integer_overflow_underflow", "attack_path": "malicious_block"}]
    prompt = build_improve_prompt(_PROP, scored, ev)
    assert _PROP["text"] in prompt and _PROP["assertion"] in prompt   # (a) the item
    assert "too abstract" in prompt                                   # (b) the critique
    # (c) dataset rows are present as failure CLASS (id + severity + root_cause),
    # NOT as concrete incident: the exploit title and attack_path must NOT leak
    # into the prompt (the cyber-safeguard trigger fixed in #143).
    assert "V1" in prompt and "integer_overflow_underflow" in prompt
    assert "u64 as float" not in prompt and "malicious_block" not in prompt
    assert "NEVER name a specific client" in prompt


def test_apply_improvement_accepts_and_keeps_immutables():
    new, reason = apply_improvement(_PROP, json.dumps({
        "text": "Exact uint64 comparison on every slashing field from decode to compare",
        "assertion": "forall f: width(f)==u64 and not lossy(f)",
        "lean_status": "proved",          # attempted upgrade must be ignored
        "severity": "CRITICAL",
    }))
    assert new is not None
    assert reason.startswith("accepted")
    assert "ignored non-mutable keys" in reason
    assert new["lean_status"] == "descends-from-proved"   # untouched
    assert new["severity"] == "HIGH"                      # untouched
    assert new["property_id"] == _PROP["property_id"]
    assert new["text"].startswith("Exact uint64")


@pytest.mark.parametrize("resp,frag", [
    ("not json", "rejected"),
    (json.dumps({"other": "x"}), "no usable mutable field"),
    (json.dumps({"text": "  "}), "no usable mutable field"),
    (json.dumps({"text": "Reject the Lighthouse-style cursor reuse"}), "generality lint"),
    (json.dumps({"assertion": "as prysm does"}), "generality lint"),
])
def test_apply_improvement_rejections(resp, frag):
    new, reason = apply_improvement(_PROP, resp)
    assert new is None and frag in reason


# ---------------------------------------------------------------------- loop

def test_loop_converges_only_when_bar_met_AND_plateaued():
    """Bar is met from round 1, but the loop must still run until the last 3
    rounds are flat — bar alone never stops it."""
    ref = _dist(4.0)

    def judge_fn(prompt):
        # stateless: a sharpened item scores 5, an unsharpened one 3
        check = prompt.split("CHECK: ")[1].splitlines()[0]
        return _judge_json(5 if check.startswith("sharper text") else 3)

    def improve_fn(prompt):
        orig = prompt.split("TEXT: ")[1].splitlines()[0]
        return json.dumps({"text": f"sharper text: {orig}",
                           "assertion": "width(f)==u64"})

    props = [_prop("CHK-A-01", "text a"), _prop("CHK-B-01", "text b")]
    res = improve_loop(props, ref, [], judge_fn, improve_fn, max_rounds=6)
    assert res["converged"] is True
    assert res["stop_reason"] == "reference_bar_met_and_plateaued"
    # round0 3.0 -> improved to 5.0, then frozen until the 3-round window is flat
    assert res["history_overall_mean"] == [3.0, 5.0, 5.0, 5.0]
    assert [r["round"] for r in res["rounds"]] == [0, 1, 2, 3]
    # bar was met from round 1 on, yet the loop kept going to round 3
    assert res["rounds"][1]["meets_reference_bar"] is True
    # improved text landed in the final properties
    assert all(p["text"].startswith("sharper text") for p in res["properties"])


def test_loop_does_not_stop_on_plateau_below_bar():
    """Plateaued-but-below-bar must run to max_rounds and end unconverged —
    the honest outcome, never dressed up."""
    ref = _dist(4.5)
    res = improve_loop(
        [_prop("CHK-A-01")], ref, [],
        judge_fn=lambda p: _judge_json(3),
        improve_fn=lambda p: json.dumps({"text": "still weak but different"}),
        max_rounds=4,
    )
    assert res["converged"] is False
    assert res["stop_reason"] == "max_rounds_reached_without_convergence"
    assert res["history_overall_mean"] == [3.0] * 5
    assert len(res["rounds"]) == 5
    assert all(not r["meets_reference_bar"] for r in res["rounds"])


def test_loop_judges_blind_and_improves_with_evidence():
    """eval != recall, structurally: judge prompts never contain dataset rows;
    improve prompts do."""
    judge_prompts, improve_prompts = [], []
    vulns = [{"id": "VULN-X1", "severity": "Critical", "label": "beacon-chain:slashing",
              "root_cause": "integer_overflow_underflow",
              "attack_path": "malicious_block", "title": "evidence row"}]

    def judge_fn(p):
        judge_prompts.append(p)
        return _judge_json(3)

    def improve_fn(p):
        improve_prompts.append(p)
        return json.dumps({"text": "sharper checklist text"})

    improve_loop([_prop("CHK-A-01")], _dist(4.5), vulns, judge_fn, improve_fn,
                 max_rounds=2)
    assert improve_prompts, "no improve round ran"
    assert all("VULN-X1" not in p for p in judge_prompts)
    assert all("VULN-X1" in p for p in improve_prompts)


def test_loop_rejected_improvement_keeps_original_and_is_logged():
    res = improve_loop(
        [_prop("CHK-A-01", "original text")], _dist(4.5), [],
        judge_fn=lambda p: _judge_json(3),
        improve_fn=lambda p: json.dumps({"text": "do it like Lighthouse does"}),
        max_rounds=2,
    )
    assert res["properties"][0]["text"] == "original text"
    results = [i["result"] for r in res["rounds"] for i in r["improvements"]]
    assert results and all("generality lint" in x for x in results)


def test_loop_logs_score_progression_per_round():
    res = improve_loop(
        [_prop("CHK-A-01")], _dist(4.5), [],
        judge_fn=lambda p: _judge_json(4),
        improve_fn=lambda p: json.dumps({"text": "x" * 30}),
        max_rounds=3,
    )
    assert len(res["history_overall_mean"]) == len(res["rounds"])
    for r in res["rounds"]:
        assert set(r) >= {"round", "distribution", "meets_reference_bar",
                          "bar_gaps", "n_improve_candidates", "improvements", "items"}
        assert r["distribution"]["overall_mean"] == res["history_overall_mean"][r["round"]]


def test_loop_duplicate_property_id_is_an_error():
    with pytest.raises(JudgeError):
        improve_loop([_prop("CHK-A-01"), _prop("CHK-A-01")], _dist(4.0), [],
                     lambda p: _judge_json(4), lambda p: "{}")


# ------------------------------------------------- vendored solodit reference

def test_solodit_vendored_provenance_matches_meta():
    """The vendored bytes must still be the pinned speca blob: recompute the
    git blob sha from the file so silent edits/CRLF churn cannot hide."""
    meta = json.loads((_DATA / "solodit_checklist.meta.json").read_text(encoding="utf-8"))
    raw = (_DATA / "solodit_checklist.csv").read_bytes()
    blob_sha = hashlib.sha1(b"blob %d\x00" % len(raw) + raw).hexdigest()
    assert blob_sha == meta["source_blob_sha"]
    assert b"\r" not in raw, "CRLF crept into the vendored reference"
    items = checklist_items_from_solodit(_DATA / "solodit_checklist.csv")
    assert len(items) == meta["n_rows"] == 52
    assert all(i["id"] and i["check"] for i in items)


def test_solodit_loader_shape():
    items = checklist_items_from_solodit(_DATA / "solodit_checklist.csv")
    assert items[0]["id"] == "SOL-AM-DOSA-1"
    assert set(items[0]) == {"id", "check", "detail"}


# ---------------------------------------------------------------- CLI wiring

def _mock_cmd() -> str:
    return f'"{sys.executable}" "{_FIX / "mock_llm.py"}"'


def test_subprocess_llm_timeout_is_a_retryable_judge_error():
    from speca_lean4.judge import subprocess_llm

    fn = subprocess_llm([sys.executable, "-c", "import time; time.sleep(30)"],
                        timeout=1)
    with pytest.raises(JudgeError, match="timeout"):
        fn("prompt")


def test_split_cmd():
    parts = split_cmd(_mock_cmd())
    assert parts[0] == sys.executable
    assert parts[1] == str(_FIX / "mock_llm.py")
    assert split_cmd("claude -p --model haiku") == ["claude", "-p", "--model", "haiku"]


@pytest.fixture
def chk_01e(tmp_path) -> Path:
    from speca_lean4.cli import main

    out = tmp_path / "01e_lean.json"
    rc = main([
        "emit-01e",
        "--scope", str(_FIX / "bug_bounty_scope.sample.json"),
        "--health-json", str(_FIX / "theorem_health.sample.json"),
        "--out", str(out),
    ])
    assert rc == 0
    return out


def test_cli_judge_end_to_end_with_mock(chk_01e, tmp_path, capsys):
    from speca_lean4.cli import main

    out = tmp_path / "judge_report.json"
    rc = main([
        "judge", "--ours", str(chk_01e), "--id-prefix", "CHK-",
        "--llm-cmd", _mock_cmd(), "--out", str(out),
    ])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ours"]["n"] == 15                  # the CHK-15 checklist
    assert report["reference"]["n"] == 52             # the solodit bar
    assert len(report["items"]) == 15
    assert len(report["reference_items"]) == 52
    assert isinstance(report["meets_reference_bar"], bool)
    for s in report["items"]:
        assert set(s["scores"]) == set(AXES)
    assert "reference bar" in capsys.readouterr().out


def test_cli_judge_without_llm_cmd_fails_with_guidance(chk_01e, capsys):
    from speca_lean4.cli import main

    rc = main(["judge", "--ours", str(chk_01e)])
    assert rc == 2
    assert "API key" in capsys.readouterr().err


def test_cli_improve_end_to_end_with_mock(chk_01e, tmp_path):
    from speca_lean4.cli import main

    # reuse the reference scores via --ref-report to skip re-judging solodit
    report = tmp_path / "judge_report.json"
    assert main(["judge", "--ours", str(chk_01e), "--id-prefix", "CHK-",
                 "--llm-cmd", _mock_cmd(), "--out", str(report)]) == 0
    out_dir = tmp_path / "improve_run"
    rc = main([
        "improve", "--ours", str(chk_01e), "--id-prefix", "CHK-",
        "--llm-cmd", _mock_cmd(), "--ref-report", str(report),
        "--out-dir", str(out_dir), "--max-rounds", "3",
    ])
    assert rc == 0
    log = json.loads((out_dir / "score_log.json").read_text(encoding="utf-8"))
    assert log["rounds"] and log["history_overall_mean"]
    assert isinstance(log["converged"], bool)
    assert log["stop_reason"]
    assert log["reference"]["n"] == 52
    improved = json.loads((out_dir / "improved_01e.json").read_text(encoding="utf-8"))
    props = improved["properties"]
    assert len(props) == 15
    assert "x_improve_note" in improved
    # immutables survived the loop; only text/assertion may differ
    orig = {p["property_id"]: p for p in
            json.loads(chk_01e.read_text(encoding="utf-8"))["properties"]
            if p["property_id"].startswith("CHK-")}
    for p in props:
        o = orig[p["property_id"]]
        for k in o:
            if k not in ("text", "assertion"):
                assert p[k] == o[k], (p["property_id"], k)


def test_cli_improve_strict_flags_nonconvergence(chk_01e, tmp_path, capsys):
    from speca_lean4.cli import main

    report = tmp_path / "judge_report.json"
    assert main(["judge", "--ours", str(chk_01e), "--id-prefix", "CHK-",
                 "--llm-cmd", _mock_cmd(), "--out", str(report)]) == 0
    out_dir = tmp_path / "improve_run"
    rc = main([
        "improve", "--ours", str(chk_01e), "--id-prefix", "CHK-",
        "--llm-cmd", _mock_cmd(), "--ref-report", str(report),
        "--out-dir", str(out_dir), "--max-rounds", "1", "--strict",
    ])
    # one round can never satisfy the 3-round plateau half of convergence
    assert rc == 1
    assert "did not converge" in capsys.readouterr().err
