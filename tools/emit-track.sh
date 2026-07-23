#!/usr/bin/env bash
# Emit a track's completed 01e into outputs/<track>/ as the audit source
# (speca#88 a/b/c-3). Each M2 track produces its own 01e checklist that becomes
# the property source for the 11-client SPECA audit run in speca-audits-2026:
#
#   a = gasper (this repo's theorem_map — the 20 CHK-* checklist)
#   b = EL spec        (plugs in once b-1 formalizes an EL theorem set)
#   c = vuln-dataset   (plugs in once c-1 formalizes a critical/high theorem set)
#
# Writes a stable single-file 01e (outputs/<track>/01e.json) plus a manifest
# recording the theorem_map / plugin commit it came from, so the audit source is
# traceable. b/c pass their own --map/--scope/--health once they exist.
#
# Usage: tools/emit-track.sh <a|b|c> [MAP] [SCOPE] [HEALTH]
set -euo pipefail
cd "$(dirname "$0")/.."

TRACK="${1:?usage: emit-track.sh <a|b|c> [MAP] [SCOPE] [HEALTH]}"
case "$TRACK" in a|b|c) ;; *) echo "track must be a, b, or c" >&2; exit 2;; esac
MAP="${2:-theorem_map.json}"
SCOPE="${3:-tests/fixtures/bug_bounty_scope.sample.json}"
HEALTH="${4:-tests/fixtures/theorem_health.sample.json}"

OUT="outputs/$TRACK"
mkdir -p "$OUT"

echo "[emit-track $TRACK] map=$MAP scope=$SCOPE"
uv run speca-lean4 emit-01e --map "$MAP" --scope "$SCOPE" --health-json "$HEALTH" \
    --out "$OUT/01e.json"

COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
uv run python - "$TRACK" "$OUT" "$MAP" "$COMMIT" <<'PY'
import json, sys
track, out, mapf, commit = sys.argv[1:5]
doc = json.load(open(f"{out}/01e.json", encoding="utf-8"))
props = doc.get("properties", [])
chk = [p for p in props if str(p.get("property_id", "")).startswith("CHK-")]
manifest = {
    "track": track,
    "plugin_repo": "NyxFoundation/speca-lean4-plugin",
    "plugin_commit": commit,
    "theorem_map": mapf,
    "property_count": len(props),
    "checklist_count": len(chk),
    "checklist_ids": [p["property_id"] for p in chk],
    "note": "Audit source for speca-audits-2026 (a/b/c-3). Copy outputs/%s/01e.json into the audit repo's source location; run 02c-04 per client against it." % track,
}
json.dump(manifest, open(f"{out}/manifest.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"  {len(props)} properties ({len(chk)} checklist) -> {out}/01e.json + manifest.json")
PY
echo "[emit-track $TRACK] done -> $OUT/"
