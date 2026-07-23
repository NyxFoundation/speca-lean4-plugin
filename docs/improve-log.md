# Improve-loop run log (speca#88 / #143)

Each entry records one stage-2 self-improvement run: the models used, the
teaching corpus, the score progression, which CHK-* properties were sharpened,
and the **commit** that persisted the sharpened `text`/`assertion` into
`theorem_map.json`. Open that commit to see the exact before/after diff of the
property changes.

Run the loop with `tools/run-improve.sh`; persist with `tools/apply-improved.py`
(see `docs/judge-loop.md`).

<!-- newest first -->

## 2026-07-23 — run 1 (10 CHK sharpened)

- **judge**: kimi-k2.6 via Hermes (`custom:ollama-cloud`) — cross-family, doubles as the self-preference check
- **improve**: `claude -p` (speca#143 defensive class-only prompt)
- **teaching corpus**: `data/ethereum_vulns_high.csv` (176 critical/high classes)
- **self-preference check**: CHK-15 **4.05** vs solodit bar **2.98** under kimi (Claude judge gave 4.01 vs 2.80) — ranking preserved cross-family, so the bar-clearing is not Claude self-favouritism
- **score progression** (overall mean): 4.053 → 4.56 → 4.72 → 4.787 (3 rounds; granularity guard rejected the over-length rewrites, original kept)
- **sharpened (10)**: CHK-AS-01, CHK-AS-02, CHK-AS-03, CHK-QW-03, CHK-SL-04, CHK-JF-01, CHK-JF-02, CHK-JF-03, CHK-JF-04, CHK-LV-01
- **before/after diff**: [`f9de5b0`](https://github.com/NyxFoundation/speca-lean4-plugin/commit/f9de5b01d5b2960ec70e4947713065fe81d4ce08) (theorem_map.json)

Example: CHK-LV-01 "every network-reachable resource must have an explicit cap" → "for every network-fed buffer/queue/decompression sink/recursive call, check size+increment against the cap and reject **before** the append/recursion; flag any path where the check runs only after" — concrete ordering condition, general, no client named.
