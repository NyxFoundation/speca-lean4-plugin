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
#   FIDELITY_CMD LLM adapter for closure-aware fidelity (default: claude -p)
#   OPUS_MODEL   set to 1 to use Claude Cloud Opus for judge/improve/fidelity
#   HERMES_BIN   path to the hermes binary when it is not on PATH
set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="${1:-improve_run_ethtotal}"
MAX_ROUNDS="${2:-3}"
CANONICAL_01E="${CANONICAL_01E:-$OUT_DIR/01e_PARTIAL_ethtotal.json}"
WORK_DIR="${WORK_DIR:-$OUT_DIR/.work}"
REPORT_DIR="${REPORT_DIR:-$OUT_DIR/quality}"
JUDGE_CMD="${JUDGE_CMD:-bash tools/llm-hermes.sh}"
IMPROVE_CMD="${IMPROVE_CMD:-claude -p}"
FIDELITY_CMD="${FIDELITY_CMD:-claude -p}"
if [[ "${OPUS_MODEL:-0}" == "1" ]]; then
  JUDGE_CMD="${JUDGE_CMD_OPUS:-claude -p --model opus}"
  IMPROVE_CMD="${IMPROVE_CMD_OPUS:-claude -p --model opus}"
  FIDELITY_CMD="${FIDELITY_CMD_OPUS:-claude -p --model opus}"
fi
VULNS_CSV="${VULNS_CSV:-data/ethtotal_vulns_high.csv}"
MAP="${MAP:-theorem_map_ethtotal.json}"
SCOPE="${SCOPE:-tests/fixtures/bug_bounty_scope.ethtotal.sample.json}"
HEALTH="${HEALTH:-lean-ethtotal/health.json}"
PACKETS="${PACKETS:-data/ethtotal_audit_packets.json}"
ALL_PROPERTIES="${ALL_PROPERTIES:-0}"
REF_REPORT="${REF_REPORT:-$REPORT_DIR/reference_judge.json}"
JUDGE_WORKERS="${JUDGE_WORKERS:-8}"
IMPROVE_WORKERS="${IMPROVE_WORKERS:-1}"
LOW_AXIS="${LOW_AXIS:-5}"

# The reference corpus is fixed for this rubric.  Reuse the checked-in
# same-rubric report when available; otherwise judge the 52 reference rows
# once as a fallback.  This keeps Cloud Opus capacity focused on the 390
# target properties.
JUDGE_REF_ARGS=()
if [[ -f "$REF_REPORT" ]]; then
  JUDGE_REF_ARGS=(--ref-report "$REF_REPORT")
fi

mkdir -p "$OUT_DIR" "$WORK_DIR" "$REPORT_DIR"
if [[ ! -f "$PACKETS" || "${REGENERATE_PACKETS:-0}" == "1" ]]; then
  echo "[0/6] materialize packets for existing theorem roots -> $PACKETS"
  uv run python tools/materialize-audit-packets.py --map "$MAP" \
      --health-json "$HEALTH" --out "$PACKETS"
fi
echo "[1/6] rebuild theorem map with all proof-aware packets"
uv run python tools/ethtotal-build-map.py --health "$HEALTH" \
    --generated data/ethtotal_generated_properties.json --packets "$PACKETS" \
    --out "$MAP"
echo "[2/6] emit full 01e (map=$MAP)"
uv run speca-lean4 emit-01e --map "$MAP" --scope "$SCOPE" --health-json "$HEALTH" \
    --out "$WORK_DIR/chk_01e.json"

# The full 01e contains proved theorem properties as well as the generated
# CHK packet.  Fidelity and quality review are intentionally scoped to the
# packet, whose closure metadata is the semantic anchor for self-improvement.
echo "[2b/6] select audit packet scope -> $WORK_DIR/packet_01e.json"
if [[ "$ALL_PROPERTIES" == "1" ]]; then
  cp "$WORK_DIR/chk_01e.json" "$WORK_DIR/packet_01e.json"
