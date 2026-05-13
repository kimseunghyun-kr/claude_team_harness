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

    contract = (
        "REQUIRED OUTPUT (WRITE mode):\n"
        f"  - Append exactly ONE block under '## Epoch {epoch_s}' in {sb_abs}, BEFORE the next top-level\n"
        "    heading (## Open Conflicts or another ## section).\n"
        "  - Block heading must be exactly '## <Your Persona Display Name>:' (with trailing colon).\n"
        "  - Block must contain at least one '>' blockquote of an earlier sketchboard line.\n"
        "  - Edit ONLY the sketchboard file. Do NOT modify your own persona file, any other agent file,\n"
        "    or any file under .claude/. Postcheck will revert and forfeit your slot if you do.\n"
        "  - Diff must be purely additive: no deletions, no edits to other persona blocks, no edits to\n"
        "    ## Ratified Decisions or ## Open Conflicts.\n"
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


def cmd_validate_bids(_args: list[str]) -> None:
    """Read a JSON array of {persona, stdout} from stdin, run bid_postcheck on
    each, and emit the validated bid array suitable for `tally`.

    Use this as the trust boundary between persona Task outputs (potentially
    malformed) and orchestrate-epoch's tally (which assumes valid bid records).

    Input:  [{"persona": "id", "stdout": "raw persona output"}, ...]
    Output: [{"persona": "id", "bid": float, "reason": str, "violations": [...]}, ...]

    A persona that returned malformed output gets bid=0.0 with the failure code
    in `violations` so the bid log records the contract violation.
    """
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
    "manifest": cmd_manifest,
    "postcheck": cmd_postcheck,
    "bid-postcheck": cmd_bid_postcheck,
    "validate-bids": cmd_validate_bids,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        err({"error": "usage: spawn_winner.py (manifest|postcheck|bid-postcheck) ..."}, 2)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
