#!/usr/bin/env python3
"""Build the BID spawn manifest for a slot.

v0.1.2 changes:
  - Manifest now includes per-persona BID history (this epoch only) for memory
    injection into the reasoning prompt.
  - Eavesdrop excerpts injected probabilistically when eavesdrop_enabled=true.
  - Spawn entries are reasoning-turn manifests (worktree-aware) when the
    flow is two-turn. The legacy single-turn manifest (without worktree) is
    still emitted under spawns[].prompt for sequential mode + tests; the
    two-turn fields (reasoning_branch, worktree_path) are sidecars the SKILL
    procedure uses to drive worktree creation + extraction.
  - Lazy orphan-worktree audit at start (audit fix: crash recovery).

Audit fixes preserved:
  #7  pure Python; no shell heredoc
  #9  config path honored throughout
  #11 no shell interpolation
  #J  single TOML reader via lib.config
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.config import read_config, repo_root, sketchboard_abs_path, state_dir  # noqa: E402
from lib.state import (  # noqa: E402
    audit_orphan_worktrees,
    bid_log_path,
    reasoning_branch_name,
    worktree_path,
    load_state,
)


_TIGHT = (",", ":")


def err(payload: dict, code: int = 1) -> None:
    print(json.dumps(payload, separators=_TIGHT))
    sys.exit(code)


def _load_bid_history(epoch: int, persona: str) -> list[dict]:
    """Return this epoch's prior bids for the given persona, oldest first."""
    log_path = bid_log_path(epoch)
    if not log_path.exists():
        return []
    out: list[dict] = []
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("persona") == persona:
            out.append({
                "slot": rec.get("slot"),
                "bid": rec.get("bid", 0.0),
                "reason": rec.get("reason", ""),
                "won": rec.get("won", False),
            })
    return out


def _read_branch_excerpt(branch: str, max_chars: int = 300) -> str:
    """Read the latest reasoning content from a branch and trim to max_chars.

    Used for eavesdrop. v0.1.2 limit: naive first-N-chars excerpt; v0.1.3
    upgrade path is to extract the structured bid-intent line. See
    references/persona-modes.md eavesdrop section.
    """
    rel_path = f".claude/state/deliberation/branches/{branch.split('/', 1)[1].split('/')[0]}/reasoning.md"
    try:
        result = subprocess.run(
            ["git", "show", f"{branch}:{rel_path}"],
            cwd=str(repo_root()),
            capture_output=True,
            text=True,
            check=True,
        )
        text = result.stdout
    except subprocess.CalledProcessError:
        # Fallback: commit message body
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%B", branch],
                cwd=str(repo_root()),
                capture_output=True,
                text=True,
                check=True,
            )
            text = result.stdout
        except subprocess.CalledProcessError:
            return ""
    text = text.replace("\n", " ").strip()
    return text[:max_chars]