else
  jq '.properties |= map(select(.property_id | startswith("CHK-")))' \
      "$WORK_DIR/chk_01e.json" > "$WORK_DIR/packet_01e.json"
fi

echo "[3/6] closure-aware fidelity review -> $WORK_DIR/fidelity_01e.json"
if [[ "$ALL_PROPERTIES" == "1" ]]; then
  uv run python tools/validate-packet-fidelity.py --in "$WORK_DIR/packet_01e.json" \
      --out "$WORK_DIR/fidelity_01e.json" --health-json "$HEALTH" --map "$MAP"
else
  uv run python tools/refine-property-fidelity.py --in "$WORK_DIR/packet_01e.json" \
      --out "$WORK_DIR/fidelity_01e.json" --health-json "$HEALTH" \
      --llm-cmd "$FIDELITY_CMD" --workers 4 --timeout 300
fi

echo "[4/6] cross-family judge (self-preference check) -> $REPORT_DIR/cloud_opus_judge.json"
if [[ -s "$WORK_DIR/judge.json" && "${REJUDGE:-0}" != "1" ]]; then
  echo "reusing existing judge report (set REJUDGE=1 to recompute)"
else
  uv run speca-lean4 judge --ours "$WORK_DIR/fidelity_01e.json" \
      --llm-cmd "$JUDGE_CMD" --llm-timeout 300 "${JUDGE_REF_ARGS[@]}" \
      --workers "$JUDGE_WORKERS" \
      --out "$WORK_DIR/judge.json"
fi

echo "[5/6] few-shot style improve loop (all 01e properties; judge=$JUDGE_CMD, improve=$IMPROVE_CMD, teaching=$VULNS_CSV)"
# The improve loop uses matching label/root-cause rows to select defensive
# weak->strong style cards. Cards can sharpen text/assertion only; the
# closure-backed audit_packet is immutable in this stage.
uv run speca-lean4 improve --ours "$WORK_DIR/fidelity_01e.json" \
    --ref-report "$WORK_DIR/judge.json" \
    --initial-report "$WORK_DIR/judge.json" \
    --llm-cmd "$JUDGE_CMD" --improve-cmd "$IMPROVE_CMD" \
    --vulns-csv "$VULNS_CSV" --out-dir "$WORK_DIR" \
    --max-rounds "$MAX_ROUNDS" --llm-timeout 300 --workers "$IMPROVE_WORKERS" \
    --low-axis "$LOW_AXIS"

echo "[6/6] post-improvement fidelity review -> $WORK_DIR/final_fidelity_01e.json"
if [[ "$ALL_PROPERTIES" == "1" ]]; then
  uv run python tools/validate-packet-fidelity.py --in "$WORK_DIR/improved_01e.json" \
      --out "$WORK_DIR/final_fidelity_01e.json" --health-json "$HEALTH" --map "$MAP"
else
  uv run python tools/refine-property-fidelity.py --in "$WORK_DIR/improved_01e.json" \
      --out "$WORK_DIR/final_fidelity_01e.json" --health-json "$HEALTH" \
      --llm-cmd "$FIDELITY_CMD" --workers 4 --timeout 300
fi

cp "$WORK_DIR/final_fidelity_01e.json" "$CANONICAL_01E"
cp "$WORK_DIR/judge.json" "$REPORT_DIR/cloud_opus_judge.json"
cp "$WORK_DIR/score_log.json" "$REPORT_DIR/cloud_opus_score_log.json"
echo "done. canonical 01e: $CANONICAL_01E ; reports: $REPORT_DIR"
echo "to persist:"
echo "  uv run python tools/apply-fidelity.py $CANONICAL_01E --map data/ethtotal_generated_properties.json"
echo "  uv run python tools/apply-improved.py $CANONICAL_01E --map data/ethtotal_generated_properties.json"
echo "  python3 tools/ethtotal-build-map.py && git diff data/ethtotal_generated_properties.json"
