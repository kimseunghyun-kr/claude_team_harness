# Personas (Deliberation Harness v0.1)

Persona Agent definitions used by `/harness-deliberate`. Each file is a full Agent (frontmatter + initialPrompt) but follows a shared two-mode contract defined in [`_persona-contract.md`](_persona-contract.md).

## How personas differ from `agents/worker.md` etc.

| Aspect                | `agents/worker.md` (existing)                          | `agents/personas/*.md` (new)                             |
|-----------------------|--------------------------------------------------------|----------------------------------------------------------|
| Input                 | Task assignment with explicit DoD                      | Sketchboard state — read first, decide what to do        |
| Output                | Code + `worker-report.v1` JSON                         | A bid (BID mode) or a Sketchboard block (WRITE mode)     |
| Authority to write    | Files declared in `files[]`                            | `Sketchboard.md` only, additive within current epoch     |
| Communication         | Via task contract                                      | Via shared document (read-then-write)                    |
| Contract enforcer     | `worker.self_review` rules + Lead review               | `scripts/deliberate/spawn-winner.sh` postcheck           |
| Abstain valid?        | No — task must be done or escalated                    | Yes — bid 0 is a first-class outcome                     |

## Adding a new persona

1. Copy an existing persona file (e.g. `scaling-optimist.md`) to `agents/personas/<your-id>.md`.
2. Update the frontmatter `name`, `description`.
3. Replace the `initialPrompt` body (after the shared contract section) with your persona's stance, backstory, and characteristic moves.
4. Add the persona id to `harness.toml [deliberation].personas[]`.
5. Run `bash tests/test-deliberation-personas.sh` — must PASS in `_Healthy` state.

## Persona file structure

Every persona file follows this layout:

```markdown
---
name: <persona-id>
description: <one-line trigger description>
tools: [Read, Write, Edit, Bash, Grep, Glob]
disallowedTools: [Agent]
model: claude-opus-4-7
effort: medium
maxTurns: 30
color: <distinguishing color>
memory: project
isolation: none           # v0.1 = no worktree (sequential turns); v0.2 = worktree
initialPrompt: |
  [Shared contract preamble, ~10 lines, citing _persona-contract.md]
  [Persona-specific stance, ~5-10 lines]
  [Mode dispatch: "If mode=BID, ... If mode=WRITE, ..."]
---

# <Persona Display Name>

<Backstory paragraph>
<Epistemic position>
<Characteristic phrasings or rhetorical patterns>
```

## Why `disallowedTools: [Agent]`

Personas must not spawn other Agents. The deliberation orchestrator (`scripts/deliberate/orchestrate-epoch.sh`) is the only authorized spawner. Persona-spawning-persona would break the bidding contract.

## Why `isolation: none` in v0.1

v0.1 runs sequential turns on the shared checkout — each WRITE persona pulls latest state and commits directly. Worktree isolation per persona is a v0.2 change tied to the eavesdrop / 1-to-1-talk feature.

## Files in this directory

- `_persona-contract.md` — shared two-mode contract (referenced by every persona)
- `README.md` — this index
- `scaling-optimist.md` — sample persona: scaling-laws true believer
- `architecture-skeptic.md` — sample persona: inductive-bias defender
- `bias-auditor.md` — sample persona: deliberation-quality monitor (does not hold a position on the topic)
