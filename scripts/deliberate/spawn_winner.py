#!/usr/bin/env python3
"""Build WRITE-mode spawn manifest + run BID/WRITE postcheck (replaces spawn-winner.sh).

Two subcommands:
  manifest <persona> <epoch> <slot> <bid> <reason>
      Print the WRITE spawn manifest for the bid winner.
  postcheck <persona> <epoch>
      Validate the worktree diff against the WRITE-mode contract.
  bid-postcheck
      (stdin) Validate persona BID-mode stdout for shape + no file changes.

Audit fixes:
  #1  FORBIDDEN_TOUCHED dead-code replaced with real section-boundary parsing
  #4  persona display name read from agents/<id>.md (not derived from id)
  #5  BID postcheck now lives here (was skill-only) — single enforcement boundary
  #11 all values pass through argv/stdin; subprocess never uses shell=True
  #13 diff position verified via lib/sketchboard.verify_block_in_epoch
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.config import read_config, repo_root  # noqa: E402
from lib.postcheck import bid_postcheck, write_postcheck  # noqa: E402


_TIGHT = (",", ":")


def err(payload: dict, code: int = 1) -> None:
    print(json.dumps(payload, separators=_TIGHT))
    sys.exit(code)


def cmd_manifest(args: list[str]) -> None:
    if len(args) < 4:
        err({"error": "usage: manifest <persona> <epoch> <slot> <bid> [reason]"}, 2)
    persona, epoch_s, slot_s, bid_s, *rest = args
    reason = " ".join(rest) if rest else ""

    cfg = read_config()
    persona_file = repo_root() / "agents" / f"{persona}.md"
    if not persona_file.exists():
        err({"error": "persona-file-missing", "persona": persona})

    # Audit #P: use absolute sketchboard path so personas can resolve regardless
    # of their working directory.
    sb_abs = (repo_root() / cfg.sketchboard_path).resolve()

    prompt = (
        "mode=WRITE\n"
        f"epoch={epoch_s}\n"
        f"slot={slot_s}\n"
        f"sketchboard_path={sb_abs}\n"
        f"your_winning_bid={bid_s}\n"
        f"your_winning_reason={reason}"
    )
    print(json.dumps({
        "subagent_type": persona,
        "prompt": prompt,
        "sketchboard_path": cfg.sketchboard_path,
    }, separators=_TIGHT))


def cmd_postcheck(args: list[str]) -> None:
    if len(args) < 2:
        err({"error": "usage: postcheck <persona> <epoch>"}, 2)
    persona, epoch_s = args[0], args[1]
    try:
        epoch = int(epoch_s)
    except ValueError:
        err({"error": "epoch-must-be-int"}, 2)
    result = write_postcheck(persona, epoch)
    print(json.dumps(result))
    # Audit policy: always exit 0; ok=false is a normal forfeit signal, not an error.
    sys.exit(0)


def cmd_bid_postcheck(_args: list[str]) -> None:
    stdout = sys.stdin.read()
    result = bid_postcheck(stdout)
    print(json.dumps(result, separators=_TIGHT))
    sys.exit(0)


COMMANDS = {
    "manifest": cmd_manifest,
    "postcheck": cmd_postcheck,
    "bid-postcheck": cmd_bid_postcheck,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        err({"error": "usage: spawn_winner.py (manifest|postcheck|bid-postcheck) ..."}, 2)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
