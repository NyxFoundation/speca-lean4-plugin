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

## 2026-07-23 — new-property generation (5 new critical/high proposals)

First run of `tools/generate-properties.py` (gen=`claude -p`, judge=kimi, floor 3.5):
paired proved gasper theorems with critical/high defect classes NOT covered by
CHK-15. 6 candidates, **5 kept**, 1 rejected by the length guard (text 279>260).

| id | theorem | defect class | judged |
|---|---|---|---|
| CHK-GEN-01 | k_safety' | consensus_divergence | 4.0 |
| CHK-GEN-02 | k_safety' | missing_input_validation | 3.8 |
| CHK-GEN-03 | justified_iff_bounded | missing_input_validation | 4.6 |
| CHK-GEN-04 | plausible_liveness_construct_extension | missing_input_validation | 4.8 |
| CHK-GEN-05 | k_safety' | race_condition | 4.2 |

These are **novel** critical/high checks the theorem implies against a real
failure class — not reproductions of a specific past bug (no client named,
general, concrete). Saved as a **proposal** in `data/generated_properties.json`;
they are NOT yet in `theorem_map.json` (adding them makes them live audit
drivers and requires updating the checklist-count/shard contract tests, so it
gates on human review).

### adopted 2026-07-23

The 5 generated proposals were **adopted into `theorem_map.json`** (vocabulary-
conformed, `anchor_map.json` defs rows added, checklist-count/shard contract
tests updated 15→20). The checklist SPECA uses is now **20 items** (15 improved
hand-authored + 5 generated). Emit: 74 properties (54 mechanical lowerings + 20
checklist). `data/generated_properties.json` was removed as it is now superseded
by the theorem_map entries.

## 2026-07-23 — severity model aligned to EF bug-bounty

The improve/generate command now surfaces the **Ethereum Foundation bug-bounty
severity definition** (`judge.EF_BOUNTY_SEVERITY`) in the prompt, so a sharpened
or generated critical/high item stays aimed at the bounty threat model:
network-scale impact reachable REMOTELY by a single message/transaction
(Critical = whole-network halt / fund-integrity break / >50% slashing; High =
~>33%; Medium = ~>5%). The teaching corpus `data/ethereum_vulns_high.csv` is
now built explicitly from the dataset's `severity_estimated` column — the
bounty-aligned severity (computed against this definition and calibrated on the
bounty-graded rows), NOT the advisory/CVSS `severity` column. (176 rows; the two
columns' critical/high sets happened to coincide here, but the derivation is now
unambiguous for future dataset updates.) Defensive framing verified: claude
accepts the severity-augmented prompt with no cyber-safeguard refusal.

## 2026-07-23 — run 2 (severity-aware, 6 items)

First run with `EF_BOUNTY_SEVERITY` in the prompt. judge=kimi, improve=claude,
teaching=critical/high (severity_estimated). Overall 4.63 → 4.83; 6 items
sharpened (CHK-AS-03, CHK-QW-01, CHK-QW-02, CHK-LV-01, CHK-GEN-01, CHK-GEN-02),
all within the granularity band. Self-preference (kimi): CHK-20 **4.59** vs
solodit **2.96**, ranking preserved. Diff: [`9a59d02`](https://github.com/NyxFoundation/speca-lean4-plugin/commit/9a59d02b8fc9c34870c9292ad068ef94681df2b3)
