#!/usr/bin/env bash
# Reproducible stage-2 self-improvement run for the EthTotal track.
#
# The eth-total-supply-safety counterpart of tools/run-improve.sh. Same loop,
# three different inputs:
#
#   map          theorem_map_ethtotal.json  (built by tools/ethtotal-build-map.py)
#   health       lean-ethtotal/health.json  (lake exe speca-export over ALL 3333 theorems)
#   teaching     data/ethtotal_vulns_high.csv — the ethereum-vuln-dataset
#                critical/high slice restricted to the value-bearing execution
#                surfaces (state-trie, transactions, evm, opcodes, gas,
#                precompiles, database, block-processing), so the sharpening
#                material is about the failure modes an accounting invariant
#                can actually be broken by. Teaching material only — never an
#                eval denominator (the #88 correction).
#
# The improved properties in <out>/improved_01e.json are a PROPOSAL. Persist
# them with tools/apply-improved.py into data/ethtotal_generated_properties.json
# (NOT into theorem_map_ethtotal.json, which is a build product) and rebuild the
# map, so the git diff of the generated-properties file is the before/after
# record.
#
# Usage:
#   tools/run-improve-ethtotal.sh [OUT_DIR] [MAX_ROUNDS]
# Env overrides:
#   JUDGE_CMD    LLM adapter for the judge     (default: cross-family Hermes)
#   IMPROVE_CMD  LLM adapter for the improver  (default: claude -p)
#   HERMES_BIN   path to the hermes binary when it is not on PATH
set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="${1:-improve_run_ethtotal}"
MAX_ROUNDS="${2:-3}"
JUDGE_CMD="${JUDGE_CMD:-bash tools/llm-hermes.sh}"
IMPROVE_CMD="${IMPROVE_CMD:-claude -p}"
VULNS_CSV="${VULNS_CSV:-data/ethtotal_vulns_high.csv}"
MAP="${MAP:-theorem_map_ethtotal.json}"
SCOPE="${SCOPE:-tests/fixtures/bug_bounty_scope.ethtotal.sample.json}"
HEALTH="${HEALTH:-lean-ethtotal/health.json}"

mkdir -p "$OUT_DIR"
echo "[1/3] emit CHK 01e (map=$MAP)"
uv run speca-lean4 emit-01e --map "$MAP" --scope "$SCOPE" --health-json "$HEALTH" \
    --out "$OUT_DIR/chk_01e.json"

echo "[2/3] cross-family judge (self-preference check) -> $OUT_DIR/judge.json"
uv run speca-lean4 judge --ours "$OUT_DIR/chk_01e.json" --id-prefix CHK- \
    --llm-cmd "$JUDGE_CMD" --llm-timeout 300 --out "$OUT_DIR/judge.json"

echo "[3/3] improve loop (judge=$JUDGE_CMD, improve=$IMPROVE_CMD, teaching=$VULNS_CSV)"
uv run speca-lean4 improve --ours "$OUT_DIR/chk_01e.json" --id-prefix CHK- \
    --ref-report "$OUT_DIR/judge.json" \
    --llm-cmd "$JUDGE_CMD" --improve-cmd "$IMPROVE_CMD" \
    --vulns-csv "$VULNS_CSV" --out-dir "$OUT_DIR" \
    --max-rounds "$MAX_ROUNDS" --llm-timeout 300

echo "done. proposal: $OUT_DIR/improved_01e.json ; scores: $OUT_DIR/score_log.json"
echo "to persist:"
echo "  uv run python tools/apply-improved.py $OUT_DIR/improved_01e.json --map data/ethtotal_generated_properties.json"
echo "  python3 tools/ethtotal-build-map.py && git diff data/ethtotal_generated_properties.json"
