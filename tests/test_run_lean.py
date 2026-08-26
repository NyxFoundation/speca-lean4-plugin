"""`_run_lean` contract tests (no Lean toolchain needed — `lake` is faked).

Regression for speca run 29749878252: a cold `lake exe` interleaves
toolchain/dependency/build noise into stdout before the exporter runs, so
health JSON must travel via `--output`, never via stdout, and every failure
mode must leave a diagnosable error (stdout/stderr tails included).
"""

from __future__ import annotations

import json
import subprocess

import pytest

from speca_lean4 import cli
from speca_lean4.cli import _run_lean

_MAP = {"properties": [{"theorem": "GasperBeaconChain.Foo.bar"}]}
_HEALTH = {"project": "GasperBeaconChain", "theorems": [
    {"name": "GasperBeaconChain.Foo.bar", "resolved": True, "lean_status": "proved"},
]}


def _fake_lake(*, rc=0, stdout="", stderr="", write_health=True, health_text=None):
    """Return a subprocess.run stand-in emulating `lake exe speca-export`."""

    def run(cmd, **kwargs):
        assert cmd[:2] == ["lake", "exe"]
        assert cmd[2] in ("speca-export", "speca-export-ethvuln")
        assert "--output" in cmd, "health must travel via --output, not stdout"
        out_path = cmd[cmd.index("--output") + 1]
        if write_health:
            text = json.dumps(_HEALTH) if health_text is None else health_text
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=stderr)

    return run


def test_run_lean_reads_output_file_despite_stdout_noise(monkeypatch):
    # The exact failure shape of speca run 29749878252: rc=0, build noise on
    # stdout — and the health JSON must still come through (via the file).
    noise = "info: downloading component 'lean'\nBuild completed successfully.\n"
    monkeypatch.setattr(cli.subprocess, "run", _fake_lake(stdout=noise))
    health = _run_lean(_MAP)
    assert health["theorems"][0]["lean_status"] == "proved"


def test_run_lean_nonzero_rc_raises_with_diagnostics(monkeypatch):
    monkeypatch.setattr(
        cli.subprocess, "run",
        _fake_lake(rc=1, stdout="partial build log", stderr="error: build failed",
                   write_health=False),
    )
    with pytest.raises(RuntimeError) as exc:
        _run_lean(_MAP)
    msg = str(exc.value)
    assert "rc=1" in msg
    assert "partial build log" in msg      # stdout tail preserved
    assert "error: build failed" in msg    # stderr tail preserved


def test_run_lean_missing_output_raises_with_diagnostics(monkeypatch):
    # rc=0 but no health file (e.g. exporter predates --output): must not
    # succeed silently and must keep the streams for diagnosis.
    monkeypatch.setattr(
        cli.subprocess, "run",
        _fake_lake(stdout="some lake chatter", write_health=False),
    )
    with pytest.raises(RuntimeError) as exc:
        _run_lean(_MAP)
    msg = str(exc.value)
    assert "wrote no" in msg
    assert "some lake chatter" in msg


def test_run_lean_invalid_json_raises_with_file_head(monkeypatch):
    monkeypatch.setattr(
        cli.subprocess, "run",
        _fake_lake(health_text="not json at all", stderr="warning: whatever"),
    )
    with pytest.raises(RuntimeError) as exc:
        _run_lean(_MAP)
    msg = str(exc.value)
    assert "not valid JSON" in msg
    assert "not json at all" in msg        # file head preserved


def test_run_lean_honors_map_lean_exe_and_src_roots(monkeypatch):
    """A second-target map of the same workspace names its own executable
    (theorem_map_ethvuln.json -> speca-export-ethvuln) and, optionally, extra
    --src-root dirs; the default stays the gasper `speca-export`."""
    seen: list[list[str]] = []

    def run(cmd, **kwargs):
        seen.append(list(cmd))
        with open(cmd[cmd.index("--output") + 1], "w", encoding="utf-8") as fh:
            fh.write(json.dumps(_HEALTH))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", run)
    _run_lean(_MAP)
    assert seen[-1][:3] == ["lake", "exe", "speca-export"]
    assert "--src-root" not in seen[-1]
    _run_lean({**_MAP, "lean_exe": "speca-export-ethvuln", "x_src_roots": ["."]})
    assert seen[-1][:3] == ["lake", "exe", "speca-export-ethvuln"]
    assert seen[-1][seen[-1].index("--src-root") + 1] == "."
