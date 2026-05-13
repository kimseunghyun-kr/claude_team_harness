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

    # Build manifest. The prompt is plain text the SKILL.md procedure passes to
    # Task; the persona file's frontmatter is what the Agent tool resolves on
    # spawn (in a fresh CC session where personas/<id>.md is registered).
    spawns = [
        {
            "subagent_type": persona,
            "prompt": (
                "mode=BID\n"
                f"epoch={epoch}\n"
                f"slot={slot}\n"
                f"sketchboard_path={cfg.sketchboard_path}\n"
                "prior_bids_visible=false"
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
