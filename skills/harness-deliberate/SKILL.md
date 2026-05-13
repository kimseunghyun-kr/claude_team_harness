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

> Status: **Preview**. Opt-in via `harness.toml [deliberation].enabled = true`. v0.1 wiring (this version): personas live at `agents/<id>.md` flat root (Agent-tool-discoverable), skill dispatch executes `scripts/deliberate/orchestrate-epoch.sh`, slot loop is autonomous within `run`.

Run multi-persona deliberation on a shared `Sketchboard.md` document. Personas bid for commit slots within a fixed epoch budget; the highest bid wins each slot and writes a single block. The human chair reviews the epoch diff at the boundary and ratifies, requests revisions, or edits-and-ratifies.

This skill is **separate** from `harness-plan` (Plans.md task tracking) and `harness-review` (code review).

## Quick Reference

| User input | Subcommand | Action |
|------------|------------|--------|
| `/harness-deliberate init "<question>"` | `init` | Create `Sketchboard.md` from template + begin epoch 1 |
| `/harness-deliberate run` | `run` | **Autonomous**: run the bidding loop until budget exhausted or all-abstain |
| `/harness-deliberate review` | `review` | Produce the chair's review report |
| `/harness-deliberate ratify` | `ratify` | Advance `ratified` ref + open the next epoch |
| `/harness-deliberate status` | `status` | Print epoch.json state |

## Procedure — what the model executes when invoked

The skill is a recipe; the model is the runtime. Each subcommand below is an executable procedure with bash invocations and Task-tool spawns.

### `init <question>`

```
1. Run: bash scripts/deliberate/orchestrate-epoch.sh init "<question>"
2. If exit 0: print the "{\"ok\":true, ...}" JSON to the user with a one-line summary.
3. If exit 1: surface the error JSON (sketchboard-exists / dirty-tree / template-missing).
```

The orchestrator script handles: precondition checks (clean tree, no existing Sketchboard.md), template substitution, first commit, epoch state initialization.

### `run` — **autonomous slot loop**

```
1. Verify state:
   - Run: bash scripts/deliberate/orchestrate-epoch.sh status
   - If state != "COLLECTING": refuse with the error JSON. Stop.

2. Read current state:
   - epoch = status.epoch
   - budget = status.budget
   - personas = status.personas

3. AUTONOMOUS LOOP — for slot in 1..budget:

   3a. Build the BID manifest:
       Run: bash scripts/deliberate/collect-bids.sh <epoch> <slot>
       This returns { "spawns": [ {subagent_type, prompt}, ... ] }.
       The prompt now includes an inline contract reminder (bid range, JSON
       shape, reason key name) — v0.1.1 fix #D.

   3b. Parallel BID spawns:
       For each spawn in manifest.spawns, call the Task tool with:
         subagent_type = spawn.subagent_type   (resolves to agents/<id>.md)
         description   = "BID <persona> slot <slot>"
         prompt        = spawn.prompt
       Make ALL spawn calls in a single tool-use block so they run in parallel.

   3c. Collect raw stdouts and validate via spawn_winner.py:
       Build a JSON array of {persona, stdout} pairs from the Task results,
       then pipe to:
         bash scripts/deliberate/spawn-winner.sh validate-bids
       The validator runs bid_postcheck on each output: parses JSON, clamps
       bids to [0.0, 1.0], records contract violations (out-of-range, wrong
       JSON key, prose-around-JSON, missing bid field). Output is a clean
       bids array that the tally script can trust.

       DO NOT hand-curate or hand-clamp bids. The bid log records the
       persona's actual output via this validator; if you fix things by hand,
       the contract-violation signal is lost and the chair can't see which
       personas are off-contract.

   3d. Tally:
       Run: <validated-bids-array> | bash scripts/deliberate/orchestrate-epoch.sh tally <epoch> <slot>

   3e. Branch on tally result:
       - {"action":"close","reason":"all-abstain"} → break the loop, go to step 4.
       - {"action":"spawn","persona":"<id>","bid":<n>,"reason":"<s>"} → continue 3f.

   3f. Build WRITE manifest:
       Run: bash scripts/deliberate/spawn-winner.sh manifest <persona> <epoch> <slot> <bid> "<reason>"
       Returns: {"subagent_type":"<id>","prompt":"<WRITE-mode prompt>"}

   3g. Spawn winner via Task tool with the WRITE manifest.

   3h. Postcheck + commit:
       Run: bash scripts/deliberate/orchestrate-epoch.sh commit-or-forfeit <epoch> <slot> <persona>
       If {"committed":true}: continue to next slot.
       If {"committed":false}: log forfeit, continue to next slot (counter still advances).

4. Close the epoch:
   - If loop broke on all-abstain:
     Run: bash scripts/deliberate/orchestrate-epoch.sh close <epoch> all-abstain
   - Else (budget exhausted naturally):
     Run: bash scripts/deliberate/orchestrate-epoch.sh close <epoch> budget-exhausted

5. Print a one-line summary: "Epoch <N> closed (reason). Run /harness-deliberate review."
```

