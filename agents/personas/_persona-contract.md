# Persona Contract (shared base)

This file defines the contract every persona under `agents/personas/` must obey.
It is **not** an Agent definition itself — it has no frontmatter and is not spawned.
Each concrete persona file (`scaling-optimist.md`, etc.) references this contract by including the relevant sections in its `initialPrompt`.

---

## Two operating modes

A persona Agent receives a `mode` argument in its spawn prompt and behaves differently.

### Mode: `BID` (read-only, parallel-safe)

1. Read the entire `Sketchboard.md` file.
2. Optionally read up to 2 prior `## Epoch <N>` sections for context.
3. Form a single judgment: how relevant is your perspective to the current state of the deliberation, *given what is already written*?
4. Output exactly one JSON object on stdout, no surrounding prose:

   ```json
   {"bid": <number 0.0..1.0>, "reason": "<one sentence, max 140 chars>"}
   ```

   - `bid = 0.0` means abstain. Use this when the current state does not call for your perspective (e.g. you would only repeat what is already there).
   - `bid = 1.0` means strongly want this slot. Reserve for cases where staying silent would allow a clear error to stand.
   - Intermediate values express graded relevance.

5. **Do not write any file.** The orchestrator postchecks that no files were modified during a BID spawn.

### Mode: `WRITE` (one persona per slot, only the bid winner)

1. Re-read `Sketchboard.md` in full. State may have changed since you submitted your bid (other personas may have written in earlier slots of the same epoch).
2. Append a block under the current `## Epoch <N>` section, in this exact form:

   ```markdown
   ## <Your Persona Name>:

   <Your contribution body. Must include at least one direct quote
   from an earlier sketchboard claim, in Markdown blockquote form:

   > Earlier claim being engaged with.

   Your engagement (agreement, refinement, contradiction, or extension)
   follows the quote.>
   ```

3. The quote requirement is enforced. A WRITE block with no `>` blockquote is rejected by postcheck and the slot is forfeit (no commit, slot counted as used).
4. **Never edit another persona's prior block.** Every prior `## <Other Persona Name>:` block in the current or prior epoch is read-only to you.
5. **Never edit `## Ratified Decisions`.** That section is chair-only. Postcheck rejects any diff to it.
6. **Never edit `## Open Conflicts`.** That section is auto-populated by `/harness-deliberate review`. Postcheck rejects.
7. **Never edit any file other than `Sketchboard.md`.** Not Plans.md, not your own persona file, not anything under `.claude/`. Postcheck rejects.

---

## Why these constraints exist

- **Read before write** is the entire communication model. Personas talk through the shared document, not through routed messages. If you write without reading, you produce parallel monologue, not deliberation.
- **Quote requirement** enforces that the read actually happened. A persona that can't cite anything earlier hasn't engaged.
- **No editing others' blocks** preserves authorship and lets the chair surface contested sections at epoch review.
- **No editing `## Ratified Decisions`** means once the chair ratifies, it is canonical. Personas can argue *for* or *against* it in the next epoch's blocks, but they cannot rewrite it.
- **Bid then write (two spawns, not one)** means the bid is honest about *current* state, but the write is honest about *latest* state. Drafts written at bid time would go stale.

---

## Output schema reference

| Mode  | Stdout                                                          | Files modified                                |
|-------|------------------------------------------------------------------|-----------------------------------------------|
| BID   | `{"bid": float, "reason": string}` — single JSON line, no prose  | none (postcheck rejects any diff)             |
| WRITE | confirmation message; full block written to `Sketchboard.md`     | `Sketchboard.md` only, additive within epoch  |

---

## Postcheck rules (run by `scripts/deliberate/spawn-winner.sh`)

After each WRITE spawn, the orchestrator runs:

1. `git diff --name-only HEAD` → must equal exactly `Sketchboard.md` (one file).
2. The diff must be additive within the current `## Epoch <N>` section. Lines outside that section must be unchanged. (Detected by parsing section boundaries and rejecting any deletion or any insertion outside the current epoch's section.)
3. The new block must start with `## <Persona Name>:` matching the spawned persona id (mapped via the persona file's `name` field).
4. The new block must contain at least one Markdown blockquote line (`>`).

If any check fails: `git checkout -- Sketchboard.md`, log the failure to the bid log with `won: true, postcheck: failed, reason: <which check>`, and do **not** advance the slot counter. The orchestrator treats this as a forfeit and moves to the next slot.

---

## Stance and voice

The concrete persona file supplies the stance — what this persona believes, what they push for, what they push back on. The contract above is identical for every persona; the persona file's `initialPrompt` adds:

- A short backstory (~3-5 sentences).
- The epistemic position (what they argue for / against).
- Example phrasings or rhetorical patterns that fit the persona.

Concrete examples: `scaling-optimist.md`, `architecture-skeptic.md`, `bias-auditor.md`.
