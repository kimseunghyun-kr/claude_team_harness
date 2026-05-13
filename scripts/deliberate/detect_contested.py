#!/usr/bin/env python3
"""Detect contested-section pairs in Sketchboard.md (replaces detect-contested.sh).

Usage:
  python3 detect_contested.py [<sketchboard-path>] [--epoch N]

Default sketchboard_path comes from harness.toml [deliberation].sketchboard_path.

Audit fix #2: the pairing logic now requires evidence that block A actually
engages with block B (A quotes a line from B's body, or A names B's display
verbatim) — not just "A contains a trigger keyword."
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.config import read_config, sketchboard_abs_path  # noqa: E402
from lib.detect import detect_contested  # noqa: E402


def main() -> None:
    argv = sys.argv[1:]
    epoch_filter: int | None = None
    sb_path: Path | None = None

    while argv:
        a = argv.pop(0)
        if a == "--epoch":
            if not argv:
                print(json.dumps({"error": "missing-value-for-epoch"}, separators=(",", ":")))
                sys.exit(2)
            epoch_filter = int(argv.pop(0))
        elif a.startswith("--"):
            print(json.dumps({"error": f"unknown-flag:{a}"}, separators=(",", ":")))
            sys.exit(2)
        else:
            sb_path = Path(a)

    if sb_path is None:
        sb_path = sketchboard_abs_path(read_config())

    if not sb_path.exists():
        print(json.dumps({
            "contested": [],
            "scanned_blocks": 0,
            "heuristic_version": "v0.1-keyword",
            "error": "sketchboard-not-found",
            "path": str(sb_path),
        }, separators=(",", ":")))
        sys.exit(1)

    result = detect_contested(sb_path.read_text(), epoch_filter=epoch_filter)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
