#!/usr/bin/env python3
"""Build BID/WRITE spawn manifests + run postchecks.

v0.1.2 — added two-turn (reasoning + extraction) manifests per the
per-persona-branch model. The legacy single-turn `manifest` subcommand stays
for tests + sequential mode fallback.

Subcommands:
  reasoning-manifest <persona> <epoch> <slot> <mode> [--bid-history <jsonl>] [--eavesdrop <json>]
      Build the manifest for a persona's REASONING turn on its worktree.
      Output includes worktree_path, branch, expected_commit_msg.
      mode = "bid" or "write".

  extraction-manifest <persona> <epoch> <slot> <mode>
      Build the manifest for the EXTRACTION turn. Reads the persona's
      reasoning branch HEAD content and embeds it in a fixed extraction
      template. Output includes model_config.temperature.

  postcheck <persona> <epoch>
      Validate the WRITE-mode worktree diff against the section-boundary
      contract. Returns {ok, failure?, detail?}.

  validate-bids
      (stdin) Read [{persona, stdout}, ...]; emit validated bid records.
      Legacy path for tests + sequential mode without two-turn extraction.

  manifest <persona> <epoch> <slot> <bid> <reason>
      Legacy single-turn WRITE manifest. Kept for backward compat with
      existing tests; new flow should use reasoning-manifest + extraction-manifest.

Audit fixes (v0.1.1):
  #1  FORBIDDEN_TOUCHED → real section-boundary parsing
  #4  persona display name read from agents/<id>.md
  #5  BID validation lives here (extraction is the new trust boundary in v0.1.2)
  #11 argv/stdin only; subprocess never shell=True
  #13 diff position verified via verify_block_in_epoch
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.config import read_config, repo_root  # noqa: E402
from lib.postcheck import bid_postcheck, write_postcheck  # noqa: E402
from lib.state import (  # noqa: E402
    reasoning_branch_name,
    reasoning_commit_message,
    worktree_path,
)


_TIGHT = (",", ":")


def err(payload: dict, code: int = 1) -> None:
    print(json.dumps(payload, separators=_TIGHT))
    sys.exit(code)


# ---------------------------------------------------------------------------
# v0.1.2: two-turn manifests (reasoning + extraction)
# ---------------------------------------------------------------------------


_BID_REASONING_TEMPLATE = """\
mode={mode_upper}-REASONING
epoch={epoch}
slot={slot}
sketchboard_path={sb_abs}
worktree_path={worktree_path}
reasoning_branch={branch}

You are reasoning on your own git branch ({branch}) inside a dedicated worktree.

WORKING DIRECTORY: {worktree_path}
You may read {sb_abs} on main. You may NOT read or write any other persona's branch.

STEP 1 — Read the sketchboard:
  Open {sb_abs} and read the full deliberation so far.

STEP 2 — Reason freely about your relevance / contribution to this slot.
  Write your reasoning as free-form Markdown into a file at:
      {worktree_path}/.claude/state/deliberation/branches/{persona}/reasoning.md
  No JSON. No format constraint on the body.

STEP 3 — End with a clear bid intent signal so the extraction step can read your stance:
  Finish your reasoning with one of these phrases (or close variants):
    - "I have a strong contribution here" (high bid, ~0.8-1.0)
    - "I have something to add" (moderate bid, ~0.4-0.7)
    - "I have little to add this slot" (low bid, ~0.1-0.3)
    - "I have nothing to add" (abstain, bid 0)

STEP 4 — Stage and notify completion.
  Run: git add .claude/state/deliberation/branches/{persona}/reasoning.md
  Then output one line confirming "REASONING-COMPLETE" so the orchestrator commits.

DO NOT commit yourself. The orchestrator will commit with the fixed structured message.
DO NOT produce JSON. That happens in the extraction step.

{bid_memory_block}
{eavesdrop_block}
"""

_WRITE_REASONING_TEMPLATE = """\
mode=WRITE-REASONING
epoch={epoch}
slot={slot}
sketchboard_path={sb_abs}
worktree_path={worktree_path}
reasoning_branch={branch}
your_winning_bid={bid}
your_winning_reason={reason}

You won this slot's bid. Now reason freely about WHAT to contribute.

WORKING DIRECTORY: {worktree_path}
You may read {sb_abs}. You may NOT read or write any other persona's branch.

STEP 1 — Re-read the sketchboard. State may have shifted since your bid.

STEP 2 — Reason freely as Markdown into:
      {worktree_path}/.claude/state/deliberation/branches/{persona}/reasoning.md
  - Identify the specific sketchboard line(s) you want to engage with.
  - Decide your stance, your evidence, your concession (if any).
  - Plan the block you'll contribute. Free-form. No format constraint on the body.

