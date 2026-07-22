#!/usr/bin/env bash
# Cross-family LLM adapter for the stage-2 judge/improve harness (speca#88/#143).
#
# Contract (see judge.subprocess_llm): read ONE prompt on stdin, print the
# model's raw text response on stdout, exit 0. This lets the judge run against
# a NON-Claude model so the "same quality level" verdict is not a same-family
# self-judge (speca#143 self-preference check).
#
# It routes through the Hermes agent, which is already configured here for a
# cross-family provider (e.g. `custom:ollama-cloud` / kimi). Tools are disabled
# (`-t ""`): the judge/improve prompt is self-contained and must not trigger an
# agentic tool loop. Any extra args are forwarded, so you can override model or
# provider per run:
#
#   speca-lean4 judge  --ours 01e.json \
#     --llm-cmd "bash tools/llm-hermes.sh"
#   # cross-family override:
#   speca-lean4 judge  --ours 01e.json \
#     --llm-cmd "bash tools/llm-hermes.sh -m kimi-k2.6 --provider custom:ollama-cloud"
#
# No API key is read or forwarded by this script; auth lives in the Hermes CLI.
set -euo pipefail
prompt="$(cat)"
exec hermes -z "$prompt" -t "" "$@"
