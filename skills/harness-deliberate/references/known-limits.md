# Known Limits (v0.1.1)

The v0.1.1 rebuild (shell → Python) addressed the audit issues that affected
correctness. A few items were *deliberately deferred* because they require
design changes, not bug fixes. They're documented here so users can plan around
them and v0.2 has a clear target.

## Deferred: persona bid-history memory (audit #3)

**What:** Each persona spawn is a fresh context. A persona has no memory of its
own prior bids within an epoch. In slot 3, scaling-optimist doesn't *know* it
self-throttled to 0.05 in slot 2; the only way it learns about its own prior
state is by re-reading Sketchboard.md (which contains its own prior block).

**Why this matters:** The "honest turn-taking" we observed in smoke tests was
partly luck — the persona inferred its prior choice from the sketchboard, not
from explicit memory. A persona could in principle:

- Bid high in slot 2 immediately after writing slot 1, because it forgot it
  just wrote.
- Repeat itself across slots because it doesn't see the "I already said this"
  signal in its private context.

In practice, with our 3 sample personas the sketchboard re-read is enough.
But the contract leaks: `prior_bids_visible=false` is hardcoded in
`collect_bids.py` with no mechanism to ever set it `true`.

**v0.2 fix:** Pass the bid log for the current epoch as a structured input to
each BID spawn. Persona prompt becomes:

```
mode=BID
epoch=3
slot=3
sketchboard_path=...
your_prior_bids_this_epoch=[
  {"slot": 1, "bid": 0.85, "reason": "..."},
  {"slot": 2, "bid": 0.05, "reason": "..."}
]
```

The persona can then incorporate "I've taken N slots already; my role this
turn is..." into its reasoning explicitly rather than emergently.

This also opens the door to **per-persona slot budgets** as a v0.2 governance
knob (e.g., no persona may win more than 50% of an epoch's slots).

## Deferred: `ratified` ref-as-branch (audit #16)

**What:** The orchestrator writes the ratified pointer to `refs/heads/ratified`:

```python
git("update-ref", "refs/heads/ratified", ...)
```

`refs/heads/` is the branches namespace, so `git branch` shows `ratified`
alongside `main`. A user who runs `git checkout ratified` ends up on what
*looks* like a branch — but the orchestrator will overwrite it on next
ratify with no merge, no log, no warning.

**Why deferred:** Cosmetic for v0.1. Real fix is to use `refs/ratified/HEAD`
(custom ref namespace, not a branch), but that breaks any existing tooling
that grew to depend on `git branch ratified`. v0.2 will migrate with a one-
time `git update-ref -d refs/heads/ratified` instruction in CHANGELOG.

## Other limits that ARE in v0.1.1 docs already

- **Contested-section detector is keyword-based and v0.2 replaces it with
  an LLM stance classifier.** See [epoch-review.md](epoch-review.md). The
  known false-positive and false-negative cases are regression-tested in
  [tests/test-sketchboard-conflict-detection.sh](../../../tests/test-sketchboard-conflict-detection.sh)
  with adversarial fixtures.
- **Personas are Claude sub-agent spawns, not local models.** Every spawn
  is an API call on Anthropic infrastructure. ~20 spawns per epoch
  (3 personas × 5 BID + ≤5 WRITE). See README "Deliberation Mode" section.
- **Worktree isolation is `none` in v0.1.** Sequential turns on the shared
  checkout. v0.2 introduces per-persona branches to enable eavesdrop and
  1-to-1 talk patterns (collapsed into probabilistic state-observation
  per the original design notes).

## Audit fixes shipped in v0.1.1 (for the record)

| Item | What | Fix |
|---|---|---|
| #1  | FORBIDDEN_TOUCHED was dead code | Real section-boundary parsing in `lib/sketchboard.py` `verify_block_in_epoch` |
| #2  | Contested pairs flagged regardless of B | B must be written before A (document order) |
| #4  | Persona heading derived from id (lossy) | Read display name from `agents/<id>.md` frontmatter/body |
| #5  | BID stdout enforcement split | `bid_postcheck` in `lib/postcheck.py` is the single owner |
| #6  | Budget hardcoded to 5 | Read from `harness.toml [deliberation].epoch_commit_budget` |
| #7  | Heredoc interpolation of LLM output | Eliminated; argv/stdin throughout |
| #8  | `--no-verify` bypassed git hooks | Removed; hooks now run on all orchestrator commits |
| #9  | `sketchboard_path` / `epoch_state_path` hardcoded | Honored throughout via `lib/config` |
| #10 | Ratify silently fell back when section missing | Raises `ValueError`; orchestrator surfaces it |
| #11 | Shell injection on question argument | argv only; subprocess never uses `shell=True` |
| #12 | `close` not idempotent | `git tag -f` |
| #13 | Diff position not verified | `verify_block_in_epoch` checks line indices against section ranges |
| #15 | `datetime.utcnow()` deprecation | All callers use `datetime.now(timezone.utc)` |

Audit items #3 (memory) and #16 (ref-as-branch) deferred — see above.
