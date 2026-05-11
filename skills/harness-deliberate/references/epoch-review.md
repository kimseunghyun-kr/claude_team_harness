# Epoch Review (Chair Workflow)

What `/harness-deliberate review` produces and how the chair acts on it.

## Trigger

`/harness-deliberate review` runs after `/harness-deliberate run` has closed an epoch (state = REVIEW). If `state != REVIEW`, the command refuses and prints the current state.

## Report sections

The review report is Markdown. It is printed to stdout, written to `.claude/state/deliberation/epoch-<N>-review.md` for permanence, and the contested-sections data also auto-populates the `## Open Conflicts` section of `Sketchboard.md` itself.

### 1. Diff summary

```
git diff <ratified>..<epoch-N-unratified> -- Sketchboard.md
```

Annotated by parsing the new persona blocks and grouping the diff by `## <Persona Name>:` header. The chair sees: "Scaling Optimist added 12 lines in slot 1; Architecture Skeptic added 18 lines in slot 2; Bias Auditor abstained all 3 slots before close."

### 2. Bid distribution

For each slot, a small table:

| Slot | Persona | Bid | Reason | Outcome |
|------|---------|-----|--------|---------|
| 1 | scaling-optimist | 0.82 | Frame contains scale-only assumption | **WON** |
| 1 | architecture-skeptic | 0.40 | Will respond next slot | lost |
| 1 | bias-auditor | 0.00 | No deliberation pattern yet | abstain |

Built from `.claude/state/deliberation/epoch-<N>-bids.jsonl`.

### 3. Contested sections

Detected by `scripts/deliberate/detect-contested.sh`. Heuristic algorithm (v0.1):

1. Parse each persona block in the current epoch.
2. For each pair of blocks (A, B) within the same epoch, check:
   - **Trigger keywords**: A contains `disagree | however | but | wrong | incorrect | not the case`, AND those words point at content from B (or vice versa). → flag.
   - **Quote-and-rebut**: A contains a blockquote of a claim that B made earlier, AND A's block contains negation language. → flag.
3. Auto-populate `## Open Conflicts` section in `Sketchboard.md` with the flagged pairs.

#### Known limits (regression-tested in `tests/test-sketchboard-conflict-detection.sh`)

The v0.1 heuristic is keyword-based and has documented failure modes:

| Case | Heuristic flags? | Reality | Test fixture |
|---|---|---|---|
| Two blocks with explicit "however" disagreement | Yes | Yes (true positive) | `tests/fixtures/sketchboard-contested-obvious.md` |
| Two complementary blocks, no trigger keywords | No | No (true negative) | `tests/fixtures/sketchboard-uncontested-obvious.md` |
| Semantic contradiction without trigger keywords | **No** | **Yes (false negative)** | `tests/fixtures/sketchboard-contested-no-keywords.md` |
| "However, I agree" — keywords without contradiction | **Yes** | **No (false positive)** | `tests/fixtures/sketchboard-uncontested-with-keywords.md` |

Tests assert all four cases including the false positive and false negative. The chair must be aware that:

- **Some real contradictions will slip through unflagged.** The chair must read the diff personally, not rely solely on `## Open Conflicts`.
- **Some flagged "conflicts" are not actually contradictions.** The chair can dismiss flagged pairs that are concord-with-trigger-words.

v0.2 replaces this heuristic with an LLM-based stance classifier. At that point, exactly two test assertions in `test-sketchboard-conflict-detection.sh` flip (the false-positive and false-negative cases) — that is the regression target.

### 4. Abstentions

Personas who bid 0 across **every** slot of this epoch get listed:

> **Bias Auditor abstained all 3 slots.** Reasons: "No deliberation pattern yet" (slot 1), "Healthy engagement so far" (slot 2), "Going well" (slot 3).

The chair should ask: was this persona genuinely satisfied, or were they silenced by dominance, or are they not a relevant persona for this question? The chair has options below to address each.

### 5. Chair actions

Three options the chair can take:

#### `ratify`

```
/harness-deliberate ratify
```

Moves the `ratified` git ref to `epoch-N-unratified`, opens epoch N+1. Unresolved `## Open Conflicts` are echoed into epoch N+1's `## Frame` section as chair-noted carry-over (so the personas know what's still open).

#### `request-revision <persona-id>`

```
/harness-deliberate request-revision architecture-skeptic
```

Reverts that persona's last block in the unratified epoch (using `git revert` on that specific commit) and reopens the epoch (state: COLLECTING) with one extra slot allocated to the named persona. Use this when the chair believes a persona's contribution was off-stance or off-contract in a way the postcheck didn't catch.

#### `edit-and-ratify`

The chair manually edits `Sketchboard.md` (typically merging contested sections, refining the `## Ratified Decisions` proposal, or rewording for clarity) and then calls `/harness-deliberate ratify`. There is no separate command — direct edit + ratify is the workflow.

## Why no `harness-review` integration

The existing `harness-review` skill reviews **code** along 4 axes (security, performance, quality, accessibility). The epoch review here is content-focused: the chair is reading positions, not code. Re-using `harness-review` would force a code-shaped lens onto deliberation content.

Sketchboard.md changes are technically Markdown diffs in a git repo, but conflating them with code review would give the chair the wrong tool.

## Output artifacts

After `/harness-deliberate review`:

- `.claude/state/deliberation/epoch-<N>-review.md` — full report (this is the chair's working copy)
- `Sketchboard.md` `## Open Conflicts` section — auto-populated with detected contested pairs
- `epoch.json` unchanged (still `state: REVIEW`)

After `/harness-deliberate ratify`:

- Git: `ratified` ref → `epoch-<N>-unratified` commit
- `epoch.json` → `state: RATIFIED` then immediately `state: OPEN, epoch: N+1`
- `Sketchboard.md`:
  - `## Open Conflicts` cleared
  - new `## Epoch <N+1>` section appended
  - any chair-noted carry-over written to `## Frame`
