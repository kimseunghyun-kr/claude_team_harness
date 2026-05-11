# Persona Modes (BID and WRITE)

Detailed mode contract for persona Agents in `/harness-deliberate run`. Authoritative source of truth is [`agents/personas/_persona-contract.md`](../../../agents/personas/_persona-contract.md); this document explains the orchestration side.

## Mode dispatch

The orchestrator spawns each persona via the `Agent` tool with a prompt that includes a `mode` token. The persona's `initialPrompt` parses `mode` and dispatches.

### BID-mode spawn prompt

The orchestrator constructs a prompt like this:

```
mode=BID
epoch=3
slot=2
sketchboard_path=Sketchboard.md
prior_bids_visible=false
```

The persona reads `Sketchboard.md`, runs through its stance to form a relevance judgment, and outputs exactly one JSON line:

```json
{"bid": 0.65, "reason": "Frame contains scale-only assumption uncontested"}
```

Postcheck (BID mode):
- `git diff` must show zero changed files. Any file write fails the BID and is treated as `bid: 0, reason: "<contract violation>", forfeit: true`.
- The stdout must parse as a single JSON object with exactly the keys `bid` (number, 0.0..1.0) and `reason` (string, ≤140 chars). Malformed output → bid: 0, reason: "<parse failure>".

### WRITE-mode spawn prompt

```
mode=WRITE
epoch=3
slot=2
sketchboard_path=Sketchboard.md
your_winning_bid=0.65
your_winning_reason=Frame contains scale-only assumption uncontested
```

The persona re-reads `Sketchboard.md` (state may differ from when they bid — earlier slots may have committed) and appends one block under the current `## Epoch <N>` section.

The block must:

1. Begin with a level-2 heading matching the persona's display name plus colon: `## Scaling Optimist:` (mapped from the persona file's `name: scaling-optimist` frontmatter).
2. Contain at least one Markdown blockquote line (`> `) — this is the "must quote earlier claim" requirement.
3. Be additive: the diff must only add lines within the current epoch's section. No deletions. No edits to other persona's blocks. No edits outside the current epoch section.

Postcheck (WRITE mode) — see `scripts/deliberate/spawn-winner.sh`:

| Check | Failure mode | Action |
|---|---|---|
| Exactly `Sketchboard.md` in `git diff --name-only` | Other file modified | Revert, forfeit slot |
| Diff is purely additive within current epoch section | Edits outside / deletions | Revert, forfeit slot |
| Block heading matches persona name | Wrong heading | Revert, forfeit slot |
| Block contains ≥ 1 `>` blockquote | Missing quote | Revert, forfeit slot |
| `## Ratified Decisions` section unchanged | Touched | Revert, forfeit slot |
| `## Open Conflicts` section unchanged | Touched | Revert, forfeit slot |

A forfeit logs to the bid log with `forfeit: true, postcheck_failure: <which check>` and advances the slot counter (no commit, but slot used).

## Why two spawns per winning bid

The bid is a relevance judgment ("do I have something to add?"). The write is the contribution itself ("here's what I add, given latest state").

If we collapsed these into one spawn:

- The "draft" would be written against bid-time state, but committed against post-other-slots state. That's stale.
- Personas would draft on every slot regardless of whether they win, wasting ~N× compute.
- The cleanly parallelizable BID phase would be coupled to WRITE-shaped work.

The cost is one extra spawn per won slot. Acceptable.

## Why the BID is bounded `[0.0, 1.0]`

- Lower bound 0.0 is the abstain semantic: "I have nothing to add given the current state."
- Upper bound 1.0 prevents bid-inflation arms races between personas.
- Continuous range (not discrete) lets personas express graded relevance — a 0.3 bid says "I'd contribute if no one else stronger comes forward" and naturally loses to a 0.7.

## Persona behavior across modes

A well-behaved persona:

- In BID mode, returns the same JSON shape regardless of stance. Stance affects the *value* of `bid`, not whether to return JSON.
- In WRITE mode, adheres to its persona file's stance and voice, quotes an earlier claim, engages with substance not posture.
- Never tries to spawn another Agent (`disallowedTools: [Agent]` in persona frontmatter blocks this at the tool-permission level too).

## Failure modes the contract catches

| Failure | Caught by |
|---|---|
| Persona writes a file in BID mode | Postcheck (BID): zero-file-change check |
| Persona returns prose instead of JSON in BID mode | Postcheck (BID): JSON parse |
| Persona edits Plans.md in WRITE mode | Postcheck (WRITE): file allowlist |
| Persona edits another persona's block | Postcheck (WRITE): diff scope check |
| Persona edits `## Ratified Decisions` | Postcheck (WRITE): chair-only section check |
| Persona writes without quoting | Postcheck (WRITE): blockquote requirement |
| Persona spawns sub-Agent | Tool permission (`disallowedTools: [Agent]`) |

## Failure modes the contract does NOT catch (v0.1 known limits)

- A persona writes a block that *quotes* an earlier claim but doesn't actually engage with it (semantic check is too expensive in v0.1).
- A persona writes a block that subtly contradicts another without trigger words (caught only by `detect-contested.sh` heuristic with known false-negative rate; see [epoch-review.md](epoch-review.md)).
- A persona drifts off-topic but stays formally compliant.

These are accepted v0.1 limitations. v0.2 introduces stance classification which catches the second; the first and third remain manual chair concerns.
