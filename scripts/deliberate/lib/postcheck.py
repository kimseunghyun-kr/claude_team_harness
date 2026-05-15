"""Postcheck for persona spawns.

Two modes, matching the BID/WRITE persona contract:
  - bid_postcheck:   verify zero files changed AND stdout is parseable JSON
                     with shape {bid: number, reason: string}
  - write_postcheck: verify exactly sketchboard_path changed, diff is purely
                     additive, addition lands in current epoch section, block
                     has the right persona heading and ≥1 blockquote.

Audit fixes:
  #1  FORBIDDEN_TOUCHED dead code → real section parsing via sketchboard.py
  #4  brittle persona-name derivation → reads display from agents/<id>.md
  #5  BID stdout enforcement was skill-only → now also enforced here
  #13 diff-position check → uses sketchboard.parse_sketchboard for boundaries
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import read_config, repo_root, sketchboard_abs_path
from .sketchboard import id_to_display_name_from_file, verify_block_in_epoch


def _git_show_prev(path: Path) -> str:
    """Return the HEAD version of a tracked file. Empty string if not in HEAD."""
    rel = path.relative_to(repo_root())
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=str(repo_root()),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return ""


def _git_changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
        check=True,
    )
    return [l for l in result.stdout.splitlines() if l.strip()]


def branch_isolation_check(
    persona_id: str,
    pre_refs: dict[str, str],
    post_refs: dict[str, str],
) -> dict:
    """Verify the only refs modified during the spawn belong to this persona.

    v0.1.2 phase 3a infrastructure. Used by the BID-REASONING / WRITE-REASONING
    postcheck to enforce branch isolation: a persona's spawn must only touch
    `refs/heads/persona/<id>/...` branches. Any modification to other personas'
    branches, to main, or to any other ref → forfeit.

    Args:
        persona_id: the persona that owns this spawn
        pre_refs / post_refs: ref snapshots from `capture_refs()` taken before
            and after the spawn

    Returns:
        {ok: True, modified_refs: [refs that changed], allowed: True}
        {ok: False, failure: "branch-isolation-violated",
         modified_refs: [...], forbidden_refs: [refs outside this persona's namespace]}
    """
    modified: list[str] = []
    for ref, post_sha in post_refs.items():
        pre_sha = pre_refs.get(ref)
        if pre_sha != post_sha:
            modified.append(ref)
    # Also catch deleted refs (present in pre, absent in post)
    for ref in pre_refs:
        if ref not in post_refs:
            modified.append(ref)

    allowed_prefix = f"refs/heads/persona/{persona_id}/"
    forbidden = [r for r in modified if not r.startswith(allowed_prefix)]

    if forbidden:
        return {
            "ok": False,
            "failure": "branch-isolation-violated",
            "modified_refs": modified,
            "forbidden_refs": forbidden,
        }
    return {"ok": True, "modified_refs": modified}


def write_postcheck(persona_id: str, epoch: int) -> dict:
    """Postcheck a WRITE-mode spawn. Returns {ok: bool, failure?: str, detail?: str}."""
    cfg = read_config()
    sb_path = sketchboard_abs_path(cfg)
    sb_rel = sb_path.relative_to(repo_root()).as_posix()

    changed = _git_changed_files()
    if not changed:
        return {"ok": False, "failure": "no-diff", "detail": "persona produced no changes"}
    if changed != [sb_rel]:
        return {
            "ok": False,
            "failure": "wrong-files-changed",
            "detail": f"expected only {sb_rel}; got: {changed}",
        }

    # Read prev (HEAD) and new (worktree) content.
    prev = _git_show_prev(sb_path)
    new = sb_path.read_text()

    # Resolve persona display name from the agent file (audit #4: no longer
    # title-case-from-id).
    agents_dir = repo_root() / "agents"
    display = id_to_display_name_from_file(persona_id, agents_dir)
    if display is None:
        return {
            "ok": False,
            "failure": "persona-file-missing",
            "detail": f"agents/{persona_id}.md not found",
        }

    ok, reason = verify_block_in_epoch(new, prev, epoch, display)
    if not ok:
        return {"ok": False, "failure": reason.split(":")[0], "detail": reason}
    return {"ok": True}


def bid_postcheck(stdout: str) -> dict:
    """Postcheck a BID-mode spawn (audit #5: was skill-side only, now enforced
    consistently here too).

    Returns {ok: True, bid: float, reason: str} on success, otherwise
    {ok: False, failure: <code>, detail: <message>, bid: 0.0, reason: <fallback>}.

    NOTE: file-touch verification was removed from this function. BID spawns
    run inside the persona's own Agent context, not the orchestrator's
    working tree, so `git diff` from here doesn't reflect what the persona
    did. File-touch violations during BID must be caught via tool restrictions
    on the persona or by inspecting the diff at the orchestrator after the
    spawn. Here we validate the part we can actually inspect: stdout shape.

    Stdout must contain a single JSON object somewhere; we accept prose
    before/after but log it as a soft violation. Strict mode would reject any
    surrounding prose, but v0.1 stays lenient to match observed persona behavior.
    """
    stripped = stdout.strip()
    candidate = stripped
    # If wrapped in fences, strip them.
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            candidate = "\n".join(lines[1:-1])

    # Find the LAST JSON object in stdout (handles "prose, then JSON" case).
    last_open = candidate.rfind("{")
    last_close = candidate.rfind("}")
    if last_open == -1 or last_close == -1 or last_close < last_open:
        return {
            "ok": False,
            "failure": "no-json-found",
            "detail": "no JSON object in stdout",
            "bid": 0.0,
            "reason": "<no-json>",
        }
    json_str = candidate[last_open : last_close + 1]
    try:
        obj = json.loads(json_str)
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "failure": "json-parse-error",
            "detail": str(e),
            "bid": 0.0,
            "reason": "<parse-failure>",
        }

    if "bid" not in obj:
        return {
            "ok": False,
            "failure": "missing-bid-field",
            "detail": "JSON has no 'bid' field",
            "bid": 0.0,
            "reason": "<missing-bid>",
        }
    try:
        bid = float(obj["bid"])
    except (TypeError, ValueError):
        return {
            "ok": False,
            "failure": "non-numeric-bid",
            "detail": f"bid={obj.get('bid')!r}",
            "bid": 0.0,
            "reason": "<non-numeric>",
        }
    # Clamp to [0, 1] rather than reject — keeps the orchestrator robust.
    bid = max(0.0, min(1.0, bid))
    reason = str(obj.get("reason", ""))[:200]

    # Soft violation: prose surrounding JSON
    has_prose = (
        last_open > 0 and candidate[:last_open].strip()
    ) or (last_close + 1 < len(candidate) and candidate[last_close + 1 :].strip())

    result = {"ok": True, "bid": bid, "reason": reason}
    if has_prose:
        result["contract_violation"] = "prose-around-json"
    return result
