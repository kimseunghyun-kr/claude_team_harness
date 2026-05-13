#!/usr/bin/env bash
# orchestrate-epoch.sh
# Thin shim — orchestrator logic lives in orchestrate_epoch.py (v0.1.1).
# Shell was fragile for heredoc interpolation, config-knob honesty, and quoting.
# This shim preserves the call surface (SKILL.md + tests) without changing it.

set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/orchestrate_epoch.py" "$@"
