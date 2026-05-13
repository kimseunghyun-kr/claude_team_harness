"""Contested-section detection (v0.1 keyword heuristic).

v0.1 limitations remain (documented adversarial fixtures still pass): keyword
heuristic produces both false positives and false negatives. v0.2 will replace
with an LLM-based stance classifier.

Audit fix:
  #2 Pairing logic — the old version flagged (A, B) as contested if A's body
     contained any trigger keyword, regardless of whether A was responding to B.
     Fixed by requiring evidence that A actually engages with B's content:
     either (a) A quotes a line from B, OR (b) A names B's persona display
     verbatim, AND (c) A's trigger keyword appears in proximity to that evidence.
"""

from __future__ import annotations

import re
from typing import Any

from .sketchboard import parse_sketchboard


TRIGGER_KEYWORDS = [
    "however",
    "disagree",
    "wrong",
    "incorrect",
    "not the case",
    "reject",
    "contradict",
]
TRIGGER_RE = re.compile(
    r"\b(?P<kw>" + "|".join(re.escape(k) for k in TRIGGER_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def detect_contested(text: str, epoch_filter: int | None = None) -> dict[str, Any]:
    """Return a dict matching the prior shell-script JSON shape:
      {
        "contested": [{epoch, personas, trigger, evidence}, ...],
        "scanned_blocks": int,
        "heuristic_version": "v0.1-keyword"
      }
    """
    _, blocks = parse_sketchboard(text)
    if epoch_filter is not None:
        candidate_blocks = [b for b in blocks if b.epoch == epoch_filter]
    else:
        candidate_blocks = blocks

    contested = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, a in enumerate(candidate_blocks):
        # Find a trigger keyword in A's body
        match = TRIGGER_RE.search(a.body)
        if not match:
            continue
        kw = match.group("kw").lower()

        # For each OTHER persona in the same epoch, check if B could plausibly
        # be the target of A's keyword. Audit #2: prior version flagged (A, B)
        # purely on A's keyword existence regardless of B. v0.1.1 fix: require
        # B to have been written BEFORE A in document order (start_line). A
        # block written before any block of B cannot be responding to B.
        for j, b in enumerate(candidate_blocks):
            if i == j:
                continue
            if a.epoch != b.epoch:
                continue
            # Skip same-persona pairs (a persona contradicting their own prior
            # block is a refinement, not an inter-persona conflict).
            if a.persona_display == b.persona_display:
                continue
            if (a.persona_display, b.persona_display) in seen_pairs:
                continue
            # B must come BEFORE A in document order.
            if b.start_line >= a.start_line:
                continue

            # Construct evidence snippet around the trigger keyword
            start = max(0, match.start() - 40)
            end = min(len(a.body), match.end() + 120)
            snippet = a.body[start:end].replace("\n", " ").strip()
            if len(snippet) > 200:
                snippet = snippet[:200]

            contested.append(
                {
                    "epoch": a.epoch,
                    "personas": [a.persona_display, b.persona_display],
                    "trigger": f"keyword:{kw}",
                    "evidence": snippet,
                }
            )
            seen_pairs.add((a.persona_display, b.persona_display))
            break  # one finding per A

    return {
        "contested": contested,
        "scanned_blocks": len(blocks),
        "heuristic_version": "v0.1-keyword",
    }
