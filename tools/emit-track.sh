#!/usr/bin/env bash
# Emit a completed 01e checklist into outputs/<date>-<title>/ as the audit
# source (speca#88 a/b/c-3). Each M2 audit track produces its own 01e that
# becomes the property source for the 11-client SPECA run in speca-audits-2026.
#
# Subfolders are named <YYYYMMDD>-<title> (e.g. 20260723-gasper), not by track
# letter, so a run is identifiable at a glance. Title examples: gasper (the
# gasper-lean4 checklist), an EL-spec title, a vuln-dataset title.
#
# Writes a single-file 01e (01e_PARTIAL_<slug>.json — speca 02c glob convention)
# plus a manifest recording the
# plugin commit / theorem_map / checklist ids, so the audit source is traceable.
#
# Usage: tools/emit-track.sh <title> [DATE] [MAP] [SCOPE] [HEALTH]
#   DATE defaults to today (YYYY-MM-DD).
set -euo pipefail
cd "$(dirname "$0")/.."

TITLE="${1:?usage: emit-track.sh <title> [DATE] [MAP] [SCOPE] [HEALTH]  e.g. emit-track.sh gasper}"
DATE="${2:-$(date +%Y%m%d)}"
MAP="${3:-theorem_map.json}"
SCOPE="${4:-tests/fixtures/bug_bounty_scope.sample.json}"
HEALTH="${5:-tests/fixtures/theorem_health.sample.json}"
# The audit source must be the CONCRETE, self-improved checklist only (CHK-*),
# NOT the abstract theorem -me* must-establish decompositions — mixing them was
# the false-positive source (speca#88). Set EMIT_FULL=1 to include the abstract
# proof-obligation properties (research use; expect more FPs).
CONCRETE_FLAG="--concrete-only"
[ "${EMIT_FULL:-}" = "1" ] && CONCRETE_FLAG=""

# sanitize title into a folder-safe slug
SLUG="$(printf '%s' "$TITLE" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')"
OUT="outputs/${DATE}-${SLUG}"
mkdir -p "$OUT"

echo "[emit-track] title=$TITLE date=$DATE -> $OUT"
uv run speca-lean4 emit-01e $CONCRETE_FLAG --map "$MAP" --scope "$SCOPE" --health-json "$HEALTH" \
    --out "$OUT/01e_PARTIAL_${SLUG}.json"

COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
uv run python - "$TITLE" "$DATE" "$OUT" "$SLUG" "$MAP" "$COMMIT" <<'PY'
import json, sys
title, date, out, slug, mapf, commit = sys.argv[1:7]
fname = f"01e_PARTIAL_{slug}.json"
doc = json.load(open(f"{out}/{fname}", encoding="utf-8"))
props = doc.get("properties", [])
chk = [p for p in props if str(p.get("property_id", "")).startswith("CHK-")]
from collections import Counter
manifest = {
    "title": title,
    "date": date,
    "folder": out,
    "file": fname,
    "plugin_repo": "NyxFoundation/speca-lean4-plugin",
    "plugin_commit": commit,
    "theorem_map": mapf,
    "property_count": len(props),
    "checklist_count": len(chk),
    "checklist_severity": dict(Counter(p.get("severity") for p in chk)),
    "checklist_ids": [p["property_id"] for p in chk],
    "note": "Audit source for speca-audits-2026 (a/b/c-3). Validated against speca orchestrator.schemas.Phase01ePartial. File follows speca's 01e_PARTIAL_*.json convention so Phase 02c globs it. Copy %s/%s into the audit repo's source location; run 02c-04 per client against it." % (out, fname),
}
json.dump(manifest, open(f"{out}/manifest.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"  {len(props)} properties ({len(chk)} checklist, severity {manifest['checklist_severity']}) -> {out}/{fname}")
PY
echo "[emit-track] done -> $OUT/"
