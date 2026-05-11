#!/usr/bin/env bash
# orchestrate-epoch.sh
# Run one epoch of the deliberation: per-slot bid → tally → spawn winner → commit.
# Closes when budget is exhausted or all personas bid 0 in the same slot.
#
# Note on agent spawning:
#   The actual Agent tool calls are made by the harness-deliberate SKILL from
#   within its Claude Code session, NOT by this script. This script handles:
#     - state machine (epoch.json transitions)
#     - bid log persistence
#     - tiebreaker logic
#     - close-conditions
#     - commit + tag
#   The skill consumes manifests from collect-bids.sh / spawn-winner.sh, makes
#   the spawns itself, and feeds results back to this orchestrator via stdin
#   when it calls "orchestrate-epoch.sh tally" and "... commit-or-forfeit".
#
# Subcommands:
#   init <question>               → create Sketchboard.md from template + begin epoch 1.
#                                    Refuses if Sketchboard.md exists or tree is dirty.
#   begin <epoch>                 → init state file, transition OPEN → COLLECTING
#   tally <epoch> <slot>          → read bid results from stdin (JSON array of bids),
#                                    select winner, update bid log, print
#                                    {"action":"close","reason":"all-abstain"} or
#                                    {"action":"spawn","persona":<id>,"bid":<f>,"reason":<s>}
#   commit-or-forfeit <epoch> <slot> <persona>
#                                → run postcheck via spawn-winner.sh; if pass, commit
#                                    and update state. If fail, revert and log forfeit.
#                                    Print {"committed":true|false,"close":<bool>}
#   close <epoch> <reason>        → tag epoch-N-unratified, set state=REVIEW
#   ratify                         → advance `ratified` ref to current epoch's unratified
#                                    tag, transition state to RATIFIED, then automatically
#                                    open the next epoch (state=COLLECTING).
#   status                         → print epoch.json contents

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${ROOT_DIR}/.claude/state/deliberation"
EPOCH_JSON="${STATE_DIR}/epoch.json"

mkdir -p "${STATE_DIR}"

bid_log_path() { echo "${STATE_DIR}/epoch-${1}-bids.jsonl"; }

read_state_field() {
  local field="$1"
  python3 -c "import json,sys; d=json.load(open('${EPOCH_JSON}')); print(d.get('${field}',''))" 2>/dev/null || echo ""
}

