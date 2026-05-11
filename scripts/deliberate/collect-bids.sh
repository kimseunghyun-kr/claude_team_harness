#!/usr/bin/env bash
# collect-bids.sh
# Spawn each persona in BID mode (read-only, parallel) and collect their bids.
#
# v0.1 implementation note:
#   The Agent tool is invoked from within a Claude Code session, not from a shell
#   directly. This script is therefore a *thin wrapper* that the harness-deliberate
#   skill calls FROM ITS OWN SESSION via the Agent tool. The script's job is:
#     - validate inputs (epoch, slot, sketchboard path)
#     - read [deliberation].personas from harness.toml
#     - print a JSON spawn manifest the skill consumes to issue parallel Agent calls
#   The actual Agent spawning is done by the skill, not by shell.
#
#   This separation keeps the orchestration testable: tests can call this script
#   with a mocked harness.toml and verify the manifest, without needing to spawn
#   real agents.
#
# Usage:
#   bash scripts/deliberate/collect-bids.sh <epoch> <slot>
#
# Output (stdout, JSON):
#   {
#     "epoch": <N>,
#     "slot": <S>,
#     "sketchboard_path": "Sketchboard.md",
#     "personas": ["scaling-optimist", ...],
#     "spawns": [
#       {
#         "subagent_type": "scaling-optimist",
#         "prompt": "mode=BID\nepoch=<N>\nslot=<S>\nsketchboard_path=<path>\n..."
#       }, ...
#     ]
#   }
#
# Stop conditions (exit 1 with JSON {"error": "<reason>"}):
#   - harness.toml [deliberation].enabled = false
#   - personas[] is empty or has < 2 entries
#   - any declared persona file is missing under agents/personas/
#   - Sketchboard.md is missing

set -euo pipefail

EPOCH="${1:-}"
SLOT="${2:-}"

if [ -z "${EPOCH}" ] || [ -z "${SLOT}" ]; then
  echo '{"error":"usage: collect-bids.sh <epoch> <slot>"}' >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HARNESS_TOML="${ROOT_DIR}/harness.toml"
PERSONA_DIR="${ROOT_DIR}/agents/personas"

# --- Read [deliberation] block from harness.toml --------------------------
# We use a minimal awk parser (no python/jq dependency for this hot path).
# Limitation: only supports flat scalars and string arrays in the [deliberation]
# section. Robust enough for v0.1 since we control the schema.

read_deliberation_field() {
  local field="$1"
  awk -v field="${field}" '
    /^\[deliberation\]/ { in_section = 1; next }
    /^\[/ && !/^\[deliberation\]/ { in_section = 0 }
    in_section && $0 ~ "^"field"[[:space:]]*=" {
      sub("^"field"[[:space:]]*=[[:space:]]*", "")
      sub(/[[:space:]]*#.*/, "")
      print
      exit
    }
  ' "${HARNESS_TOML}"
}

read_personas_array() {
  awk '
    /^\[deliberation\]/ { in_section = 1; next }
    /^\[/ && !/^\[deliberation\]/ { in_section = 0 }
    in_section && /^personas[[:space:]]*=[[:space:]]*\[/ {
      in_array = 1
      sub(/^personas[[:space:]]*=[[:space:]]*\[/, "")
    }
    in_array {
      buf = buf " " $0
      if (match(buf, /\]/)) {
        sub(/\].*$/, "", buf)
        gsub(/[[:space:]]*"/, "\"", buf)
        n = split(buf, items, ",")
        for (i = 1; i <= n; i++) {
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", items[i])
          gsub(/^"|"$/, "", items[i])
          if (items[i] != "") print items[i]
        }
        in_array = 0
        exit
      }
    }
  ' "${HARNESS_TOML}"
}

ENABLED="$(read_deliberation_field 'enabled' | tr -d ' ')"
SKETCHBOARD_PATH="$(read_deliberation_field 'sketchboard_path' | tr -d ' "')"
SKETCHBOARD_PATH="${SKETCHBOARD_PATH:-Sketchboard.md}"

if [ "${ENABLED}" != "true" ]; then
  echo '{"error":"deliberation-disabled","hint":"set [deliberation].enabled = true in harness.toml"}'
  exit 1
fi

# Validate config BEFORE runtime state. A missing persona file is a config bug;
# a missing Sketchboard.md is a "you forgot to call /harness-deliberate init"
# runtime state. Surface config bugs first.

# Collect persona ids (sequential to preserve declaration order).
# Use a read loop instead of mapfile for bash 3.2 compat (macOS default shell).
PERSONAS=()
while IFS= read -r persona_line; do
  [ -z "${persona_line}" ] && continue
  PERSONAS+=("${persona_line}")
done < <(read_personas_array)

if [ "${#PERSONAS[@]}" -lt 2 ]; then
  echo "{\"error\":\"insufficient-personas\",\"count\":${#PERSONAS[@]},\"hint\":\"need >= 2\"}"
  exit 1
fi

# Validate every persona file exists
for p in "${PERSONAS[@]}"; do
  if [ ! -f "${PERSONA_DIR}/${p}.md" ]; then
    echo "{\"error\":\"persona-file-missing\",\"persona\":\"${p}\",\"expected_path\":\"agents/personas/${p}.md\"}"
    exit 1
  fi
done

# Now check runtime state
if [ ! -f "${ROOT_DIR}/${SKETCHBOARD_PATH}" ]; then
  echo "{\"error\":\"sketchboard-missing\",\"path\":\"${SKETCHBOARD_PATH}\"}"
  exit 1
fi

# --- Build spawn manifest --------------------------------------------------

printf '{"epoch":%d,"slot":%d,"sketchboard_path":"%s","personas":[' \
  "${EPOCH}" "${SLOT}" "${SKETCHBOARD_PATH}"

for i in "${!PERSONAS[@]}"; do
  if [ "${i}" -gt 0 ]; then printf ","; fi
  printf '"%s"' "${PERSONAS[$i]}"
done

printf '],"spawns":['

for i in "${!PERSONAS[@]}"; do
  if [ "${i}" -gt 0 ]; then printf ","; fi
  PROMPT="mode=BID\\nepoch=${EPOCH}\\nslot=${SLOT}\\nsketchboard_path=${SKETCHBOARD_PATH}\\nprior_bids_visible=false"
  printf '{"subagent_type":"%s","prompt":"%s"}' \
    "${PERSONAS[$i]}" "${PROMPT}"
done

printf ']}\n'
