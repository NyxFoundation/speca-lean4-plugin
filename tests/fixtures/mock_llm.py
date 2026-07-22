"""Deterministic stand-in for the --llm-cmd adapter (CI runs with NO API key).

Reads one prompt on stdin, writes one response on stdout — the same contract
`judge.subprocess_llm` expects from e.g. `claude -p`. Judge prompts get a
fixed five-axis score derived (deterministically) from the item text hash so
distributions are stable but non-degenerate; improve prompts get a sharpened
text/assertion rewrite.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys


def main() -> int:
    # the adapter contract is UTF-8 on both pipes regardless of locale
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    prompt = sys.stdin.read()
    if "sharpening ONE audit-checklist item" in prompt:
        m = re.search(r"^TEXT: (.*)$", prompt, re.MULTILINE)
        base = (m.group(1).strip() if m else "the checked invariant").rstrip(".")
        print(json.dumps({
            "text": f"{base} — verify the exact uint64 arithmetic, bounds checks "
                    "and rejection path on the decode-to-comparison route",
            "assertion": "forall f in decoded_fields: width(f) == spec_width(f) "
                         "and bounds_checked(f) before use(f)",
        }))
        return 0
    # judge prompt: deterministic per-item scores in 3..5 keyed off the CHECK line
    m = re.search(r"^CHECK: (.*)$", prompt, re.MULTILINE)
    seed = hashlib.sha256((m.group(1) if m else prompt).encode()).digest()
    axes = ["specificity", "implementation_readiness", "generality",
            "actionability", "granularity"]
    scores = {ax: 3 + seed[i] % 3 for i, ax in enumerate(axes)}
    print(json.dumps({
        "scores": scores,
        "critique": "mock: deterministic scores for CI wiring only",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
