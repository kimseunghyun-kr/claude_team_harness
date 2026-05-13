#!/usr/bin/env python3
"""Build the parallel-BID-spawn manifest for a slot (replaces collect-bids.sh).

Usage:
  python3 collect_bids.py <epoch> <slot>

Output (stdout): JSON manifest the SKILL.md run procedure consumes to issue
parallel Task-tool spawns.

Audit fixes:
  #7  no shell heredoc — pure Python
  #9  config path honored (sketchboard_path read from harness.toml)
  #11 no shell interpolation in the emitted prompts (json.dumps escapes)
  #J  single TOML reader (lib.config) — eliminates DRY violation
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.config import read_config, repo_root, sketchboard_abs_path  # noqa: E402


_TIGHT = (",", ":")


def err(payload: dict, code: int = 1) -> None:
    print(json.dumps(payload, separators=_TIGHT))
    sys.exit(code)


def main() -> None:
    if len(sys.argv) < 3:
        err({"error": "usage: collect_bids.py <epoch> <slot>"}, 2)
    try:
        epoch = int(sys.argv[1])
        slot = int(sys.argv[2])
    except ValueError:
        err({"error": "epoch and slot must be integers"}, 2)

    cfg = read_config()

    if not cfg.enabled:
        err({
            "error": "deliberation-disabled",
            "hint": "set [deliberation].enabled = true in harness.toml",
        })

    # Validate config BEFORE runtime state (audit fix from prior round)
    if len(cfg.personas) < 2:
        err({
            "error": "insufficient-personas",
            "count": len(cfg.personas),
            "hint": "need >= 2",
        })

    agents_dir = repo_root() / "agents"
    for persona in cfg.personas:
        if not (agents_dir / f"{persona}.md").exists():
            err({
                "error": "persona-file-missing",
                "persona": persona,
                "expected_path": f"agents/{persona}.md",
            })

    # Runtime state
    sb_path = sketchboard_abs_path(cfg)
    if not sb_path.exists():
        err({"error": "sketchboard-missing", "path": cfg.sketchboard_path})

    # Build manifest. Fix #C: emit ABSOLUTE sketchboard_path so personas can
    # find the file regardless of their Agent runtime cwd. Fix #D: include an
    # inline contract reminder so personas don't drift on BID shape.
    sb_abs = str(sb_path)
    contract = (
        "REQUIRED OUTPUT: exactly one JSON line on stdout, no prose before or after, no markdown fences.\n"
        "Shape: {\"bid\": NUMBER, \"reason\": STRING}\n"
        "  - bid must be a FLOAT in [0.0, 1.0]. Integer 0 or 1 is accepted. 6, 8, -1, etc. are CONTRACT VIOLATIONS.\n"
        "  - reason must use the key name \"reason\" (NOT \"rationale\" / \"why\" / etc.) and be a string ≤140 chars.\n"
        "  - bid=0.0 = abstain (you have nothing to contribute given current state).\n"
        "  - Do NOT modify any file in BID mode (read-only). Postcheck will reject any diff.\n"
    )
    spawns = [
        {
            "subagent_type": persona,
            "prompt": (
                "mode=BID\n"
                f"epoch={epoch}\n"
                f"slot={slot}\n"
                f"sketchboard_path={sb_abs}\n"
                "prior_bids_visible=false\n\n"
                + contract
            ),
        }
        for persona in cfg.personas
    ]

    print(json.dumps({
        "epoch": epoch,
        "slot": slot,
        "sketchboard_path": cfg.sketchboard_path,
        "personas": list(cfg.personas),
        "spawns": spawns,
    }, separators=_TIGHT))


if __name__ == "__main__":
    main()
