#!/usr/bin/env bash
# Run a command with a working `lake`/`lean` on PATH.
#
# This machine is NixOS: the elan installed under ~/.elan is unusable (its
# shims carry a stale /nix/store bash interpreter), and upstream Lean release
# tarballs are not FHS-compatible. nixpkgs' `elan` handles both — it patches
# the toolchains it downloads — so every Lean invocation in this repo goes
# through it.
#
# Usage:  tools/lean-env.sh lake build
#         tools/lean-env.sh lake exe speca-export --targets t.txt --output h.json
set -euo pipefail
exec nix shell nixpkgs#elan --command "$@"
