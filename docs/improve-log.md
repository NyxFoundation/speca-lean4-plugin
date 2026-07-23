# Improve-loop run log (speca#88 / #143)

Each entry records one stage-2 self-improvement run: the models used, the
teaching corpus, the score progression, which CHK-* properties were sharpened,
and the **commit** that persisted the sharpened `text`/`assertion` into
`theorem_map.json`. Open that commit to see the exact before/after diff of the
property changes.

Run the loop with `tools/run-improve.sh`; persist with `tools/apply-improved.py`
(see `docs/judge-loop.md`).

<!-- newest first -->
