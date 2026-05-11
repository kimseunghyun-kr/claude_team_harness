#!/usr/bin/env bash
# test-sketchboard-conflict-detection.sh
# Adversarial coverage for scripts/deliberate/detect-contested.sh.
#
# v0.1 heuristic is keyword-based; this test pins down BOTH what the heuristic
# correctly flags AND what it gets wrong (false positives + false negatives) so
# the v0.2 LLM-based stance classifier has a clear regression target — exactly
# 2 of these 4 assertions flip on the v0.2 upgrade.
#
# Per .claude/rules/test-quality.md: these assertions are NOT test tampering.
# They document the v0.1 heuristic's actual behavior; the heuristic is named in
# the test as "v0.1-keyword" so the gap is explicit, not hidden.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DETECT="${ROOT_DIR}/scripts/deliberate/detect-contested.sh"
FIXTURES="${ROOT_DIR}/tests/fixtures"
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; echo "       $2"; }

count_contested() {
  local fixture="$1"
  bash "${DETECT}" "${fixture}" --epoch 1 \
    | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("contested",[])))'
}

# --- Case A: TestContested_ObviousContested (true positive) ---
# Fixture has explicit "I disagree", "this is wrong", "However" in mutually
# rebutting blocks. Heuristic must flag.
echo "TestContested_ObviousContested"
COUNT_A="$(count_contested "${FIXTURES}/sketchboard-contested-obvious.md")"
if [ "${COUNT_A}" -ge 1 ]; then
  pass "TestContested_ObviousContested: heuristic correctly flags ${COUNT_A} contested pair(s) on obvious fixture"
else
  fail "TestContested_ObviousContested" "expected ≥1 contested pair; heuristic returned 0. fixture has explicit disagree/however/wrong keywords."
fi

# --- Case B: TestContested_ObviousUncontested (true negative) ---
# Fixture has two complementary blocks with no trigger keywords. Heuristic must NOT flag.
echo "TestContested_ObviousUncontested"
COUNT_B="$(count_contested "${FIXTURES}/sketchboard-uncontested-obvious.md")"
if [ "${COUNT_B}" -eq 0 ]; then
  pass "TestContested_ObviousUncontested: heuristic correctly does not flag complementary blocks (count=0)"
else
  fail "TestContested_ObviousUncontested" "expected 0 contested pairs on uncontested fixture; got ${COUNT_B}"
fi

# --- Case C: TestContested_NoKeywords_KnownFalseNegative (v0.1 limit) ---
# Fixture has semantic contradiction (compute vs data quality as binding constraint)
# WITHOUT trigger keywords. The v0.1 heuristic cannot detect this and is EXPECTED to miss.
# This assertion documents the gap. v0.2 stance classifier flips this to ≥1.
echo "TestContested_NoKeywords_KnownFalseNegative"
COUNT_C="$(count_contested "${FIXTURES}/sketchboard-contested-no-keywords.md")"
if [ "${COUNT_C}" -eq 0 ]; then
  pass "TestContested_NoKeywords_KnownFalseNegative: v0.1 heuristic misses semantic contradiction without keywords (expected; documents v0.1 gap)"
else
  fail "TestContested_NoKeywords_KnownFalseNegative" "v0.1 heuristic should NOT flag this fixture (no trigger keywords present); got ${COUNT_C}. Either the heuristic gained capability (good — update this assertion) or fixture leaked keywords (fix fixture)."
fi

# --- Case D: TestContested_KeywordsWithoutContradiction_KnownFalsePositive (v0.1 limit) ---
# Fixture has architecture-skeptic block using "however", "I agree", "I disagree", "but" —
# but the substantive content AGREES with the optimist. The v0.1 heuristic flags
# any block containing trigger keywords, so this is a false positive.
# This assertion documents the gap. v0.2 stance classifier flips this to 0.
echo "TestContested_KeywordsWithoutContradiction_KnownFalsePositive"
COUNT_D="$(count_contested "${FIXTURES}/sketchboard-uncontested-with-keywords.md")"
if [ "${COUNT_D}" -ge 1 ]; then
  pass "TestContested_KeywordsWithoutContradiction_KnownFalsePositive: v0.1 heuristic flags 'however, I agree' as contested (expected; documents v0.1 gap)"
else
  fail "TestContested_KeywordsWithoutContradiction_KnownFalsePositive" "v0.1 heuristic should flag this fixture (trigger keywords present); got 0. Either the heuristic gained nuance (good — update this assertion) or trigger keywords were removed from fixture (fix fixture)."
fi

# --- Heuristic version sanity: tests pin v0.1-keyword ---
echo "TestContested_HeuristicVersionStable"
VERSION="$(bash "${DETECT}" "${FIXTURES}/sketchboard-contested-obvious.md" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("heuristic_version",""))')"
if [ "${VERSION}" = "v0.1-keyword" ]; then
  pass "TestContested_HeuristicVersionStable: heuristic_version = v0.1-keyword"
else
  fail "TestContested_HeuristicVersionStable" "expected heuristic_version=v0.1-keyword; got '${VERSION}'. If v0.2 stance classifier landed, the false-positive/false-negative test assertions above also need to flip."
fi

# --- Summary ---
echo ""
echo "TOTAL: PASS=${PASS} FAIL=${FAIL}"
[ "${FAIL}" -eq 0 ] || exit 1