STEP 3 — End with the intended block in prose, prefixed by:
  "Here is the contribution I want to make:"
  followed by your draft block content. The extraction step will format it
  into the canonical `## <Display Name>:` shape with blockquote.

STEP 4 — Stage and notify.
  Run: git add .claude/state/deliberation/branches/{persona}/reasoning.md
  Output one line "REASONING-COMPLETE".

DO NOT commit yourself. DO NOT produce the formatted block yet. Reasoning step only.
"""

_BID_EXTRACTION_TEMPLATE = """\
You are extracting a structured bid from a persona's reasoning commit.

Persona: {persona_display}
Epoch: {epoch}, Slot: {slot}

The reasoning content below was produced freely by the persona. Your job is
to summarize the persona's bid intent and confidence into a strict JSON line.

Reasoning content:
---
{reasoning_content}
---

Output EXACTLY one JSON line, no prose before or after, no markdown fences:
{{"bid": <float 0.0..1.0>, "reason": "<≤140 chars summary of why>"}}

Rules:
  - Use the literal key names "bid" and "reason". No alternatives.
  - bid: float in [0.0, 1.0]. Map the persona's stated intent:
      "strong contribution" → ~0.8-1.0
      "something to add"     → ~0.4-0.7
      "little to add"        → ~0.1-0.3
      "nothing to add" / abstain → 0.0
  - reason: short summary of the persona's main argument for bidding this level.
  - Do not generate new reasoning. Summarize what's there.
  - If the reasoning does not contain a clear bid signal, default to bid=0.0 with reason="<no clear bid signal>".
"""

_WRITE_EXTRACTION_TEMPLATE = """\
You are extracting a formatted Sketchboard block from a persona's WRITE reasoning.

Persona: {persona_display}
Persona ID: {persona_id}
Epoch: {epoch}, Slot: {slot}
Sketchboard path: {sb_abs}

The reasoning content below was produced freely. Your job is to format the
persona's intended contribution into the canonical block shape AND apply it
directly to the sketchboard file on main.

Reasoning content:
---
{reasoning_content}
---

YOUR TASK:
1. Use the Edit tool to append exactly ONE block under the current `## Epoch {epoch}` section in {sb_abs}, BEFORE the next top-level heading (`## Open Conflicts` or another `## X` section).

2. Block shape (REQUIRED):
   ```
   ## {persona_display}:

   > <one-line blockquote of an actual line from the sketchboard>

   <body — formatted from the persona's reasoning>
   ```

3. The blockquote MUST be a line that actually exists in the sketchboard right now (read the file first to verify). Pick whichever line the persona engaged with in their reasoning. The framing question is always a safe choice.

4. The body is your formatted version of the persona's reasoning. Preserve their voice, claims, and concessions. Do NOT add new reasoning or change their stance.

5. CRITICAL constraints (postcheck will revert if violated):
   - Edit ONLY {sb_abs}. No other file.
   - Additive only — no deletions, no edits to existing lines.
   - Block lands INSIDE `## Epoch {epoch}` section.
   - Heading exactly `## {persona_display}:` with trailing colon.
   - At least one `>` blockquote line of a real sketchboard line.

