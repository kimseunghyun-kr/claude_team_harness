"""SSOT reader for harness.toml [deliberation] block.

Single owner of "what does the config say?" — eliminates the audit-#J DRY violation
where collect-bids.sh and spawn-winner.sh each had their own awk-based TOML parser.

Why not `tomllib`/`tomli`: this code may run on Python < 3.11 systems (the repo's
own check-residue.sh ships its own parser pattern), so we use a minimal regex-based
parser scoped to the one block we need. If the config grows beyond what this parser
handles, swap in tomllib at the cost of one Python version bump.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DeliberationConfig:
    """Parsed [deliberation] block. All fields have defaults so a missing config
    block produces a `disabled, no-personas` config rather than crashing."""

    enabled: bool = False
    sketchboard_path: str = "Sketchboard.md"
    epoch_state_path: str = ".claude/state/deliberation/"
    epoch_commit_budget: int = 5
    bid_tiebreaker: str = "declaration-order"
    personas: list[str] = None  # type: ignore[assignment]
    # v0.1.2 — per-persona branch / two-turn extraction
    extraction_model: str = ""               # empty → use persona's frontmatter model
    extraction_temperature: float = 0.0      # deterministic extraction by default
    spawn_mode: str = "subagent"             # "subagent" | "sequential"
    eavesdrop_enabled: bool = False
    eavesdrop_probability: float = 0.15
    gc_keep_epochs: int = 3

    def __post_init__(self) -> None:
        if self.personas is None:
            self.personas = []


def repo_root() -> Path:
    """Resolve repo root from this file's location.
    `scripts/deliberate/lib/config.py` → `<repo>/`.
    """
    return Path(__file__).resolve().parents[3]


def harness_toml_path() -> Path:
    return repo_root() / "harness.toml"


_SCALAR_RE = re.compile(r"^(?P<key>[a-z_][a-z0-9_]*)\s*=\s*(?P<value>.+?)\s*(?:#.*)?$")
_ARRAY_START_RE = re.compile(r"^(?P<key>[a-z_][a-z0-9_]*)\s*=\s*\[(?P<rest>.*)$")
_SECTION_RE = re.compile(r"^\[(?P<name>[a-z_][a-z0-9_.]*)\]\s*$")


def _strip_inline_comment(value: str) -> str:
    # naive: a `#` outside quotes ends the value. Good enough for our schema.
    in_str = False
    for i, ch in enumerate(value):
        if ch == '"':
            in_str = not in_str
        elif ch == "#" and not in_str:
            return value[:i].strip()
    return value.strip()


def _parse_scalar(raw: str) -> Any:
    raw = _strip_inline_comment(raw)
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    try:
        if "." not in raw:
            return int(raw)
        return float(raw)
    except ValueError:
        return raw


def _parse_array(items_buf: str) -> list[Any]:
    items_buf = items_buf.rstrip("]").strip()
    if not items_buf:
        return []
    out: list[Any] = []
    for raw in items_buf.split(","):
        raw = raw.strip()
        if not raw:
            continue
        out.append(_parse_scalar(raw))
    return out


def read_config() -> DeliberationConfig:
    """Read and return the [deliberation] block as a typed config object.

    Robust to: inline comments, single-line and multi-line arrays, missing keys
    (defaults apply), and missing block entirely (returns disabled default).
    """
    path = harness_toml_path()
    if not path.exists():
        return DeliberationConfig()

    in_section = False
    raw_data: dict[str, Any] = {}
    array_buf: list[str] = []
    array_key: str | None = None

    for line in path.read_text().splitlines():
        # Continue collecting an open multi-line array. array_buf already starts
        # with the content AFTER the opening `[` (saved when we matched
        # _ARRAY_START_RE earlier), so we just join and parse up to the `]`.
        if array_key is not None:
            array_buf.append(line)
            if "]" in line:
                full = " ".join(array_buf)
                raw_data[array_key] = _parse_array(full)
                array_key = None
                array_buf = []
            continue

        section_match = _SECTION_RE.match(line.strip())
        if section_match:
            in_section = section_match.group("name") == "deliberation"
            continue
        if not in_section:
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Array start
        array_match = _ARRAY_START_RE.match(stripped)
        if array_match:
            key = array_match.group("key")
            rest = array_match.group("rest")
            if "]" in rest:
                items = rest[: rest.index("]")]
                raw_data[key] = _parse_array(items)
            else:
                array_key = key
                array_buf = [rest]
            continue

        # Scalar
        scalar_match = _SCALAR_RE.match(stripped)
        if scalar_match:
            raw_data[scalar_match.group("key")] = _parse_scalar(scalar_match.group("value"))

    return DeliberationConfig(
        enabled=bool(raw_data.get("enabled", False)),
        sketchboard_path=str(raw_data.get("sketchboard_path", "Sketchboard.md")),
        epoch_state_path=str(raw_data.get("epoch_state_path", ".claude/state/deliberation/")),
        epoch_commit_budget=int(raw_data.get("epoch_commit_budget", 5)),
        bid_tiebreaker=str(raw_data.get("bid_tiebreaker", "declaration-order")),
        personas=list(raw_data.get("personas", []) or []),
        extraction_model=str(raw_data.get("extraction_model", "") or ""),
        extraction_temperature=float(raw_data.get("extraction_temperature", 0.0)),
        spawn_mode=str(raw_data.get("spawn_mode", "subagent") or "subagent"),
        eavesdrop_enabled=bool(raw_data.get("eavesdrop_enabled", False)),
        eavesdrop_probability=float(raw_data.get("eavesdrop_probability", 0.15)),
        gc_keep_epochs=int(raw_data.get("gc_keep_epochs", 3)),
    )


def sketchboard_abs_path(cfg: DeliberationConfig | None = None) -> Path:
    if cfg is None:
        cfg = read_config()
    return (repo_root() / cfg.sketchboard_path).resolve()


def state_dir(cfg: DeliberationConfig | None = None) -> Path:
    if cfg is None:
        cfg = read_config()
    return (repo_root() / cfg.epoch_state_path).resolve()