read_tiebreaker() {
  awk '
    /^\[deliberation\]/ { in_section = 1; next }
    /^\[/ && !/^\[deliberation\]/ { in_section = 0 }
    in_section && /^bid_tiebreaker[[:space:]]*=/ {
      sub(/^bid_tiebreaker[[:space:]]*=[[:space:]]*/, "")
      sub(/[[:space:]]*#.*/, "")
      gsub(/^[[:space:]]*"|"[[:space:]]*$/, "")
      print
      exit
    }
  ' "${ROOT_DIR}/harness.toml" | tr -d '"' | tr -d ' '
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
  ' "${ROOT_DIR}/harness.toml"
}

CMD="${1:-}"
shift || true

# Read sketchboard path from harness.toml
read_sketchboard_path() {
  awk '
    /^\[deliberation\]/ { in_section = 1; next }
    /^\[/ && !/^\[deliberation\]/ { in_section = 0 }
    in_section && /^sketchboard_path[[:space:]]*=/ {
      sub(/^sketchboard_path[[:space:]]*=[[:space:]]*/, "")
      sub(/[[:space:]]*#.*/, "")
      gsub(/[[:space:]]*"|"[[:space:]]*/, "")
      print
      exit
    }
  ' "${ROOT_DIR}/harness.toml" | tr -d '"' | tr -d ' '
}

case "${CMD}" in

  init)
    # Bundle: refuse if dirty tree or Sketchboard.md exists, then create from
    # template + begin epoch 1.
    QUESTION="${*:-}"
    if [ -z "${QUESTION}" ]; then
      echo '{"error":"usage: init <question>","hint":"the framing question for this deliberation"}' >&2
      exit 2
    fi
    SKETCHBOARD_PATH="$(read_sketchboard_path)"
    SKETCHBOARD_PATH="${SKETCHBOARD_PATH:-Sketchboard.md}"
    SKETCHBOARD_ABS="${ROOT_DIR}/${SKETCHBOARD_PATH}"

    cd "${ROOT_DIR}"
    if [ -f "${SKETCHBOARD_ABS}" ]; then
      echo "{\"error\":\"sketchboard-exists\",\"hint\":\"delete or rename ${SKETCHBOARD_PATH} first to start a fresh deliberation\"}"
      exit 1
    fi
    DIRTY="$(git status --porcelain | head -n 1 || true)"
    if [ -n "${DIRTY}" ]; then
      echo "{\"error\":\"dirty-tree\",\"hint\":\"commit or stash before init; orchestrator commits after each slot\"}"
      exit 1
    fi

    # Read personas from harness.toml and build the personas list block
    PERSONAS_BLOCK=""
    while IFS= read -r persona_line; do
      [ -z "${persona_line}" ] && continue
      PERSONAS_BLOCK="${PERSONAS_BLOCK}- ${persona_line}"$'\n'
    done < <(read_personas_array)

    # Substitute template
    TEMPLATE="${ROOT_DIR}/templates/Sketchboard.md.tmpl"
    if [ ! -f "${TEMPLATE}" ]; then
      echo '{"error":"template-missing","hint":"templates/Sketchboard.md.tmpl not found"}'
      exit 1
    fi
    python3 - <<PYEOF
import re
with open("${TEMPLATE}") as f:
    tmpl = f.read()
out = tmpl.replace("{{QUESTION}}", """${QUESTION}""")
out = out.replace("{{FRAME}}", "(chair to fill before run, or leave blank)")
out = out.replace("{{PERSONAS_LIST}}", """${PERSONAS_BLOCK}""".rstrip())
with open("${SKETCHBOARD_ABS}", "w") as f:
    f.write(out)
PYEOF

    # Commit the init
    git add "${SKETCHBOARD_PATH}"
    git commit -m "init(deliberation): epoch 1 — ${QUESTION}" --no-verify >/dev/null

    # Begin epoch 1
    "$0" begin 1 >/dev/null
    echo "{\"ok\":true,\"epoch\":1,\"state\":\"COLLECTING\",\"sketchboard_path\":\"${SKETCHBOARD_PATH}\",\"question\":\"$(printf '%s' "${QUESTION}" | sed 's/\\/\\\\/g; s/"/\\"/g')\"}"
    ;;

  begin)
    EPOCH="${1:-1}"
    cat > "${EPOCH_JSON}" <<EOF
{
  "epoch": ${EPOCH},
  "state": "COLLECTING",
  "budget": 5,
  "slots_used": 0,
  "close_reason": null,
  "personas": $(read_personas_array | python3 -c 'import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))'),
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "closed_at": null
}
EOF
    # Initialize empty bid log
    : > "$(bid_log_path "${EPOCH}")"
    echo "{\"ok\":true,\"epoch\":${EPOCH},\"state\":\"COLLECTING\"}"
    ;;

  tally)
    EPOCH="${1:-}"
    SLOT="${2:-}"
    if [ -z "${EPOCH}" ] || [ -z "${SLOT}" ]; then
      echo '{"error":"usage: tally <epoch> <slot>"}' >&2
      exit 2
    fi

    # Read bid results from stdin: JSON array
    # [{"persona":"a","bid":0.8,"reason":"..."},{"persona":"b","bid":0.0,"reason":"..."}, ...]
    BIDS_JSON="$(cat)"

    TIEBREAKER="$(read_tiebreaker)"
    TIEBREAKER="${TIEBREAKER:-declaration-order}"

    # Append every bid to the bid log
    LOG_PATH="$(bid_log_path "${EPOCH}")"
    python3 - <<PYEOF
import json, sys
bids = json.loads('''${BIDS_JSON}''')
slot = ${SLOT}
with open('${LOG_PATH}', 'a') as f:
    for b in bids:
        rec = {"slot": slot, "persona": b["persona"], "bid": float(b["bid"]),
               "reason": b.get("reason", ""), "won": False}
        f.write(json.dumps(rec) + "\n")
PYEOF

    # Select winner using Python (cleaner than shell for this)
    PERSONAS_ORDER="$(read_personas_array | python3 -c 'import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))')"

    python3 - <<PYEOF
import json, sys, random
bids = json.loads('''${BIDS_JSON}''')
order = json.loads('''${PERSONAS_ORDER}''')
tiebreaker = "${TIEBREAKER}"
slot = ${SLOT}
epoch = ${EPOCH}

active = [b for b in bids if float(b["bid"]) > 0.0]
if not active:
    print(json.dumps({"action": "close", "reason": "all-abstain"}))
    sys.exit(0)

max_bid = max(float(b["bid"]) for b in active)
tied = [b for b in active if float(b["bid"]) == max_bid]

if len(tied) == 1:
    winner = tied[0]
elif tiebreaker == "declaration-order":
    order_idx = {p: i for i, p in enumerate(order)}
    winner = min(tied, key=lambda b: order_idx.get(b["persona"], 999))
elif tiebreaker == "random":
    rng = random.Random(f"{epoch}:{slot}")
    winner = rng.choice(tied)
else:
    # unknown tiebreaker → fall back to declaration-order
    order_idx = {p: i for i, p in enumerate(order)}
    winner = min(tied, key=lambda b: order_idx.get(b["persona"], 999))

print(json.dumps({
    "action": "spawn",
    "persona": winner["persona"],
    "bid": float(winner["bid"]),
    "reason": winner.get("reason", ""),
}))

# Mark winner in bid log (rewrite the slot entries with won: true for winner)
log_path = "${LOG_PATH}"
with open(log_path) as f:
    lines = [json.loads(l) for l in f if l.strip()]
for rec in lines:
    if rec["slot"] == slot and rec["persona"] == winner["persona"]:
        rec["won"] = True
with open(log_path, "w") as f:
    for rec in lines:
        f.write(json.dumps(rec) + "\n")
PYEOF
    ;;

  commit-or-forfeit)
    EPOCH="${1:-}"
    SLOT="${2:-}"
    PERSONA="${3:-}"
    if [ -z "${EPOCH}" ] || [ -z "${SLOT}" ] || [ -z "${PERSONA}" ]; then
      echo '{"error":"usage: commit-or-forfeit <epoch> <slot> <persona>"}' >&2
      exit 2
    fi

    POSTCHECK_RESULT="$(bash "${ROOT_DIR}/scripts/deliberate/spawn-winner.sh" postcheck "${PERSONA}" "${EPOCH}")"
    POSTCHECK_OK="$(echo "${POSTCHECK_RESULT}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("ok", False))')"

    if [ "${POSTCHECK_OK}" = "True" ]; then
      cd "${ROOT_DIR}"
      git add Sketchboard.md
      git commit -m "epoch-${EPOCH} slot-${SLOT}: ${PERSONA}" >/dev/null
      # Update slots_used in epoch.json
      python3 - <<PYEOF
