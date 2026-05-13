#!/usr/bin/env python3
"""Deliberation epoch orchestrator (replaces orchestrate-epoch.sh).

Subcommands:
  init <question>             create Sketchboard.md from template + begin epoch 1
  begin <epoch>               initialize state file
  tally <epoch> <slot>        read JSON array of bids from stdin, return winner or close
  commit-or-forfeit <epoch> <slot> <persona>
                              postcheck winner's diff; commit or revert+forfeit
  close <epoch> [reason]      tag epoch-N-unratified, transition to REVIEW
  ratify                      advance ratified ref + open next epoch
  status                      print epoch.json

Audit fixes vs the prior shell version (numbered references match the audit doc):
  #6  budget reads from harness.toml (not hardcoded 5)
  #7  no shell heredoc interpolation; argv/stdin-based throughout
  #8  --no-verify removed; git hooks now run on all orchestrator commits
  #9  sketchboard_path and epoch_state_path honored throughout
  #10 ratify fails loudly if "## Open Conflicts" section is missing
  #11 question and other strings passed via argv; subprocess never uses shell=True
  #12 close uses `tag -f` and reports drift loudly
  #15 datetime calls use timezone-aware UTC
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

# Allow running from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.config import read_config, repo_root, sketchboard_abs_path  # noqa: E402
from lib.postcheck import write_postcheck  # noqa: E402
from lib.sketchboard import append_next_epoch_section, render_template  # noqa: E402
from lib.state import (  # noqa: E402
    append_bids,
    begin_next_epoch,
    bid_log_path,
    close_epoch,
    git,
    git_capture,
    git_dirty,
    increment_slots_used,
    init_epoch_state,
    load_state,
    mark_forfeit_in_log,
    mark_winner_in_log,
    ratify,
    save_state,
)


_TIGHT = (",", ":")  # match prior shell JSON output for grep compat


def err(payload: dict, exit_code: int = 1) -> None:
    print(json.dumps(payload, separators=_TIGHT))
    sys.exit(exit_code)


def ok(payload: dict) -> None:
    print(json.dumps(payload, separators=_TIGHT))
    sys.exit(0)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_init(args: list[str]) -> None:
    if not args:
        err({"error": "usage: init <question>"}, 2)
    question = " ".join(args).strip()
    if not question:
        err({"error": "empty-question"}, 2)

    cfg = read_config()
    sb_path = sketchboard_abs_path(cfg)
    if sb_path.exists():
        err({
            "error": "sketchboard-exists",
            "hint": f"delete or rename {cfg.sketchboard_path} first",
        })
    if git_dirty():
        err({
            "error": "dirty-tree",
            "hint": "commit or stash before init; orchestrator commits per slot",
        })

    template_path = repo_root() / "templates" / "Sketchboard.md.tmpl"
    if not template_path.exists():
        err({"error": "template-missing", "path": str(template_path)})

    rendered = render_template(
        template_path.read_text(),
        question=question,
        frame="",
        personas=cfg.personas,
    )
    sb_path.write_text(rendered)

    # Commit. Audit #8: no --no-verify.
    git("add", str(sb_path.relative_to(repo_root())))
    git("commit", "-m", f"init(deliberation): epoch 1 — {question}")

    init_epoch_state(epoch=1)
    ok({
        "ok": True,
        "epoch": 1,
        "state": "COLLECTING",
        "sketchboard_path": cfg.sketchboard_path,
        "question": question,
    })


def cmd_begin(args: list[str]) -> None:
    epoch = int(args[0]) if args else 1
    init_epoch_state(epoch)
    ok({"ok": True, "epoch": epoch, "state": "COLLECTING"})


def cmd_tally(args: list[str]) -> None:
    if len(args) < 2:
        err({"error": "usage: tally <epoch> <slot>"}, 2)
    epoch, slot = int(args[0]), int(args[1])

    bids_raw = sys.stdin.read()
    try:
        bids = json.loads(bids_raw)
    except json.JSONDecodeError as e:
        err({"error": "bad-bid-json", "detail": str(e)}, 2)

    if not isinstance(bids, list) or not bids:
        err({"error": "empty-bids"}, 2)

    append_bids(epoch, slot, bids)

    active = [b for b in bids if float(b["bid"]) > 0.0]
    if not active:
        ok({"action": "close", "reason": "all-abstain"})

    cfg = read_config()
    max_bid = max(float(b["bid"]) for b in active)
    tied = [b for b in active if float(b["bid"]) == max_bid]

    if len(tied) == 1:
        winner = tied[0]
    elif cfg.bid_tiebreaker == "random":
        rng = random.Random(f"{epoch}:{slot}")
        winner = rng.choice(tied)
    else:  # declaration-order (default and unknown fall-back)
        order_idx = {p: i for i, p in enumerate(cfg.personas)}
        winner = min(tied, key=lambda b: order_idx.get(b["persona"], 999))

    mark_winner_in_log(epoch, slot, winner["persona"])
    ok({
        "action": "spawn",
        "persona": winner["persona"],
        "bid": float(winner["bid"]),
        "reason": winner.get("reason", ""),
    })


def cmd_commit_or_forfeit(args: list[str]) -> None:
    if len(args) < 3:
        err({"error": "usage: commit-or-forfeit <epoch> <slot> <persona>"}, 2)
    epoch, slot, persona = int(args[0]), int(args[1]), args[2]

    result = write_postcheck(persona, epoch)

    cfg = read_config()
    sb_rel = cfg.sketchboard_path

    if result["ok"]:
        git("add", sb_rel)
        # Audit #8: hooks run on slot commits.
        git("commit", "-m", f"epoch-{epoch} slot-{slot}: {persona}")
        increment_slots_used(slot)
        ok({"committed": True, "slot": slot, "persona": persona})
    else:
        # Revert and log forfeit. Audit #9: revert the configured path, not hardcoded.
        git("checkout", "--", sb_rel)
        mark_forfeit_in_log(epoch, slot, persona, result.get("failure", "unknown"))
        ok({
            "committed": False,
            "slot": slot,
            "persona": persona,
            "failure": result.get("failure"),
            "detail": result.get("detail"),
        })


def cmd_close(args: list[str]) -> None:
    if not args:
        err({"error": "usage: close <epoch> [reason]"}, 2)
    epoch = int(args[0])
    reason = args[1] if len(args) > 1 else "budget-exhausted"
    state = close_epoch(epoch, reason)
    ok({
        "closed": True,
        "epoch": epoch,
        "reason": reason,
        "tag": f"epoch-{epoch}-unratified",
        "state": state["state"],
    })


def cmd_ratify(_args: list[str]) -> None:
    state = load_state()
    if state is None:
        err({"error": "no-active-deliberation", "hint": "call init first"})
    cur_epoch = int(state["epoch"])
    if state["state"] != "REVIEW":
        err({
            "error": "wrong-state",
            "current": state["state"],
            "hint": f"ratify only valid in REVIEW state; epoch {cur_epoch} is in {state['state']}",
        })

    # Verify the unratified tag exists
    try:
        git_capture("rev-parse", f"epoch-{cur_epoch}-unratified")
    except RuntimeError:
        err({"error": "missing-tag", "tag": f"epoch-{cur_epoch}-unratified"})

    # Append next-epoch section to sketchboard (audit #10: fail loudly if section missing)
    cfg = read_config()
    sb_path = sketchboard_abs_path(cfg)
    next_epoch = cur_epoch + 1
    try:
        new_content = append_next_epoch_section(sb_path.read_text(), next_epoch)
    except ValueError as e:
        err({"error": "section-append-failed", "detail": str(e)})
    sb_path.write_text(new_content)

    git("add", cfg.sketchboard_path)
    git("commit", "-m", f"ratify(deliberation): epoch {cur_epoch} ratified → open epoch {next_epoch}")

    ratified_state = ratify(cur_epoch)
    ratified_sha = git_capture("rev-parse", "--short", "ratified")

    # Immediately advance state to the next epoch.
    begin_next_epoch(next_epoch)

    ok({
        "ratified_epoch": cur_epoch,
        "ratified_sha": ratified_sha,
        "next_epoch": next_epoch,
        "state": "COLLECTING",
    })


def cmd_status(_args: list[str]) -> None:
    state = load_state()
    if state is None:
        err({"error": "no-active-deliberation", "hint": "call init first"})
    print(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


COMMANDS = {
    "init": cmd_init,
    "begin": cmd_begin,
    "tally": cmd_tally,
    "commit-or-forfeit": cmd_commit_or_forfeit,
    "close": cmd_close,
    "ratify": cmd_ratify,
    "status": cmd_status,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        err(
            {
                "error": (
                    "usage: orchestrate_epoch.py "
                    "(init|begin|tally|commit-or-forfeit|close|ratify|status) ..."
                )
            },
            2,
        )
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