After editing, confirm in ONE sentence what you wrote. Do not produce JSON output.
"""


def _build_bid_memory_block(bid_history: list[dict]) -> str:
    if not bid_history:
        return ""
    lines = ["Your prior bids this epoch:"]
    for h in bid_history:
        slot = h.get("slot", "?")
        bid_v = h.get("bid", 0.0)
        reason = (h.get("reason") or "").replace("\n", " ")[:100]
        won = h.get("won", False)
        lines.append(f"  slot {slot}: bid={bid_v:.2f}, won={won}, reason=\"{reason}\"")
    return "\n" + "\n".join(lines) + "\n"


def _build_eavesdrop_block(eavesdrop_excerpts: list[dict]) -> str:
    if not eavesdrop_excerpts:
        return ""
    out = ["\n(Eavesdropped excerpts — non-binding overheard reasoning):"]
    for e in eavesdrop_excerpts:
        from_p = e.get("from_persona", "?")
        excerpt = e.get("excerpt", "").replace("\n", " ")[:300]
        out.append(f"  from {from_p}: {excerpt}")
    return "\n".join(out) + "\n"


def cmd_reasoning_manifest(args: list[str]) -> None:
    """Usage: reasoning-manifest <persona> <epoch> <slot> <mode> [--bid-history <json>] [--eavesdrop <json>] [--bid <f> --reason <s>]

    --bid-history and --eavesdrop accept JSON strings (use shell -- separator carefully).
    --bid + --reason are required when mode=write (passed to the WRITE template).
    """
    if len(args) < 4:
        err({"error": "usage: reasoning-manifest <persona> <epoch> <slot> <mode> [flags]"}, 2)
    persona, epoch_s, slot_s, mode = args[0], args[1], args[2], args[3]
    rest = args[4:]

    bid_history: list[dict] = []
    eavesdrop: list[dict] = []
    bid_value: str = ""
    bid_reason: str = ""
    i = 0
    while i < len(rest):
        flag = rest[i]
        if flag == "--bid-history":
            try:
                bid_history = json.loads(rest[i + 1])
            except (IndexError, json.JSONDecodeError):
                err({"error": "bad-bid-history"}, 2)
            i += 2
        elif flag == "--eavesdrop":
            try:
                eavesdrop = json.loads(rest[i + 1])
            except (IndexError, json.JSONDecodeError):
                err({"error": "bad-eavesdrop"}, 2)
            i += 2
        elif flag == "--bid":
            bid_value = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        elif flag == "--reason":
            bid_reason = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        else:
            err({"error": f"unknown-flag:{flag}"}, 2)

    if mode not in ("bid", "write"):
        err({"error": "mode-must-be-bid-or-write", "got": mode}, 2)

    cfg = read_config()
    persona_file = repo_root() / "agents" / f"{persona}.md"
    if not persona_file.exists():
        err({"error": "persona-file-missing", "persona": persona})

    epoch = int(epoch_s)
    slot = int(slot_s)
    sb_abs = (repo_root() / cfg.sketchboard_path).resolve()
    wt_path = worktree_path(persona, epoch, slot)
    branch = reasoning_branch_name(persona, epoch, slot, mode)

    if mode == "bid":
        prompt = _BID_REASONING_TEMPLATE.format(
            mode_upper="BID",
            epoch=epoch,
            slot=slot,
            sb_abs=sb_abs,
            worktree_path=wt_path,
            branch=branch,
            persona=persona,
            bid_memory_block=_build_bid_memory_block(bid_history),
            eavesdrop_block=_build_eavesdrop_block(eavesdrop),
        )
    else:  # write
        if not bid_value:
            err({"error": "write-mode-requires-bid"}, 2)
        prompt = _WRITE_REASONING_TEMPLATE.format(
            epoch=epoch,
            slot=slot,
            sb_abs=sb_abs,
            worktree_path=wt_path,
            branch=branch,
            persona=persona,
            bid=bid_value,
            reason=bid_reason,
        )

    print(json.dumps({
        "turn": "reasoning",
        "mode": mode,
        "subagent_type": persona,
        "prompt": prompt,
        "worktree_path": str(wt_path),
        "branch": branch,
        "expected_commit_msg": reasoning_commit_message(persona, epoch, slot, mode),
    }, separators=_TIGHT))


def _get_persona_display(persona_id: str) -> str:
    """Read display name from the persona file's first `# X` heading, fall back to title-case."""
    from lib.sketchboard import id_to_display_name_from_file
    display = id_to_display_name_from_file(persona_id, repo_root() / "agents")
    if display is None:
        display = " ".join(w.capitalize() for w in persona_id.split("-"))
    return display


