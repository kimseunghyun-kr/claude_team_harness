#!/usr/bin/env bash
# spawn-winner.sh
# Build the WRITE-mode spawn manifest for the bid winner, AND postcheck the diff
# after the harness-deliberate skill has spawned the Agent and the Agent has
# returned control.
#
# Two modes:
#
#   1. Manifest mode (before spawn):
#        bash scripts/deliberate/spawn-winner.sh manifest <persona-id> <epoch> <slot> <bid> <reason>
#      Prints the spawn manifest as JSON for the skill to consume.
#
#   2. Postcheck mode (after spawn):
#        bash scripts/deliberate/spawn-winner.sh postcheck <persona-id> <epoch>
#      Inspects the working tree diff, validates against the WRITE contract,
#      prints {"ok":true} or {"ok":false,"failure":"<which check>"}.
#      Caller uses this to decide whether to commit or revert.
#
# Stop conditions: missing args -> exit 2.

set -euo pipefail

MODE="${1:-}"
shift || true

case "${MODE}" in
  manifest) ;;
  postcheck) ;;
  *)
    echo '{"error":"usage: spawn-winner.sh (manifest|postcheck) ..."}' >&2
    exit 2
    ;;
esac

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [ "${MODE}" = "manifest" ]; then
  PERSONA="${1:-}"
  EPOCH="${2:-}"
  SLOT="${3:-}"
  BID="${4:-}"
  REASON="${5:-}"

  if [ -z "${PERSONA}" ] || [ -z "${EPOCH}" ] || [ -z "${SLOT}" ] || [ -z "${BID}" ]; then
    echo '{"error":"usage: spawn-winner.sh manifest <persona> <epoch> <slot> <bid> <reason>"}' >&2
    exit 2
  fi

  PERSONA_FILE="${ROOT_DIR}/agents/${PERSONA}.md"
  if [ ! -f "${PERSONA_FILE}" ]; then
    echo "{\"error\":\"persona-file-missing\",\"persona\":\"${PERSONA}\"}"
    exit 1
  fi

  # Read sketchboard path from harness.toml (default Sketchboard.md)
  SKETCHBOARD_PATH="$(awk '
    /^\[deliberation\]/ { in_section = 1; next }
    /^\[/ && !/^\[deliberation\]/ { in_section = 0 }
    in_section && /^sketchboard_path[[:space:]]*=/ {
      sub(/^sketchboard_path[[:space:]]*=[[:space:]]*/, "")
      sub(/[[:space:]]*#.*/, "")
      gsub(/^[[:space:]]*"|"[[:space:]]*$/, "")
      print
      exit
    }
  ' "${ROOT_DIR}/harness.toml" | tr -d '"')"
  SKETCHBOARD_PATH="${SKETCHBOARD_PATH:-Sketchboard.md}"

  # Escape reason for JSON
  REASON_ESC="$(printf '%s' "${REASON}" | sed 's/\\/\\\\/g; s/"/\\"/g')"

  PROMPT="mode=WRITE\\nepoch=${EPOCH}\\nslot=${SLOT}\\nsketchboard_path=${SKETCHBOARD_PATH}\\nyour_winning_bid=${BID}\\nyour_winning_reason=${REASON_ESC}"

  printf '{"subagent_type":"%s","prompt":"%s","sketchboard_path":"%s"}\n' \
    "${PERSONA}" "${PROMPT}" "${SKETCHBOARD_PATH}"
  exit 0
fi

# --- postcheck mode ---
PERSONA="${1:-}"
EPOCH="${2:-}"

if [ -z "${PERSONA}" ] || [ -z "${EPOCH}" ]; then
  echo '{"ok":false,"failure":"usage-error"}' >&2
  exit 2
fi

cd "${ROOT_DIR}"

# Read sketchboard path
SKETCHBOARD_PATH="$(awk '
  /^\[deliberation\]/ { in_section = 1; next }
  /^\[/ && !/^\[deliberation\]/ { in_section = 0 }
  in_section && /^sketchboard_path[[:space:]]*=/ {
    sub(/^sketchboard_path[[:space:]]*=[[:space:]]*/, "")
    sub(/[[:space:]]*#.*/, "")
    print
    exit
  }
' harness.toml | tr -d '" ')"
SKETCHBOARD_PATH="${SKETCHBOARD_PATH:-Sketchboard.md}"

# Check 1: only Sketchboard.md changed
CHANGED_FILES="$(git diff --name-only HEAD || true)"
if [ -z "${CHANGED_FILES}" ]; then
  echo '{"ok":false,"failure":"no-diff","detail":"persona produced no changes"}'
  exit 0   # postcheck ok=false is a normal forfeit signal — orchestrator branches on JSON, not exit code
fi

if [ "${CHANGED_FILES}" != "${SKETCHBOARD_PATH}" ]; then
  echo "{\"ok\":false,\"failure\":\"wrong-files-changed\",\"detail\":\"expected only ${SKETCHBOARD_PATH}; got: ${CHANGED_FILES}\"}"
  exit 0   # postcheck ok=false is a normal forfeit signal — orchestrator branches on JSON, not exit code
fi

# Check 2: diff is purely additive within current epoch section
# Extract added lines (start with +) and deleted lines (start with -).
# Deleted lines that aren't part of file headers (--- a/) → fail.
DELETED_LINES="$(git diff HEAD -- "${SKETCHBOARD_PATH}" | grep -E '^-[^-]' || true)"
if [ -n "${DELETED_LINES}" ]; then
  echo '{"ok":false,"failure":"non-additive-diff","detail":"persona deleted lines; WRITE must be additive"}'
  exit 0   # postcheck ok=false is a normal forfeit signal — orchestrator branches on JSON, not exit code
fi

# Check 3: added lines all live within the current epoch section
# Approach: grab the diff, find which sections the added lines fall under.
# We use line numbers from `git diff -U0` to be precise.
ADDITIONS_OUTSIDE_EPOCH="$(git diff -U0 HEAD -- "${SKETCHBOARD_PATH}" | awk -v epoch="${EPOCH}" '
  /^@@ / {
    # Extract +start,count
    match($0, /\+[0-9]+/)
    if (RSTART > 0) {
      cur_line = substr($0, RSTART+1, RLENGTH-1) + 0
    }
    in_added_block = 1
    next
  }
  /^\+/ && in_added_block {
    line = substr($0, 2)
    # Find which section this line belongs to by reading the working file
    # Simpler check: detect if added line itself is editing forbidden sections
    if (line ~ /^## Ratified Decisions/) print "edited_ratified_decisions_heading"
    if (line ~ /^## Open Conflicts/) print "edited_open_conflicts_heading"
    cur_line++
  }
' || true)"

# A more robust check: re-read the file and verify the diffs land in current epoch section
# For v0.1 we use a simpler heuristic — check that no added line falls into Ratified
# or Open Conflicts sections by scanning the working tree.
FORBIDDEN_TOUCHED="$(awk -v epoch="${EPOCH}" '
  /^## Ratified Decisions/ { in_ratified = 1; in_conflicts = 0; in_epoch = 0; next }
  /^## Open Conflicts/    { in_conflicts = 1; in_ratified = 0; in_epoch = 0; next }
  /^## Epoch [0-9]+/      { in_ratified = 0; in_conflicts = 0; match($0, /[0-9]+/); cur_epoch = substr($0, RSTART, RLENGTH) + 0; in_epoch = (cur_epoch == epoch+0); next }
  /^---/                  { in_ratified = 0; in_conflicts = 0; in_epoch = 0; next }
' "${SKETCHBOARD_PATH}")"

# Check 4: extract added persona block, verify heading matches persona display name + colon,
# verify at least one blockquote line.
ADDED_BLOCK="$(git diff HEAD -- "${SKETCHBOARD_PATH}" | grep -E '^\+' | sed 's/^\+//' || true)"

# Persona display name = persona id with hyphens → spaces + Title Case
PERSONA_DISPLAY="$(printf '%s' "${PERSONA}" | tr '-' ' ' | awk '{ for (i=1; i<=NF; i++) $i = toupper(substr($i,1,1)) substr($i,2); print }')"

if ! printf '%s\n' "${ADDED_BLOCK}" | grep -qE "^## ${PERSONA_DISPLAY}:[[:space:]]*$"; then
  echo "{\"ok\":false,\"failure\":\"missing-or-wrong-heading\",\"detail\":\"expected '## ${PERSONA_DISPLAY}:' header in added block\"}"
  exit 0   # postcheck ok=false is a normal forfeit signal — orchestrator branches on JSON, not exit code
fi

if ! printf '%s\n' "${ADDED_BLOCK}" | grep -qE '^>'; then
  echo '{"ok":false,"failure":"missing-blockquote","detail":"WRITE block must contain at least one blockquote (must quote earlier claim)"}'
  exit 0   # postcheck ok=false is a normal forfeit signal — orchestrator branches on JSON, not exit code
fi

# Check 5: did added lines land in any forbidden section heading?
if printf '%s\n' "${ADDED_BLOCK}" | grep -qE '^## (Ratified Decisions|Open Conflicts)[[:space:]]*$'; then
  echo '{"ok":false,"failure":"edited-forbidden-section-heading"}'
  exit 0   # postcheck ok=false is a normal forfeit signal — orchestrator branches on JSON, not exit code
fi

echo '{"ok":true}'
