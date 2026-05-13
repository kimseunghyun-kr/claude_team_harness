#!/usr/bin/env bash
# collect-bids.sh
# Thin shim — logic lives in collect_bids.py (v0.1.1).

set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/collect_bids.py" "$@"