**Autonomy property**: between step 1 and step 5, the model executes everything without user input. No interactive prompts, no confirmation between slots, no "should I continue?" gates. The user types `/harness-deliberate run` once and the loop runs to completion.

### `review`

```
1. Verify state == REVIEW. If not, refuse.

2. Run the contested-section detector:
   bash scripts/deliberate/detect-contested.sh Sketchboard.md --epoch <epoch>

3. Read the bid log:
   .claude/state/deliberation/epoch-<N>-bids.jsonl

4. Print a Markdown report with sections:
   - Bid distribution per slot (from bid log)
   - Slot count per persona (flag if any persona has 3+ → dominance trigger)
   - Contested sections (from step 2; note v0.1 known limits: false positive on
     "however, I agree", false negative on semantic contradiction without
     trigger keywords — see tests/test-sketchboard-conflict-detection.sh)
   - Abstentions (personas who bid 0 in every slot of the epoch)
   - Chair actions: ratify | request-revision <persona-id> | edit-and-ratify

5. Auto-populate `## Open Conflicts` in Sketchboard.md with detected pairs
   (additive, only this section; do not edit persona blocks).

6. Commit: "review(deliberation): epoch <N> review — <K> contested pair(s), <D> dominance flag(s)"
```

### `ratify`

```
1. Run: bash scripts/deliberate/orchestrate-epoch.sh ratify
2. Print the JSON: ratified_epoch, ratified_sha, next_epoch.
3. Sketchboard.md now has a fresh `## Epoch <N+1>` section appended.
4. epoch.json is in state COLLECTING with epoch counter = N+1, ready for `run`.
```

### `status`

```
Run: bash scripts/deliberate/orchestrate-epoch.sh status
Print the JSON to the user as a fenced block.
```

## How it differs from existing harness skills

| Concept | This skill | Existing skill |
|---|---|---|
| Shared artifact | `Sketchboard.md` (separate from Plans.md) | `Plans.md` |
| Communication model | State observation (read-then-write) | Task assignment |
| Review type | Sketchboard content diff + contested sections | Code diff + 4 perspectives |
| Conflict handling | Surface to human at epoch boundary | Resolved by Lead during work |

## Configuration

`harness.toml [deliberation]` block (opt-in):

```toml
[deliberation]
enabled = false                          # opt-in
sketchboard_path = "Sketchboard.md"
epoch_state_path = ".claude/state/deliberation/"
epoch_commit_budget = 5
bid_tiebreaker = "declaration-order"     # or "random"
personas = ["scaling-optimist", "architecture-skeptic", "bias-auditor"]
```

## Persona contract

See [`agents/personas/_persona-contract.md`](../../agents/personas/_persona-contract.md) and [references/persona-modes.md](${CLAUDE_SKILL_DIR}/references/persona-modes.md).

Persona Agent files at `agents/<id>.md` (flat root). The `agents/personas/` subdirectory contains docs only (README + contract).

## Out of scope (v0.1)

- Per-persona git branches (v0.2)
- Eavesdrop / 1-to-1 talk (v0.2)
- CRDT / Yjs (v0.3)
- LLM-based stance classifier for contested-section detection (v0.2)
- Worktree isolation per persona (v0.2)

## Tests

- `tests/test-deliberation-personas.sh` — 3-state coverage (Healthy / NotConfigured / Corrupted)
- `tests/test-deliberation-bidding.sh` — bidding mechanics + tiebreak + close conditions
- `tests/test-sketchboard-conflict-detection.sh` — contested-section detection on adversarial fixtures

## References

- [references/bidding.md](${CLAUDE_SKILL_DIR}/references/bidding.md) — slot loop algorithm + bid log format
- [references/persona-modes.md](${CLAUDE_SKILL_DIR}/references/persona-modes.md) — BID and WRITE contract details
- [references/epoch-review.md](${CLAUDE_SKILL_DIR}/references/epoch-review.md) — chair workflow + v0.1 heuristic limits
