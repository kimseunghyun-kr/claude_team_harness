#!/usr/bin/env bash
# test-deliberation-bidding.sh
# Verify the bidding mechanics in scripts/deliberate/orchestrate-epoch.sh tally:
#   1. Highest bid wins
#   2. Tied bids broken by declaration order (per harness.toml personas[] order)
#   3. All-abstain (every bid 0.0) returns close action
#   4. Single non-zero bid wins even if tied with zeros

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR="${ROOT_DIR}/scripts/deliberate/orchestrate-epoch.sh"
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; echo "       $2"; }

# Set up isolated state dir for the test (don't pollute real .claude/state)
TEST_STATE="$(mktemp -d)"
trap 'rm -rf "${TEST_STATE}"' EXIT
export STATE_DIR="${TEST_STATE}"  # not actually consumed; orchestrator hardcodes path
# Instead, we'll create a fresh epoch.json in the real path but clean it after.
REAL_STATE_DIR="${ROOT_DIR}/.claude/state/deliberation"
mkdir -p "${REAL_STATE_DIR}"
EPOCH_TEST=99    # use a high number to avoid collision

cleanup() {
  rm -f "${REAL_STATE_DIR}/epoch-${EPOCH_TEST}-bids.jsonl"
  # Restore epoch.json if we touched it
  if [ -f "${REAL_STATE_DIR}/epoch.json.test-bak" ]; then
    mv "${REAL_STATE_DIR}/epoch.json.test-bak" "${REAL_STATE_DIR}/epoch.json"
  elif [ -f "${REAL_STATE_DIR}/epoch.json" ] && [ "$(jq -r '.epoch' "${REAL_STATE_DIR}/epoch.json" 2>/dev/null || echo "")" = "${EPOCH_TEST}" ]; then
    rm -f "${REAL_STATE_DIR}/epoch.json"
  fi
  rm -rf "${TEST_STATE}"
}
trap cleanup EXIT

# Backup any existing epoch.json
if [ -f "${REAL_STATE_DIR}/epoch.json" ]; then
  cp "${REAL_STATE_DIR}/epoch.json" "${REAL_STATE_DIR}/epoch.json.test-bak"
fi

# Initialize a fresh test epoch via the orchestrator. We need [deliberation].enabled=true
# for begin to populate personas[] correctly — but the begin command doesn't actually
# require enabled=true (it just reads personas). So we proceed.
bash "${ORCHESTRATOR}" begin "${EPOCH_TEST}" >/dev/null

# --- Test 1: highest bid wins (no tie) ---
echo "TestBidding_HighestWins"
BIDS_T1='[
  {"persona":"scaling-optimist","bid":0.30,"reason":"r1"},
  {"persona":"architecture-skeptic","bid":0.85,"reason":"r2"},
  {"persona":"bias-auditor","bid":0.50,"reason":"r3"}
]'
RESULT_T1="$(echo "${BIDS_T1}" | bash "${ORCHESTRATOR}" tally "${EPOCH_TEST}" 1)"
WINNER_T1="$(echo "${RESULT_T1}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("persona",""))')"

if [ "${WINNER_T1}" = "architecture-skeptic" ]; then
  pass "TestBidding_HighestWins: architecture-skeptic (bid 0.85) wins"
else
  fail "TestBidding_HighestWins" "expected architecture-skeptic; got '${WINNER_T1}'. result: ${RESULT_T1}"
fi

# --- Test 2: tied bids broken by declaration order ---
# personas[] in harness.toml = [scaling-optimist, architecture-skeptic, bias-auditor]
# So if scaling-optimist and architecture-skeptic both bid 0.75, scaling-optimist wins.
echo "TestBidding_TieBrokenByDeclarationOrder"
BIDS_T2="$(cat "${ROOT_DIR}/tests/fixtures/bids-tied.json")"
RESULT_T2="$(echo "${BIDS_T2}" | bash "${ORCHESTRATOR}" tally "${EPOCH_TEST}" 2)"
WINNER_T2="$(echo "${RESULT_T2}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("persona",""))')"

# Fixture bids: architecture-skeptic 0.75, scaling-optimist 0.75 (tied), bias-auditor 0.30
# Declaration order: scaling-optimist first → wins
if [ "${WINNER_T2}" = "scaling-optimist" ]; then
  pass "TestBidding_TieBrokenByDeclarationOrder: scaling-optimist wins tie at 0.75 (declared before architecture-skeptic)"
else
  fail "TestBidding_TieBrokenByDeclarationOrder" "expected scaling-optimist; got '${WINNER_T2}'. result: ${RESULT_T2}"
fi

# --- Test 3: all-abstain returns close action ---
echo "TestBidding_AllAbstainCloses"
BIDS_T3='[
  {"persona":"scaling-optimist","bid":0.0,"reason":"nothing to add"},
  {"persona":"architecture-skeptic","bid":0.0,"reason":"already made my point"},
  {"persona":"bias-auditor","bid":0.0,"reason":"deliberation healthy"}
]'
RESULT_T3="$(echo "${BIDS_T3}" | bash "${ORCHESTRATOR}" tally "${EPOCH_TEST}" 3)"
ACTION_T3="$(echo "${RESULT_T3}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("action",""))')"
REASON_T3="$(echo "${RESULT_T3}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("reason",""))')"

if [ "${ACTION_T3}" = "close" ] && [ "${REASON_T3}" = "all-abstain" ]; then
  pass "TestBidding_AllAbstainCloses: all-zero bids → action=close, reason=all-abstain"
else
  fail "TestBidding_AllAbstainCloses" "expected action=close reason=all-abstain; got action=${ACTION_T3} reason=${REASON_T3}. result: ${RESULT_T3}"
fi

# --- Test 4: single non-zero bid wins even if others abstain ---
echo "TestBidding_SingleActiveBidWins"
BIDS_T4='[
  {"persona":"scaling-optimist","bid":0.0,"reason":"nothing"},
  {"persona":"architecture-skeptic","bid":0.0,"reason":"nothing"},
  {"persona":"bias-auditor","bid":0.20,"reason":"flagging mild echo"}
]'
RESULT_T4="$(echo "${BIDS_T4}" | bash "${ORCHESTRATOR}" tally "${EPOCH_TEST}" 4)"
WINNER_T4="$(echo "${RESULT_T4}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("persona",""))')"

if [ "${WINNER_T4}" = "bias-auditor" ]; then
  pass "TestBidding_SingleActiveBidWins: bias-auditor with bid 0.20 wins despite low score (only active bidder)"
else
  fail "TestBidding_SingleActiveBidWins" "expected bias-auditor; got '${WINNER_T4}'. result: ${RESULT_T4}"
fi

# --- Summary ---
echo ""
echo "TOTAL: PASS=${PASS} FAIL=${FAIL}"
[ "${FAIL}" -eq 0 ] || exit 1
