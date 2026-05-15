"""Epoch state management: epoch.json + bid log + git refs/tags.

Centralizes everything that was previously sprinkled across shell heredocs.
Datetime calls use timezone-aware UTC (fixes audit #15 — utcnow() deprecation).
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any

from .config import read_config, repo_root, state_dir


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch_json_path() -> Path:
    return state_dir() / "epoch.json"


def bid_log_path(epoch: int) -> Path:
    return state_dir() / f"epoch-{epoch}-bids.jsonl"


def ensure_state_dir() -> None:
    state_dir().mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, Any] | None:
    path = epoch_json_path()
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_state(state: dict[str, Any]) -> None:
    epoch_json_path().write_text(json.dumps(state, indent=2) + "\n")


def init_epoch_state(epoch: int) -> dict[str, Any]:
    """Initialize epoch.json for a new epoch. Reads budget from config
    (audit #6 — was hardcoded to 5)."""
    cfg = read_config()
    ensure_state_dir()
    state = {
        "epoch": epoch,
        "state": "COLLECTING",
        "budget": cfg.epoch_commit_budget,
        "slots_used": 0,
        "close_reason": None,
        "personas": list(cfg.personas),
        "started_at": _now_utc(),
        "closed_at": None,
    }
    save_state(state)
    # Always start with a clean bid log for this epoch (audit #14).
    bid_log_path(epoch).write_text("")
    return state


def append_bids(epoch: int, slot: int, bids: list[dict[str, Any]]) -> None:
    """Append all bids (including bid=0 abstains) to the bid log."""
    path = bid_log_path(epoch)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for b in bids:
            rec = {
                "slot": slot,
                "persona": b["persona"],
                "bid": float(b["bid"]),
                "reason": b.get("reason", ""),
                "won": False,
            }
            f.write(json.dumps(rec) + "\n")


def mark_winner_in_log(epoch: int, slot: int, persona: str) -> None:
    path = bid_log_path(epoch)
    if not path.exists():
        return
    lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for rec in lines:
        if rec["slot"] == slot and rec["persona"] == persona:
            rec["won"] = True
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n")


def mark_forfeit_in_log(epoch: int, slot: int, persona: str, failure: str) -> None:
    path = bid_log_path(epoch)
    if not path.exists():
        return
    lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for rec in lines:
        if rec["slot"] == slot and rec["persona"] == persona and rec.get("won"):
            rec["forfeit"] = True
            rec["postcheck_failure"] = failure
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n")


def increment_slots_used(slot: int) -> None:
    state = load_state()
    if state is None:
        return
    state["slots_used"] = slot
    save_state(state)


def close_epoch(epoch: int, reason: str) -> dict[str, Any]:
    state = load_state()
    if state is None:
        raise RuntimeError("no active deliberation; call init first")
    state["state"] = "REVIEW"
    state["close_reason"] = reason
    state["closed_at"] = _now_utc()
    save_state(state)
    # Tag the current HEAD as epoch-N-unratified. Audit #12: force-update with
    # `-f` so re-runs aren't silently swallowed; if the tag must move, do so
    # explicitly.
    git("tag", "-f", f"epoch-{epoch}-unratified")
    return state


def ratify(cur_epoch: int) -> dict[str, Any]:
    state = load_state()
    if state is None:
        raise RuntimeError("no active deliberation")
    if state["state"] != "REVIEW":
        raise RuntimeError(f"ratify only valid in REVIEW state; got {state['state']}")
    tag = f"epoch-{cur_epoch}-unratified"
    git("update-ref", "refs/heads/ratified", git_capture("rev-parse", tag))
    # NOTE (audit #16): refs/heads/ratified creates a branch named "ratified".
    # Cleaner would be refs/ratified/HEAD. Deferred to v0.2 to avoid breaking
    # callers that already rely on `git branch ratified`.
    state["state"] = "RATIFIED"
    state["ratified_at"] = _now_utc()
    save_state(state)
    return state


def begin_next_epoch(next_epoch: int) -> None:
    """Open epoch N+1 in state COLLECTING (called immediately after ratify)."""
    state = load_state()
    if state is None:
        state = {}
    state.update(
        {
            "epoch": next_epoch,
            "state": "COLLECTING",
            "slots_used": 0,
            "close_reason": None,
            "started_at": _now_utc(),
            "closed_at": None,
        }
    )
    # Keep budget + personas from config in case they changed.
    cfg = read_config()
    state["budget"] = cfg.epoch_commit_budget
    state["personas"] = list(cfg.personas)
    save_state(state)
    bid_log_path(next_epoch).write_text("")


# ---------------------------------------------------------------------------
# Git helpers — argv-based, no shell. Audit #11 (shell injection) is avoided
# by never calling subprocess with shell=True.
# ---------------------------------------------------------------------------


def git(*args: str) -> int:
    result = subprocess.run(
        ["git", *args], cwd=str(repo_root()), capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return result.returncode


def git_capture(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo_root()), capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def git_dirty() -> bool:
    """True if the working tree has TRACKED uncommitted changes.

    v0.1.2 fix: untracked files (`??` prefix) no longer count. They don't risk
    commit-bleed because the orchestrator's commits use `--only <pathspec>` and
    never `git add -A`. A leftover sample file or IDE swap file should not
    block `init`.

    What DOES count: modifications to tracked files, staged changes, renames,
    deletions, conflicts. All of these could bleed into the next epoch commit
    if not isolated, and the orchestrator's `--only` pathspec is the second
    line of defense — but it's safer to refuse upfront than to silently drop
    user work into a deliberation commit.
    """
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
    ).stdout
    tracked_changes = [l for l in out.splitlines() if l and not l.startswith("??")]
    return bool(tracked_changes)