import json
p = "${EPOCH_JSON}"
d = json.load(open(p))
d["slots_used"] = ${SLOT}
json.dump(d, open(p, "w"), indent=2)
PYEOF
      echo "{\"committed\":true,\"slot\":${SLOT},\"persona\":\"${PERSONA}\"}"
    else
      cd "${ROOT_DIR}"
      git checkout -- Sketchboard.md
      # Annotate the bid log with forfeit
      LOG_PATH="$(bid_log_path "${EPOCH}")"
      FAIL_REASON="$(echo "${POSTCHECK_RESULT}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("failure", "unknown"))')"
      python3 - <<PYEOF
import json
log = "${LOG_PATH}"
with open(log) as f:
    lines = [json.loads(l) for l in f if l.strip()]
for rec in lines:
    if rec["slot"] == ${SLOT} and rec["persona"] == "${PERSONA}" and rec.get("won"):
        rec["forfeit"] = True
        rec["postcheck_failure"] = "${FAIL_REASON}"
with open(log, "w") as f:
    for rec in lines:
        f.write(json.dumps(rec) + "\n")
PYEOF
      echo "{\"committed\":false,\"slot\":${SLOT},\"persona\":\"${PERSONA}\",\"failure\":\"${FAIL_REASON}\"}"
    fi
    ;;

  close)
    EPOCH="${1:-}"
    REASON="${2:-budget-exhausted}"
    if [ -z "${EPOCH}" ]; then
      echo '{"error":"usage: close <epoch> [reason]"}' >&2
      exit 2
    fi
    cd "${ROOT_DIR}"
    git tag "epoch-${EPOCH}-unratified" 2>/dev/null || true
    python3 - <<PYEOF
