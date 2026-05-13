"""Sketchboard.md section parsing + block append + additivity check.

Centralizes everything that touches the deliberation document. Used by:
  - orchestrate_epoch.py init/ratify (template substitution, section append)
  - spawn_winner.py postcheck (additivity, position, forbidden-section)
  - detect_contested.py (block extraction)

Audit fixes implemented here:
  #1  FORBIDDEN_TOUCHED dead-code → real section-boundary check
  #10 ratify section-insertion verified
  #13 diff position verified within current epoch section
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


PERSONA_HEADING_RE = re.compile(r"^## (?P<name>.+?):\s*$")
EPOCH_HEADING_RE = re.compile(r"^## Epoch (?P<n>\d+)\s*$")
TOP_HEADING_RE = re.compile(r"^## (?P<name>.+?)\s*$")

# Section names that personas must never edit (chair-only / auto-populated).
FORBIDDEN_SECTIONS = ("Ratified Decisions", "Open Conflicts", "Frame", "Personas")


@dataclass
class Section:
    heading: str           # e.g. "Epoch 1", "Open Conflicts", "Scaling Optimist:"
    start_line: int        # inclusive, 0-indexed
    end_line: int          # exclusive
    parent_epoch: int | None = None  # if this is a persona block under an epoch


@dataclass
class PersonaBlock:
    persona_display: str   # "Scaling Optimist" (no trailing colon)
    epoch: int
    start_line: int        # heading line
    end_line: int          # exclusive
    body: str              # joined body text (without the heading line)


def parse_sketchboard(text: str) -> tuple[list[Section], list[PersonaBlock]]:
    """Return (top-level sections, persona blocks).

    A "top-level section" is any "## X" heading. A "persona block" is a "## Name:"
    heading nested under a "## Epoch N" section.
    """
    lines = text.splitlines()
    sections: list[Section] = []
    persona_blocks: list[PersonaBlock] = []
    current_epoch: int | None = None
    pending: dict | None = None

    def flush(end_line: int) -> None:
        nonlocal pending
        if pending is not None:
            sections.append(
                Section(
                    heading=pending["heading"],
                    start_line=pending["start_line"],
                    end_line=end_line,
                    parent_epoch=pending.get("parent_epoch"),
                )
            )
            if pending.get("is_persona"):
                body = "\n".join(lines[pending["start_line"] + 1 : end_line])
                persona_blocks.append(
                    PersonaBlock(
                        persona_display=pending["display"],
                        epoch=pending["parent_epoch"],
                        start_line=pending["start_line"],
                        end_line=end_line,
                        body=body,
                    )
                )
        pending = None

    for i, line in enumerate(lines):
        # Persona block heading: "## Name:" (trailing colon distinguishes from
        # top-level sections like "## Open Conflicts").
        persona_match = PERSONA_HEADING_RE.match(line)
        if persona_match and current_epoch is not None:
            flush(i)
            display = persona_match.group("name").strip()
            pending = {
                "heading": display + ":",
                "start_line": i,
                "parent_epoch": current_epoch,
                "is_persona": True,
                "display": display,
            }
            continue

        # Epoch heading: "## Epoch N"
        epoch_match = EPOCH_HEADING_RE.match(line)
        if epoch_match:
            flush(i)
            current_epoch = int(epoch_match.group("n"))
            pending = {
                "heading": f"Epoch {current_epoch}",
                "start_line": i,
                "parent_epoch": None,
                "is_persona": False,
            }
            continue

        # Other "## X" top-level heading (Frame / Personas / Open Conflicts /
        # Ratified Decisions / etc.) — exit any current epoch.
        top_match = TOP_HEADING_RE.match(line)
        if top_match and not persona_match:
            flush(i)
            current_epoch = None
            pending = {
                "heading": top_match.group("name").strip(),
                "start_line": i,
                "parent_epoch": None,
                "is_persona": False,
            }
            continue

    flush(len(lines))
    return sections, persona_blocks


def find_section_range(text: str, heading: str) -> tuple[int, int] | None:
    """Return (start_line, end_line) of a top-level section by heading. None if absent."""
    sections, _ = parse_sketchboard(text)
    for s in sections:
        if s.heading == heading:
            return s.start_line, s.end_line
    return None


def display_name_to_id(display: str) -> str:
    """e.g. 'Scaling Optimist' → 'scaling-optimist'."""
    return display.strip().lower().replace(" ", "-")


def id_to_display_name_from_file(persona_id: str, agents_dir: Path) -> str | None:
    """Read `agents/<id>.md` frontmatter for the persona display name.

    Audit #4: was deriving display from id via title-case. Now reads the persona
    file. We look for a `name:` field in frontmatter (which holds the id) and
    derive display from the first `# <X>` heading in the body, OR fall back to
    title-cased id if neither is found.
    """
    path = agents_dir / f"{persona_id}.md"
    if not path.exists():
        return None
    text = path.read_text()
    # Body heading: first "# X" line after the frontmatter close.
    in_frontmatter = False
    frontmatter_closed = False
    for line in text.splitlines():
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            in_frontmatter = False
            frontmatter_closed = True
            continue
        if frontmatter_closed and line.startswith("# ") and not line.startswith("##"):
            return line[2:].strip()
    # Fallback: title-case id
    return " ".join(w.capitalize() for w in persona_id.split("-"))


# ---------------------------------------------------------------------------
# Template substitution (used by orchestrate_epoch.py init)
# ---------------------------------------------------------------------------


def render_template(tmpl_text: str, question: str, frame: str, personas: list[str]) -> str:
    """Plain string replacement. Question + frame are passed as-is (no shell
    interpolation, audit #11)."""
    personas_block = "\n".join(f"- {p}" for p in personas)
    out = tmpl_text.replace("{{QUESTION}}", question)
    out = out.replace("{{FRAME}}", frame or "(chair to fill before run, or leave blank)")
    out = out.replace("{{PERSONAS_LIST}}", personas_block)
    return out


# ---------------------------------------------------------------------------
# Ratify: append new epoch section. Audit #10: explicitly assert the insertion
# point existed, fail loudly if not.
# ---------------------------------------------------------------------------


def append_next_epoch_section(text: str, next_epoch: int) -> str:
    """Insert `## Epoch <next>` immediately before `## Open Conflicts`.

    Raises ValueError if `## Open Conflicts` is missing (audit #10 — the prior
    silent fallback "append at the end" was wrong because it landed after
    Ratified Decisions).
    """
    open_conflicts_re = re.compile(r"(^|\n)## Open Conflicts\b", re.MULTILINE)
    match = open_conflicts_re.search(text)
    if not match:
        raise ValueError(
            "ratify: '## Open Conflicts' section not found in sketchboard; "
            "cannot determine where to insert the next epoch section"
        )
    insert_at = match.start() + (1 if text[match.start()] == "\n" else 0)
    block = (
        f"\n## Epoch {next_epoch}\n\n"
        f"<!-- Persona blocks for epoch {next_epoch} accumulate below. -->\n\n"
        f"---\n\n"
    )
    return text[:insert_at] + block + text[insert_at:]


# ---------------------------------------------------------------------------
# Postcheck helpers — used by spawn_winner.py
# ---------------------------------------------------------------------------


def verify_block_in_epoch(
    new_text: str, prev_text: str, epoch: int, persona_display: str
) -> tuple[bool, str]:
    """Verify the diff between prev_text and new_text is:
      1. Purely additive (no deletions/edits to existing lines).
      2. All added lines land WITHIN the `## Epoch <epoch>` section (audit #1, #13).
      3. New block has the persona's heading `## <Display>:` and ≥1 blockquote.

    Returns (ok, reason). reason is empty on ok.
    """
    prev_lines = prev_text.splitlines()
    new_lines = new_text.splitlines()

    # 1. Additive: every line in prev must appear in new in the same order.
    j = 0
    for line in prev_lines:
        # Find this line in new_lines from position j onward.
        while j < len(new_lines) and new_lines[j] != line:
            j += 1
        if j >= len(new_lines):
            return False, "non-additive: existing line removed or modified"
        j += 1

    # 2. Find the epoch section in NEW text.
    _, new_blocks = parse_sketchboard(new_text)
    epoch_sections, _ = parse_sketchboard(new_text)
    epoch_section = next(
        (s for s in epoch_sections if s.heading == f"Epoch {epoch}"), None
    )
    if epoch_section is None:
        return False, f"epoch-section-missing: no '## Epoch {epoch}' heading in new content"

    # 3. The added lines (those in new but not in prev, in order) must all sit
    # within [epoch_section.start_line, epoch_section.end_line).
    added_indices = _added_line_indices(prev_lines, new_lines)
    for idx in added_indices:
        if not (epoch_section.start_line <= idx < epoch_section.end_line):
            # Check which section it landed in for a useful error
            for fs in FORBIDDEN_SECTIONS:
                fs_range = find_section_range(new_text, fs)
                if fs_range and fs_range[0] <= idx < fs_range[1]:
                    return False, f"edited-forbidden-section: addition landed in '{fs}' section"
            return (
                False,
                f"out-of-epoch-section: addition at line {idx} is outside '## Epoch {epoch}'",
            )

    # 4. The new persona block exists in the new content, attributed to this
    # persona, in the current epoch.
    matching = [
        b for b in new_blocks
        if b.epoch == epoch and b.persona_display == persona_display
    ]
    if not matching:
        return False, (
            f"missing-or-wrong-heading: no '## {persona_display}:' block in epoch {epoch}"
        )

    # 5. The newest block (largest start_line) must contain ≥1 blockquote line.
    newest = max(matching, key=lambda b: b.start_line)
    if not any(l.startswith(">") for l in newest.body.splitlines()):
        return False, "missing-blockquote: WRITE block must quote an earlier claim"

    return True, ""


def _added_line_indices(prev: list[str], new: list[str]) -> list[int]:
    """Return indices in `new` of lines that are additions vs `prev` (assumes
    pure-additive — caller has already verified)."""
    out: list[int] = []
    j = 0
    for ni, nline in enumerate(new):
        if j < len(prev) and nline == prev[j]:
            j += 1
        else:
            out.append(ni)
    return out
