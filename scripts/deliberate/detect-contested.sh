#!/usr/bin/env bash
# detect-contested.sh
# v0.1 heuristic for contested-section detection on Sketchboard.md.
#
# Usage:
#   bash scripts/deliberate/detect-contested.sh <sketchboard-path> [--epoch N]
#
# Output (stdout, JSON):
#   { "contested": [
#       { "epoch": <N>,
#         "personas": ["scaling-optimist", "architecture-skeptic"],
#         "trigger": "keyword:however",
#         "evidence": "<≤200 char snippet>"
#       }, ...
#     ],
#     "scanned_blocks": <int>,
#     "heuristic_version": "v0.1-keyword"
#   }
#
# v0.1 heuristic limits (documented and regression-tested):
#   - False positive: "however, I agree" → flagged
#   - False negative: semantic contradiction without trigger keywords → missed
# Tests: tests/test-sketchboard-conflict-detection.sh

set -euo pipefail

SKETCHBOARD="${1:-Sketchboard.md}"
EPOCH_FILTER=""

# Parse optional --epoch N flag
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --epoch) EPOCH_FILTER="$2"; shift 2 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "${SKETCHBOARD}" ]; then
  echo '{"contested":[],"scanned_blocks":0,"heuristic_version":"v0.1-keyword","error":"sketchboard-not-found"}'
  exit 1
fi

# Delegate to Python — much cleaner JSON output than awk.
python3 - "${SKETCHBOARD}" "${EPOCH_FILTER}" <<'PYEOF'
import json
import re
import sys

sketchboard_path = sys.argv[1]
epoch_filter = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
epoch_filter = int(epoch_filter) if epoch_filter else None

# Trigger keywords. Adding to this list expands recall and false-positive rate.
TRIGGER_KEYWORDS = [
    "however", "disagree", "wrong", "incorrect", "not the case",
    "reject", "contradict", "but the framing", "but this",
]
TRIGGER_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in TRIGGER_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Parse Sketchboard.md into persona blocks within epoch sections.
# Block schema: { "persona": str, "epoch": int, "body": str }
blocks = []
with open(sketchboard_path) as f:
    lines = f.readlines()

current_epoch = None
in_epoch_section = False
current_persona = None
current_body = []


def flush_block():
    global current_persona, current_body
    if current_persona and current_epoch is not None:
        blocks.append({
            "persona": current_persona,
            "epoch": current_epoch,
            "body": "".join(current_body),
        })
    current_persona = None
    current_body = []


for line in lines:
    # ## Epoch <N>
    m = re.match(r"^## Epoch (\d+)\s*$", line)
    if m:
        flush_block()
        current_epoch = int(m.group(1))
        in_epoch_section = True
        continue

    # Other ## sections (Open Conflicts, Ratified Decisions, etc.) — exit epoch
    # Persona blocks have form "## <Name>:" with trailing colon. Other ## sections don't.
    if line.startswith("## ") and not line.rstrip().endswith(":"):
        flush_block()
        in_epoch_section = False
        continue

    # Persona block: ## <Name>:
    m = re.match(r"^## (.+?):\s*$", line)
    if m and in_epoch_section:
        flush_block()
        current_persona = m.group(1).strip()
        current_body = []
        continue

    # Body line accumulation
    if current_persona is not None:
        current_body.append(line)

flush_block()

# Pair up blocks within the same epoch and check for trigger keywords.
contested = []
seen_pairs = set()  # to avoid emitting (A,B) and (B,A) as duplicates
for i, a in enumerate(blocks):
    if epoch_filter is not None and a["epoch"] != epoch_filter:
        continue
    for j, b in enumerate(blocks):
        if i == j:
            continue
        if a["epoch"] != b["epoch"]:
            continue
        # Skip same-persona pairs: a persona contradicting their own prior block
        # is a refinement / concession, not a contested pair between personas.
        if a["persona"] == b["persona"]:
            continue
        if (a["persona"], b["persona"]) in seen_pairs:
            continue

        match = TRIGGER_RE.search(a["body"])
        if match:
            trigger_word = match.group(1).lower()
            # Snippet around the match
            start = max(0, match.start() - 40)
            end = min(len(a["body"]), match.end() + 120)
            snippet = a["body"][start:end].replace("\n", " ").strip()
            if len(snippet) > 200:
                snippet = snippet[:200]
            contested.append({
                "epoch": a["epoch"],
                "personas": [a["persona"], b["persona"]],
                "trigger": f"keyword:{trigger_word}",
                "evidence": snippet,
            })
            seen_pairs.add((a["persona"], b["persona"]))

result = {
    "contested": contested,
    "scanned_blocks": len(blocks),
    "heuristic_version": "v0.1-keyword",
}
print(json.dumps(result))
PYEOF