import json, datetime
p = "${EPOCH_JSON}"
d = json.load(open(p))
d["state"] = "REVIEW"
d["close_reason"] = "${REASON}"
d["closed_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump(d, open(p, "w"), indent=2)
PYEOF
    echo "{\"closed\":true,\"epoch\":${EPOCH},\"reason\":\"${REASON}\",\"tag\":\"epoch-${EPOCH}-unratified\"}"
    ;;

  ratify)
    # Advance the `ratified` ref to the current epoch's unratified tag, set
    # state RATIFIED, then automatically open the next epoch (state COLLECTING).
    if [ ! -f "${EPOCH_JSON}" ]; then
      echo '{"error":"no-active-deliberation","hint":"call init first"}'
      exit 1
    fi
    CUR_EPOCH="$(python3 -c "import json; print(json.load(open('${EPOCH_JSON}'))['epoch'])")"
    CUR_STATE="$(python3 -c "import json; print(json.load(open('${EPOCH_JSON}'))['state'])")"
    if [ "${CUR_STATE}" != "REVIEW" ]; then
      echo "{\"error\":\"wrong-state\",\"current\":\"${CUR_STATE}\",\"hint\":\"ratify only valid in REVIEW state; epoch ${CUR_EPOCH} is in ${CUR_STATE}\"}"
      exit 1
    fi

    cd "${ROOT_DIR}"
    TAG="epoch-${CUR_EPOCH}-unratified"
    if ! git rev-parse "${TAG}" >/dev/null 2>&1; then
      echo "{\"error\":\"missing-tag\",\"tag\":\"${TAG}\"}"
      exit 1
    fi
    git update-ref refs/heads/ratified "$(git rev-parse "${TAG}")"
    RATIFIED_SHA="$(git rev-parse --short ratified)"

    # Append a new ## Epoch <N+1> section to Sketchboard.md so personas can write into it.
    NEXT_EPOCH=$((CUR_EPOCH + 1))
    SKETCHBOARD_PATH="$(read_sketchboard_path)"
    SKETCHBOARD_PATH="${SKETCHBOARD_PATH:-Sketchboard.md}"
    python3 - <<PYEOF
import re
path = "${ROOT_DIR}/${SKETCHBOARD_PATH}"
with open(path) as f:
    content = f.read()

# Insert "## Epoch <NEXT_EPOCH>" section just before "## Open Conflicts"
next_section = f"\n## Epoch ${NEXT_EPOCH}\n\n<!-- Persona blocks for epoch ${NEXT_EPOCH} accumulate below. -->\n\n---\n"
if re.search(r"^## Open Conflicts", content, flags=re.MULTILINE):
    content = re.sub(r"(\n## Open Conflicts)", next_section + r"\1", content, count=1)
else:
    content += next_section

with open(path, "w") as f:
    f.write(content)
PYEOF
    git add "${SKETCHBOARD_PATH}"
    git commit -m "ratify(deliberation): epoch ${CUR_EPOCH} ratified → open epoch ${NEXT_EPOCH}" --no-verify >/dev/null

    # Update state to RATIFIED, then immediately advance epoch counter
    python3 - <<PYEOF
import json, datetime
p = "${EPOCH_JSON}"
d = json.load(open(p))
d["state"] = "RATIFIED"
d["ratified_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
# Immediately open the next epoch
d["epoch"] = ${NEXT_EPOCH}
d["state"] = "COLLECTING"
d["slots_used"] = 0
d["close_reason"] = None
d["started_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
d["closed_at"] = None
json.dump(d, open(p, "w"), indent=2)
PYEOF
    # Fresh bid log for next epoch
    : > "$(bid_log_path "${NEXT_EPOCH}")"

    echo "{\"ratified_epoch\":${CUR_EPOCH},\"ratified_sha\":\"${RATIFIED_SHA}\",\"next_epoch\":${NEXT_EPOCH},\"state\":\"COLLECTING\"}"
    ;;

  status)
    if [ -f "${EPOCH_JSON}" ]; then
      cat "${EPOCH_JSON}"
    else
      echo '{"error":"no-active-deliberation","hint":"call /harness-deliberate init first"}'
      exit 1
    fi
    ;;

  *)
    echo '{"error":"usage: orchestrate-epoch.sh (begin|tally|commit-or-forfeit|close|status) ..."}' >&2
    exit 2
    ;;
esac
