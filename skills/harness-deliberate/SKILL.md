---
name: harness-deliberate
description: "HAR: Multi-persona deliberation on a shared Sketchboard.md document with chair-ratified epoch boundaries (Preview, v0.1). Trigger: deliberate, deliberation, persona discussion, sketchboard, epoch review. Do NOT load for: code planning (use harness-plan), code review (use harness-review), task implementation (use harness-work)."
description-en: "HAR: Multi-persona deliberation on a shared Sketchboard.md document with chair-ratified epoch boundaries (Preview, v0.1). Trigger: deliberate, deliberation, persona discussion, sketchboard, epoch review. Do NOT load for: code planning (use harness-plan), code review (use harness-review), task implementation (use harness-work)."
description-ja: "HAR: 複数ペルソナによる Sketchboard.md 上の議論と人間チェアによる epoch ratification (Preview, v0.1)。トリガー: deliberate、議論、ペルソナ、sketchboard、epoch review。コードのプランニング・レビュー・実装には使わない。"
kind: workflow
purpose: "Run multi-persona deliberation epochs on a shared Sketchboard.md and surface contested sections to a human chair"
trigger: "deliberate, deliberation, persona discussion, sketchboard, epoch review"
shape: workflow
role: orchestrator
pair: none
owner: harness-core
since: "2026-05-09"
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Task"]
argument-hint: "[init <question>|run|review|ratify|status]"
user-invocable: true
effort: medium
preview: true
---

# Harness Deliberate (Preview, v0.1)

> Status: **Preview**. Opt-in via `harness.toml [deliberation].enabled = true`. The orchestration model and the persona contract may change before v1.0.

Run multi-persona deliberation on a shared `Sketchboard.md` document. Personas bid for commit slots within a fixed epoch budget; the highest bid wins each slot and writes a single block. The human chair reviews the epoch diff at the boundary and ratifies, requests revisions, or edits-and-ratifies.

This skill is **separate** from the existing `harness-plan` (task tracking on `Plans.md`) and `harness-review` (code review). Sketchboard.md is the deliberation HEAD; Plans.md is untouched.

## Quick Reference

| User input | Subcommand | Action |
|------------|------------|--------|
| `/harness-deliberate init "<question>"` | `init` | Generate `Sketchboard.md` from template, set epoch 1 OPEN |
| `/harness-deliberate run` | `run` | Run the bidding loop until budget exhausted or all-abstain |
| `/harness-deliberate review` | `review` | Produce the chair's review report for the just-closed epoch |
| `/harness-deliberate ratify` | `ratify` | Move the `ratified` ref forward, open the next epoch |
| `/harness-deliberate status` | `status` | Show current epoch state from `.claude/state/deliberation/epoch.json` |

## How it differs from existing harness skills

| Concept | This skill | Existing skill | Why separate |
|---|---|---|---|
| Shared artifact | `Sketchboard.md` | `Plans.md` | Plans tracks tasks; Sketchboard tracks the deliberation itself |
| Communication model | State observation (read-then-write) | Task assignment | Personas talk through the document, not via routed messages |
| Review type | Sketchboard content diff + contested sections | Code diff + 4 perspectives | Chair reviews positions, not code quality |
| Conflict handling | Surface to human at epoch boundary | Resolved by Lead during work | Chair deliberately decides what's canonical |

## Subcommand details

### `init <question>` — open a deliberation

Creates `Sketchboard.md` from `templates/Sketchboard.md.tmpl`, substituting:

- `{{QUESTION}}` ← the chair's framing question (the argument to `init`)
- `{{FRAME}}` ← left blank for chair to fill before running epoch 1
- `{{PERSONAS_LIST}}` ← from `harness.toml [deliberation].personas`

Writes initial `.claude/state/deliberation/epoch.json` with `state: OPEN, epoch: 1`.

**Preconditions**:
- `[deliberation].enabled = true` in `harness.toml`
- `Sketchboard.md` does not already exist (use `git rm Sketchboard.md` to start fresh)
- Repo is git-clean (no uncommitted changes — the orchestrator will be committing)

**Output**: confirmation + suggestion to fill in `## Frame` before running `run`.

### `run` — execute the bidding loop

For details see [references/bidding.md](${CLAUDE_SKILL_DIR}/references/bidding.md).