def _sample_eavesdrop(
    target_persona: str,
    other_personas: list[str],
    epoch: int,
    slot: int,
    probability: float,
) -> list[dict]:
    """For each other persona, sample whether to inject their most recent
    reasoning branch as an eavesdrop excerpt for target_persona.

    Returns: [{"from_persona": id, "excerpt": str}, ...] for triggered samples.
    Empty list if eavesdrop_enabled=false (caller's responsibility — we don't
    re-check here).
    """
    rng = random.Random(f"{target_persona}:{epoch}:{slot}")
    out: list[dict] = []
    for other in other_personas:
        if rng.random() >= probability:
            continue
        # Look for the most recent reasoning branch from this other persona this epoch
        # Branches: persona/<other>/{bid|write}-epoch-<epoch>-slot-<S>
        try:
            result = subprocess.run(
                [
                    "git", "for-each-ref",
                    f"--format=%(refname:short)",
                    f"refs/heads/persona/{other}/",
                ],
                cwd=str(repo_root()),
                capture_output=True,
                text=True,
                check=True,
            )
            branches = [b.strip() for b in result.stdout.splitlines() if b.strip()]
            # Pick the most recent commit (HEAD time) branch
            if not branches:
                continue
            # For simplicity, pick the branch with the largest slot number for this epoch
            best = None
            best_slot = -1
            for b in branches:
                import re
                m = re.search(rf"epoch-{epoch}-slot-(\d+)$", b)
                if m:
                    s = int(m.group(1))
                    if s > best_slot:
                        best_slot = s
                        best = b
            if best is None:
                continue
            excerpt = _read_branch_excerpt(best)
            if excerpt:
                out.append({"from_persona": other, "excerpt": excerpt, "branch": best})
        except subprocess.CalledProcessError:
            continue
    return out


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

    sb_path = sketchboard_abs_path(cfg)
    if not sb_path.exists():
        err({"error": "sketchboard-missing", "path": cfg.sketchboard_path})

    # v0.1.2: lazy orphan-worktree audit before any spawn manifest is produced.
    # If the orchestrator crashed mid-slot in a prior run, leftover worktrees
    # would block worktree_create. Clean them up here.
    state = load_state()
    audit_orphan_worktrees(
        current_epoch=epoch,
        current_state=(state.get("state") if state else "COLLECTING"),
    )

    # Build spawn manifests with bid memory + eavesdrop (if enabled).
    sb_abs = str(sb_path)
    contract = (
        "REQUIRED OUTPUT: exactly one JSON line on stdout, no prose before or after, no markdown fences.\n"
        "Shape: {\"bid\": NUMBER, \"reason\": STRING}\n"
        "  - bid must be a FLOAT in [0.0, 1.0]. Integer 0 or 1 is accepted. 6, 8, -1, etc. are CONTRACT VIOLATIONS.\n"
        "  - reason must use the key name \"reason\" (NOT \"rationale\" / \"why\" / etc.) and be a string ≤140 chars.\n"
        "  - bid=0.0 = abstain (you have nothing to contribute given current state).\n"
        "  - Do NOT modify any file in BID mode (read-only). Postcheck will reject any diff.\n"
    )

    spawns = []
    for persona in cfg.personas:
        bid_history = _load_bid_history(epoch, persona)
        eavesdrop_excerpts = []
        if cfg.eavesdrop_enabled:
            other_personas = [p for p in cfg.personas if p != persona]
            eavesdrop_excerpts = _sample_eavesdrop(
                persona, other_personas, epoch, slot, cfg.eavesdrop_probability
            )

        # Build bid memory text for injection
        bid_memory = ""
        if bid_history:
            bid_memory = "\nYour prior bids this epoch:\n"
            for h in bid_history:
                bid_memory += (
                    f"  slot {h['slot']}: bid={h['bid']:.2f}, won={h['won']}, "
                    f"reason=\"{(h['reason'] or '')[:100]}\"\n"
                )

        # Eavesdrop block (only if any triggered)
        eavesdrop_block = ""
        if eavesdrop_excerpts:
            eavesdrop_block = "\n(Eavesdropped overheard reasoning — non-binding):\n"
            for e in eavesdrop_excerpts:
                eavesdrop_block += f"  from {e['from_persona']}: {e['excerpt']}\n"

        prompt = (
            "mode=BID\n"
            f"epoch={epoch}\n"
            f"slot={slot}\n"
            f"sketchboard_path={sb_abs}\n"
            "prior_bids_visible=true\n"  # v0.1.2 flips this — we now inject memory
            + bid_memory
            + eavesdrop_block
            + "\n"
            + contract
        )

        spawns.append({
            "subagent_type": persona,
            "prompt": prompt,
            # v0.1.2 sidecars for the two-turn flow (SKILL.md uses these to
            # drive worktree_create + reasoning-manifest + extraction-manifest):
            "reasoning_branch": reasoning_branch_name(persona, epoch, slot, "bid"),
            "worktree_path": str(worktree_path(persona, epoch, slot)),
            "bid_history": bid_history,
            "eavesdrop_excerpts": eavesdrop_excerpts,
        })

    print(json.dumps({
        "epoch": epoch,
        "slot": slot,
        "sketchboard_path": cfg.sketchboard_path,
        "personas": list(cfg.personas),
        "spawn_mode": cfg.spawn_mode,
        "spawns": spawns,
    }, separators=_TIGHT))


if __name__ == "__main__":
    main()
