#!/usr/bin/env bash
# spawn-winner.sh
# Thin shim — logic lives in spawn_winner.py (v0.1.1).

set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/spawn_winner.py" "$@"
