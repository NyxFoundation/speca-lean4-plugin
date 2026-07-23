#!/usr/bin/env bash
# Reproducible stage-2 self-improvement run (speca#88 / #143).
#
# One command: emit the CHK checklist 01e, judge it against the solodit bar with
# a CROSS-FAMILY model (self-preference check), then run the improve loop that
# sharpens low-scoring items into concrete implementation checks using the
# ethereum-vuln-dataset critical/high failure classes as teaching material.
#
# The improved properties in <out>/improved_01e.json are a PROPOSAL. Apply them
# back into theorem_map.json with tools/apply-improved.py and commit, so the
# git history is the before/after record (see docs/improve-log.md).
#
# Usage:
#   tools/run-improve.sh [OUT_DIR] [MAX_ROUNDS]
# Env overrides:
#   JUDGE_CMD    LLM adapter for the judge     (default: cross-family Hermes)
#   IMPROVE_CMD  LLM adapter for the improver  (default: claude -p)
#   VULNS_CSV    teaching-material corpus       (default: critical/high slice)
set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="${1:-improve_run}"
MAX_ROUNDS="${2:-3}"
JUDGE_CMD="${JUDGE_CMD:-bash tools/llm-hermes.sh}"
IMPROVE_CMD="${IMPROVE_CMD:-claude -p}"
VULNS_CSV="${VULNS_CSV:-data/ethereum_vulns_high.csv}"
SCOPE="${SCOPE:-tests/fixtures/bug_bounty_scope.sample.json}"
HEALTH="${HEALTH:-tests/fixtures/theorem_health.sample.json}"

mkdir -p "$OUT_DIR"
echo "[1/3] emit CHK 01e"
uv run speca-lean4 emit-01e --scope "$SCOPE" --health-json "$HEALTH" \
    --out "$OUT_DIR/chk_01e.json"

echo "[2/3] cross-family judge (self-preference check) -> $OUT_DIR/judge.json"
uv run speca-lean4 judge --ours "$OUT_DIR/chk_01e.json" --id-prefix CHK- \
    --llm-cmd "$JUDGE_CMD" --llm-timeout 180 --out "$OUT_DIR/judge.json"

echo "[3/3] improve loop (judge=$JUDGE_CMD, improve=$IMPROVE_CMD, teaching=$VULNS_CSV)"
uv run speca-lean4 improve --ours "$OUT_DIR/chk_01e.json" --id-prefix CHK- \
    --ref-report "$OUT_DIR/judge.json" \
    --llm-cmd "$JUDGE_CMD" --improve-cmd "$IMPROVE_CMD" \
    --vulns-csv "$VULNS_CSV" --out-dir "$OUT_DIR" \
    --max-rounds "$MAX_ROUNDS" --llm-timeout 180

echo "done. proposal: $OUT_DIR/improved_01e.json ; scores: $OUT_DIR/score_log.json"
echo "to persist: uv run python tools/apply-improved.py $OUT_DIR/improved_01e.json && git commit theorem_map.json"
