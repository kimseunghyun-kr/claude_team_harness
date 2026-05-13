#!/usr/bin/env bash
# detect-contested.sh
# Thin shim — logic lives in detect_contested.py (v0.1.1).

set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/detect_contested.py" "$@"
