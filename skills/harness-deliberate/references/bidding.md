# Bidding Mechanics

How the per-slot bidding loop works in `/harness-deliberate run`.

## The slot loop

```
config:
  budget = harness.toml [deliberation].epoch_commit_budget   # default 5
  personas = harness.toml [deliberation].personas            # ordered list
  tiebreaker = harness.toml [deliberation].bid_tiebreaker    # "declaration-order" | "random"

for slot in 1..budget:
  # Step 1: collect bids from every persona in parallel
  bids = parallel_spawn(personas, mode=BID)
    # each persona spawn returns {"bid": float, "reason": string}
    # spawn timeout: 60s; if a persona times out, treat as bid=0 reason="timeout"

  # Step 2: persist all bids (including 0-bids) to the bid log
  append_bid_log(epoch, slot, bids)

  # Step 3: filter abstainers
  active_bids = [b for b in bids if b.score > 0.0]

  # Step 4: close-on-all-abstain
  if len(active_bids) == 0:
    close_epoch(reason="all-abstain")
    break

  # Step 5: pick the winner
  winner = select_winner(active_bids, tiebreaker)

  # Step 6: spawn winner in WRITE mode
  result = spawn(winner.persona, mode=WRITE)

  # Step 7: postcheck the diff
  postcheck_result = postcheck_diff()
  if postcheck_result == "rejected":
    # forfeit: revert the diff, log the forfeit, advance to next slot
    git_checkout("Sketchboard.md")
    mark_bid_log_forfeit(slot, winner.persona, postcheck_result.reason)
    continue   # slot counter still advances

  # Step 8: commit
  git_commit(f"epoch-{N} slot-{slot}: {winner.persona}")

# After the loop
close_epoch(reason="budget-exhausted")
git_tag(f"epoch-{N}-unratified")
```

## Tie-breaking

When multiple personas tie at the maximum bid:

- `bid_tiebreaker = "declaration-order"` (default): pick the persona that appears first in `harness.toml [deliberation].personas[]`. Deterministic, reproducible across reruns.
- `bid_tiebreaker = "random"`: shuffle tied personas with a seed derived from `(epoch, slot)` so reruns of the same epoch+slot still pick the same winner.

## Bid log format

Path: `.claude/state/deliberation/epoch-<N>-bids.jsonl`. One JSON object per line.

```json
{"slot": 1, "persona": "scaling-optimist", "bid": 0.82, "reason": "Architectural mysticism in frame", "won": true}
{"slot": 1, "persona": "architecture-skeptic", "bid": 0.40, "reason": "Will respond next slot", "won": false}
{"slot": 1, "persona": "bias-auditor", "bid": 0.0, "reason": "No deliberation pattern yet", "won": false}
{"slot": 2, "persona": "scaling-optimist", "bid": 0.30, "reason": "Already made my point", "won": false}
{"slot": 2, "persona": "architecture-skeptic", "bid": 0.85, "reason": "Direct rebuttal needed", "won": true}
{"slot": 2, "persona": "bias-auditor", "bid": 0.0, "reason": "Healthy engagement so far", "won": false}
{"slot": 3, "persona": "scaling-optimist", "bid": 0.0, "reason": "Nothing to add", "won": false, "forfeit": false}
{"slot": 3, "persona": "architecture-skeptic", "bid": 0.0, "reason": "Just wrote", "won": false, "forfeit": false}
{"slot": 3, "persona": "bias-auditor", "bid": 0.0, "reason": "Going well", "won": false, "forfeit": false}
```

In the example above, slot 3 closes the epoch with `close_reason: "all-abstain"` even though budget was 5 — only 2 commits land.

## Forfeit case

When a winner's WRITE diff fails postcheck:

```json
{"slot": 4, "persona": "scaling-optimist", "bid": 0.70, "reason": "...", "won": true, "forfeit": true, "postcheck_failure": "edited_open_conflicts_section"}
```

Forfeits **do** advance the slot counter (slot 4 is consumed). This prevents an infinite loop where the same persona keeps winning and keeps violating the contract.

## Cost analysis

For 3 personas × 5 slot budget:

- Best case (all-abstain on slot 1): 3 BID spawns total
- Typical case (normal deliberation): 3 BID + 1 WRITE per slot × ~3-4 slots before all-abstain ≈ 12-16 BID + 3-4 WRITE = 15-20 spawns
- Worst case (budget exhausted, no abstentions): 3 BID + 1 WRITE per slot × 5 = 20 spawns

Acceptable. Bids are read-only and parallelize cleanly.

## Why bid-then-write (not bid-with-draft)

Alternative considered: persona returns `{bid, draft}` in one shot, draft committed only on win.

Rejected because:

1. **Stale drafts**: by the time slot N closes, slots 1..N-1 may have changed Sketchboard. A draft written at bid time is reasoning about an obsolete state.
2. **Wasted compute**: every persona drafts every slot. With 3 personas × 5 slots = 15 drafts, of which only ≤5 ship.
3. **Honest separation**: BID is "do I have something to say given current state?", WRITE is "what exactly do I say given current state?" These are different judgments and benefit from being separate.

The cost of two spawns instead of one is the price of those properties.

## Stop conditions for `run`

Before starting the loop, refuse to run if:

- `Sketchboard.md` is missing → "call `/harness-deliberate init` first"
- `epoch.json` is in state `REVIEW` or `RATIFIED` → "review and ratify the prior epoch first"
- Working tree is dirty → "commit or stash uncommitted changes; the orchestrator commits after each slot"
- `[deliberation].enabled = false` in `harness.toml` → "set enabled = true first"
- `[deliberation].personas[]` is empty or has < 2 entries → "deliberation needs ≥ 2 personas"
