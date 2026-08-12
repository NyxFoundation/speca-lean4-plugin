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
#
# Resolving the binary: on a NixOS workstation `hermes` is often only a zsh
# alias to a /nix/store path, so it is invisible to this (bash) script. Set
# HERMES_BIN to point at it, e.g.
#   export HERMES_BIN="$(zsh -ic 'alias hermes' | cut -d= -f2-)"
# Otherwise PATH is used.
set -euo pipefail
HERMES_BIN="${HERMES_BIN:-hermes}"
if ! command -v "$HERMES_BIN" >/dev/null 2>&1; then
    echo "llm-hermes.sh: '$HERMES_BIN' not found on PATH — set HERMES_BIN to the hermes binary" >&2
    exit 127
fi
prompt="$(cat)"
exec "$HERMES_BIN" -z "$prompt" -t "" "$@"