Per-slot loop (until budget exhausted or all-abstain):
1. Spawn each persona in BID mode in parallel via `scripts/deliberate/collect-bids.sh`.
2. Tally bids; if all are 0, close the epoch with reason `all-abstain`.
3. Pick the winner (highest bid, ties broken by `bid_tiebreaker` config).
4. Spawn the winner in WRITE mode via `scripts/deliberate/spawn-winner.sh`.
5. Postcheck the diff. If it passes: `git commit -m "epoch-N slot-S: <persona-id>"`. If it fails: forfeit the slot (no commit, slot counter does not advance).
6. Append every bid to `.claude/state/deliberation/epoch-<N>-bids.jsonl`.

At loop end:
- `git tag epoch-<N>-unratified`
- Update `epoch.json` with `state: REVIEW`, `closed_at`, `close_reason`.

**Stop conditions** (refuse to run):
- `Sketchboard.md` is missing (call `init` first).
- `epoch.json` is in state `REVIEW` or `RATIFIED` (call `review` then `ratify` first).
- Working tree is dirty.

### `review` — chair's epoch review

For details see [references/epoch-review.md](${CLAUDE_SKILL_DIR}/references/epoch-review.md).

Produces a Markdown report containing:

1. **Diff summary**: `git diff <ratified>..HEAD -- Sketchboard.md` annotated with persona attribution per block.
2. **Bid distribution**: per slot, which personas bid what; who won; who abstained and why.
3. **Contested sections**: detected by `scripts/deliberate/detect-contested.sh` heuristic (see [references/epoch-review.md](${CLAUDE_SKILL_DIR}/references/epoch-review.md) for known limits — heuristic produces both false positives and false negatives, regression-tested in `tests/test-sketchboard-conflict-detection.sh`). Auto-populates `## Open Conflicts` section in Sketchboard.md.
4. **Abstentions**: personas who bid 0 across every slot of the epoch with their reasons.
5. **Chair actions**: ratify | request-revision <persona-id> | edit-and-ratify.

This deliberately does **not** invoke `agents/reviewer.md` or `harness-review` — those review code, not deliberation content.

### `ratify` — promote the unratified epoch to canonical

Moves the `ratified` git ref forward to `epoch-<N>-unratified`, opens epoch N+1 (state: OPEN), clears `## Open Conflicts` (the unresolved ones get echoed into the new epoch's frame as a chair-noted carry-over).

If the chair wants to reject the epoch instead, they edit `Sketchboard.md` directly first (un-doing or modifying persona blocks) and call `ratify`. There is no separate `reject` subcommand — direct edit + ratify is the workflow.

### `status` — inspect current state

Reads `.claude/state/deliberation/epoch.json` and prints:
- Current epoch number and state (`OPEN | COLLECTING | REVIEW | RATIFIED`)
- Slots used / budget
- Personas and last-bid scores from the most recent slot
- Last ratified commit + tag

## Persona contract

See [`agents/personas/_persona-contract.md`](../../agents/personas/_persona-contract.md) and [references/persona-modes.md](${CLAUDE_SKILL_DIR}/references/persona-modes.md).

Two modes per persona spawn:
- **BID** (read-only, parallel-safe) → returns `{"bid": float, "reason": string}`
- **WRITE** (one persona per slot) → appends one block to `Sketchboard.md`

## Configuration

`harness.toml [deliberation]` block:

```toml
[deliberation]
enabled = false                          # opt-in
sketchboard_path = "Sketchboard.md"
epoch_state_path = ".claude/state/deliberation/"
epoch_commit_budget = 5
bid_tiebreaker = "declaration-order"     # or "random"
personas = ["scaling-optimist", "architecture-skeptic", "bias-auditor"]
```

## Out of scope (v0.1)

- Per-persona git branches (v0.2 will add eavesdrop / 1-to-1 talk via this)
- CRDT / Yjs (v0.3)
- LLM-based stance classifier for contested-section detection (v0.2)
- Dominance scoring across epochs / probabilistic relational graph (v0.3)
- Worktree isolation per persona (v0.2; v0.1 = sequential turns on shared checkout)

## Related skills

- `harness-plan` — plan tasks (separate artifact, untouched)
- `harness-work` — implement tasks
- `harness-review` — code review (NOT used for epoch review)
- `harness-setup` — project init

## Tests

- `tests/test-deliberation-personas.sh` — 3-state coverage (Healthy / NotConfigured / Corrupted)
- `tests/test-deliberation-bidding.sh` — bidding mechanics + tiebreak + close conditions
- `tests/test-sketchboard-conflict-detection.sh` — contested-section detection on adversarial fixtures