def _read_reasoning_content(persona: str, epoch: int, slot: int, mode: str) -> str:
    """Read the reasoning artifact from the persona's branch HEAD.

    Looks for the file `.claude/state/deliberation/branches/<persona>/reasoning.md`
    at the branch tip. Returns its content (empty string if absent).
    """
    branch = reasoning_branch_name(persona, epoch, slot, mode)
    rel_path = f".claude/state/deliberation/branches/{persona}/reasoning.md"
    try:
        result = subprocess.run(
            ["git", "show", f"{branch}:{rel_path}"],
            cwd=str(repo_root()),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        # No reasoning file — fall back to commit message body
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%B", branch],
                cwd=str(repo_root()),
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return ""


def cmd_extraction_manifest(args: list[str]) -> None:
    """Usage: extraction-manifest <persona> <epoch> <slot> <mode>

    Reads the persona's reasoning branch HEAD and builds the extraction prompt.
    For mode=bid: extraction emits JSON {"bid": float, "reason": str}.
    For mode=write: extraction edits Sketchboard.md to apply the formatted block.
    """
    if len(args) < 4:
        err({"error": "usage: extraction-manifest <persona> <epoch> <slot> <mode>"}, 2)
    persona, epoch_s, slot_s, mode = args[0], args[1], args[2], args[3]

    if mode not in ("bid", "write"):
        err({"error": "mode-must-be-bid-or-write", "got": mode}, 2)

    cfg = read_config()
    epoch = int(epoch_s)
    slot = int(slot_s)
    display = _get_persona_display(persona)
    reasoning_content = _read_reasoning_content(persona, epoch, slot, mode)
    sb_abs = (repo_root() / cfg.sketchboard_path).resolve()

    if mode == "bid":
        prompt = _BID_EXTRACTION_TEMPLATE.format(
            persona_display=display,
            epoch=epoch,
            slot=slot,
            reasoning_content=reasoning_content,
        )
    else:
        prompt = _WRITE_EXTRACTION_TEMPLATE.format(
            persona_display=display,
            persona_id=persona,
            epoch=epoch,
            slot=slot,
            sb_abs=sb_abs,
            reasoning_content=reasoning_content,
        )

    print(json.dumps({
        "turn": "extraction",
        "mode": mode,
        "subagent_type": "general-purpose",  # extraction is mechanical reformatting
        "prompt": prompt,
        "model_config": {"temperature": cfg.extraction_temperature},
        "persona_display": display,
    }, separators=_TIGHT))


# ---------------------------------------------------------------------------
# Legacy single-turn manifest (kept for backward compat + sequential mode tests)
# ---------------------------------------------------------------------------


def cmd_manifest(args: list[str]) -> None:
    if len(args) < 4:
        err({"error": "usage: manifest <persona> <epoch> <slot> <bid> [reason]"}, 2)
    persona, epoch_s, slot_s, bid_s, *rest = args
    reason = " ".join(rest) if rest else ""

    cfg = read_config()
    persona_file = repo_root() / "agents" / f"{persona}.md"
    if not persona_file.exists():
        err({"error": "persona-file-missing", "persona": persona})

    sb_abs = (repo_root() / cfg.sketchboard_path).resolve()

    contract = (
        "REQUIRED OUTPUT (WRITE mode):\n"
        f"  - Append exactly ONE block under '## Epoch {epoch_s}' in {sb_abs}, BEFORE the next top-level\n"
        "    heading (## Open Conflicts or another ## section).\n"
        "  - Block heading must be exactly '## <Your Persona Display Name>:' (with trailing colon).\n"
        "  - Block must contain at least one '>' blockquote of an earlier sketchboard line.\n"
        "  - Edit ONLY the sketchboard file.\n"
        "  - Diff must be purely additive.\n"
    )

    prompt = (
        "mode=WRITE\n"
        f"epoch={epoch_s}\n"
        f"slot={slot_s}\n"
        f"sketchboard_path={sb_abs}\n"
        f"your_winning_bid={bid_s}\n"
        f"your_winning_reason={reason}\n\n"
        + contract
    )
    print(json.dumps({
        "subagent_type": persona,
        "prompt": prompt,
        "sketchboard_path": cfg.sketchboard_path,
    }, separators=_TIGHT))


# ---------------------------------------------------------------------------
# Postcheck + validation
# ---------------------------------------------------------------------------


def cmd_postcheck(args: list[str]) -> None:
    if len(args) < 2:
        err({"error": "usage: postcheck <persona> <epoch>"}, 2)
    persona, epoch_s = args[0], args[1]
    try:
        epoch = int(epoch_s)
    except ValueError:
        err({"error": "epoch-must-be-int"}, 2)
    result = write_postcheck(persona, epoch)
    print(json.dumps(result, separators=_TIGHT))
    sys.exit(0)


def cmd_bid_postcheck(_args: list[str]) -> None:
    stdout = sys.stdin.read()
    result = bid_postcheck(stdout)
    print(json.dumps(result, separators=_TIGHT))
    sys.exit(0)


def cmd_validate_bids(_args: list[str]) -> None:
    """Legacy validate-bids path. Two-turn flow uses extraction-manifest output
    directly; this stays for backward compat with tests + sequential mode."""
    payload = sys.stdin.read()
    try:
        raw_bids = json.loads(payload)
    except json.JSONDecodeError as e:
        err({"error": "bad-input-json", "detail": str(e)}, 2)
    if not isinstance(raw_bids, list):
        err({"error": "input-not-array"}, 2)

    out = []
    for entry in raw_bids:
        persona = entry.get("persona", "<unknown>")
        stdout = entry.get("stdout", "")
        result = bid_postcheck(stdout)
        rec = {
            "persona": persona,
            "bid": float(result.get("bid", 0.0)),
            "reason": result.get("reason", ""),
        }
        violations = []
        if not result.get("ok", False):
            violations.append(result.get("failure", "unknown"))
        if "contract_violation" in result:
            violations.append(result["contract_violation"])
        if violations:
            rec["violations"] = violations
        out.append(rec)
    print(json.dumps(out, separators=_TIGHT))
    sys.exit(0)


COMMANDS = {
    # v0.1.2 two-turn flow
    "reasoning-manifest": cmd_reasoning_manifest,
    "extraction-manifest": cmd_extraction_manifest,
    # Legacy + postchecks
    "manifest": cmd_manifest,
    "postcheck": cmd_postcheck,
    "bid-postcheck": cmd_bid_postcheck,
    "validate-bids": cmd_validate_bids,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        err({
            "error": (
                "usage: spawn_winner.py "
                "(reasoning-manifest|extraction-manifest|manifest|postcheck|bid-postcheck|validate-bids) ..."
            )
        }, 2)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
