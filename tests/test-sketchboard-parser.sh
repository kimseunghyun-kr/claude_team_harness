#!/usr/bin/env bash
# test-sketchboard-parser.sh
# Regression tests for lib/sketchboard.parse_sketchboard.
#
# History: v0.1.1 rebuild introduced a bug where the Epoch section was flushed
# at the FIRST child persona heading line, so the persona heading itself sat
# at `end_line` and failed the `idx < end_line` check in postcheck. Result:
# every "first persona block of an epoch" forfeited with out-of-epoch-section.
# This test pins the fix.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; echo "       $2"; }

# Test 1: Epoch section contains its child persona block
# (the bug case — first persona heading shouldn't close the epoch)
echo "TestParser_EpochContainsFirstPersonaBlock"
python3 - <<'PYEOF' || fail "TestParser_EpochContainsFirstPersonaBlock" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.sketchboard import parse_sketchboard

text = """# Sketchboard

## Question
Q?

## Epoch 1

<!-- empty -->

## Scaling Optimist:

> Q?

Body line one.

---

## Open Conflicts

---

## Ratified Decisions
"""
sections, blocks = parse_sketchboard(text)
epoch_1 = next((s for s in sections if s.heading == "Epoch 1"), None)
assert epoch_1 is not None, "Epoch 1 section missing"
assert len(blocks) == 1, f"expected 1 persona block; got {len(blocks)}"
b = blocks[0]
# The persona heading line MUST be inside the epoch section range
assert epoch_1.start_line <= b.start_line < epoch_1.end_line, \
    f"persona heading at {b.start_line} not in epoch range [{epoch_1.start_line}, {epoch_1.end_line})"
# AND the persona end_line must be <= epoch end_line
assert b.end_line <= epoch_1.end_line, \
    f"persona block ends at {b.end_line} past epoch end {epoch_1.end_line}"
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestParser_EpochContainsFirstPersonaBlock"; fi

# Test 2: Epoch ends at the next non-persona top-level heading
echo "TestParser_EpochEndsAtNextTopSection"
python3 - <<'PYEOF' || fail "TestParser_EpochEndsAtNextTopSection" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.sketchboard import parse_sketchboard

text = """## Epoch 1

## Scaling Optimist:

> x

A.

## Architecture Skeptic:

> y

B.

## Open Conflicts
"""
sections, blocks = parse_sketchboard(text)
epoch_1 = next((s for s in sections if s.heading == "Epoch 1"), None)
oc = next((s for s in sections if s.heading == "Open Conflicts"), None)
assert epoch_1 and oc
assert epoch_1.end_line == oc.start_line, \
    f"Epoch 1 should end at Open Conflicts start; got {epoch_1.end_line} vs {oc.start_line}"
assert len(blocks) == 2, f"expected 2 persona blocks; got {len(blocks)}"
assert all(b.epoch == 1 for b in blocks), "both blocks should be in epoch 1"
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestParser_EpochEndsAtNextTopSection"; fi

# Test 3: WRITE postcheck accepts the FIRST persona block of an epoch
echo "TestParser_PostcheckAcceptsFirstBlock"
python3 - <<'PYEOF' || fail "TestParser_PostcheckAcceptsFirstBlock" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.sketchboard import verify_block_in_epoch

prev = """## Epoch 1

<!-- empty -->

---

## Open Conflicts
"""

new = """## Epoch 1

<!-- empty -->

## Scaling Optimist:

> some claim

body

---

## Open Conflicts
"""

ok, reason = verify_block_in_epoch(new, prev, epoch=1, persona_display="Scaling Optimist")
assert ok, f"first persona block should pass postcheck; got reason: {reason}"
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestParser_PostcheckAcceptsFirstBlock"; fi

# Test 4: WRITE postcheck rejects writes outside the epoch
echo "TestParser_PostcheckRejectsOutOfEpoch"
python3 - <<'PYEOF' || fail "TestParser_PostcheckRejectsOutOfEpoch" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.sketchboard import verify_block_in_epoch

prev = """## Epoch 1

<!-- empty -->

---

## Ratified Decisions
"""

# Block written INSIDE Ratified Decisions (forbidden)
new = """## Epoch 1

<!-- empty -->

---

## Ratified Decisions

## Scaling Optimist:

> claim

body
"""

ok, reason = verify_block_in_epoch(new, prev, epoch=1, persona_display="Scaling Optimist")
assert not ok, "out-of-epoch write should be rejected"
print(f"OK (rejected: {reason})")
PYEOF
if [ $? -eq 0 ]; then pass "TestParser_PostcheckRejectsOutOfEpoch"; fi

# Test 5: postcheck rejects content appended AFTER the final top-level section
# (v0.1.2 Fix #3 — boundary edge case: persona appends below Ratified Decisions
# instead of inside the epoch. The diff is purely additive but the addition
# lands outside any current-epoch section.)
echo "TestParser_PostcheckRejectsAppendAfterRatified"
python3 - <<'PYEOF' || fail "TestParser_PostcheckRejectsAppendAfterRatified" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.sketchboard import verify_block_in_epoch

prev = """## Epoch 1

<!-- empty -->

---

## Open Conflicts

---

## Ratified Decisions
"""

# Block appended AFTER Ratified Decisions (past end of document, outside epoch)
new = """## Epoch 1

<!-- empty -->

---

## Open Conflicts

---

## Ratified Decisions

## Scaling Optimist:

> some claim

body appended after every other section
"""

ok, reason = verify_block_in_epoch(new, prev, epoch=1, persona_display="Scaling Optimist")
assert not ok, f"append after Ratified Decisions should be rejected; got ok=True"
# We don't constrain WHICH error code as long as it's a structural rejection —
# could be 'out-of-epoch-section' or 'edited-forbidden-section' depending on
# whether the parser considers a new persona heading after the last top section
# as inside-Ratified or after-all-sections. Either is acceptable.
print(f"OK (rejected: {reason})")
PYEOF
if [ $? -eq 0 ]; then pass "TestParser_PostcheckRejectsAppendAfterRatified"; fi

echo ""
echo "TOTAL: PASS=${PASS} FAIL=${FAIL}"
[ "${FAIL}" -eq 0 ] || exit 1
