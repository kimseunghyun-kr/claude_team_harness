#!/usr/bin/env bash
# test-deliberation-personas.sh
# 3-state coverage for the deliberation persona pack, per
# .claude/rules/active-watching-test-policy.md naming:
#   _Healthy        — all 3 declared personas resolve to existing files
#   _NotConfigured  — [deliberation].enabled = false → silent no-op (exit 0, healthy=true, reason="not-configured")
#   _Corrupted      — declared persona file missing → exit 1 with persona-file-missing error

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0

note() { echo "  → $1"; }
pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; echo "       $2"; }

# --- Test 1: TestPersonas_Healthy ---
echo "TestPersonas_Healthy"
note "verify all 3 declared personas have files under agents/personas/"

PERSONAS_TOML="$(awk '
  /^\[deliberation\]/ { in_section = 1; next }
  /^\[/ && !/^\[deliberation\]/ { in_section = 0 }
  in_section && /^personas[[:space:]]*=[[:space:]]*\[/ {
    in_array = 1; sub(/^personas[[:space:]]*=[[:space:]]*\[/, "")
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
      exit
    }
  }
' "${ROOT_DIR}/harness.toml")"

healthy_ok=true
healthy_reasons=""
while IFS= read -r persona_id; do
  [ -z "${persona_id}" ] && continue
  if [ ! -f "${ROOT_DIR}/agents/${persona_id}.md" ]; then
    healthy_ok=false
    healthy_reasons="${healthy_reasons} missing:${persona_id}"
  fi
done <<< "${PERSONAS_TOML}"

# Also: the shared contract docs must exist (kept under agents/personas/ as docs-only).
if [ ! -f "${ROOT_DIR}/agents/personas/_persona-contract.md" ]; then
  healthy_ok=false
  healthy_reasons="${healthy_reasons} missing:_persona-contract.md"
fi

if [ "${healthy_ok}" = true ]; then
  pass "TestPersonas_Healthy: all 3 declared personas + contract file present"
else
  fail "TestPersonas_Healthy" "Missing files:${healthy_reasons}"
fi

# --- Test 2: TestPersonas_NotConfigured ---
# When enabled=false (the default state), collect-bids.sh exits with a
# deliberation-disabled error JSON. This is the "opt-in not used" semantic
# per active-watching-test-policy.md: the system should not warn or page
# anyone — it should just say "not configured" cleanly.
echo "TestPersonas_NotConfigured"
note "verify enabled=false produces clean deliberation-disabled JSON without crashing"

# Read current enabled state. We don't mutate harness.toml in tests; we just
# verify the current default ships with enabled=false (which is the contract).
ENABLED_DEFAULT="$(awk '
  /^\[deliberation\]/ { in_section = 1; next }
  /^\[/ && !/^\[deliberation\]/ { in_section = 0 }
  in_section && /^enabled[[:space:]]*=/ {
    sub(/^enabled[[:space:]]*=[[:space:]]*/, "")
    sub(/[[:space:]]*#.*/, "")
    gsub(/[[:space:]]/, "")
    print
    exit
  }
' "${ROOT_DIR}/harness.toml")"

if [ "${ENABLED_DEFAULT}" != "false" ]; then
  fail "TestPersonas_NotConfigured" "harness.toml [deliberation].enabled must default to false; got '${ENABLED_DEFAULT}'"
else
  # Run collect-bids.sh — should exit 1 with deliberation-disabled error
  set +e
  OUTPUT="$(bash "${ROOT_DIR}/scripts/deliberate/collect-bids.sh" 1 1 2>&1)"
  EXIT_CODE=$?
  set -e

  if [ "${EXIT_CODE}" -ne 1 ]; then
    fail "TestPersonas_NotConfigured" "expected exit 1 when disabled; got ${EXIT_CODE}. output: ${OUTPUT}"
  elif ! echo "${OUTPUT}" | grep -q '"error":"deliberation-disabled"'; then
    fail "TestPersonas_NotConfigured" "expected error=deliberation-disabled; got: ${OUTPUT}"
  else
    pass "TestPersonas_NotConfigured: clean deliberation-disabled error when enabled=false"
  fi
fi

# --- Test 3: TestPersonas_Corrupted ---
# When a declared persona file is missing, collect-bids.sh must exit 1 with
# persona-file-missing error. Simulate by temporarily renaming a persona file.
echo "TestPersonas_Corrupted"
note "verify missing persona file triggers persona-file-missing error"

PERSONA_TO_HIDE="${ROOT_DIR}/agents/scaling-optimist.md"
HIDDEN_PATH="${PERSONA_TO_HIDE}.test-hidden"

# Need to flip enabled=true temporarily to reach the persona-file check
TEMP_TOML="$(mktemp)"
cp "${ROOT_DIR}/harness.toml" "${TEMP_TOML}"
trap 'mv "${TEMP_TOML}" "${ROOT_DIR}/harness.toml" 2>/dev/null; mv "${HIDDEN_PATH}" "${PERSONA_TO_HIDE}" 2>/dev/null; true' EXIT

# Patch harness.toml: enabled=true (we restore via trap)
sed -i.bak 's/^enabled = false/enabled = true/' "${ROOT_DIR}/harness.toml"
rm -f "${ROOT_DIR}/harness.toml.bak"

# Hide the persona file
mv "${PERSONA_TO_HIDE}" "${HIDDEN_PATH}"

set +e
OUTPUT="$(bash "${ROOT_DIR}/scripts/deliberate/collect-bids.sh" 1 1 2>&1)"
EXIT_CODE=$?
set -e

# Restore (also done by trap, but explicit here for clarity)
mv "${HIDDEN_PATH}" "${PERSONA_TO_HIDE}"
mv "${TEMP_TOML}" "${ROOT_DIR}/harness.toml"
trap - EXIT

if [ "${EXIT_CODE}" -ne 1 ]; then
  fail "TestPersonas_Corrupted" "expected exit 1; got ${EXIT_CODE}. output: ${OUTPUT}"
elif ! echo "${OUTPUT}" | grep -q '"error":"persona-file-missing"'; then
  fail "TestPersonas_Corrupted" "expected error=persona-file-missing; got: ${OUTPUT}"
  fail_detail="(persona file path now agents/<id>.md after Fix 1; check collect-bids.sh PERSONA_DIR)"
else
  pass "TestPersonas_Corrupted: persona-file-missing error when persona file removed"
fi

# --- Summary ---
echo ""
echo "TOTAL: PASS=${PASS} FAIL=${FAIL}"
[ "${FAIL}" -eq 0 ] || exit 1
