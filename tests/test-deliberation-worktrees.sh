#!/usr/bin/env bash
# test-deliberation-worktrees.sh
# v0.1.2 phase 3a infrastructure tests: worktree lifecycle, orphan audit,
# branch isolation check. Pins the foundation for the per-persona reasoning
# branch model (Fix #1).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; echo "       $2"; }

# Cleanup hook so a failed test never leaves worktrees lying around.
cleanup() {
  for wt in .claude/worktrees/test-*; do
    [ -d "$wt" ] && git worktree remove --force "$wt" 2>/dev/null || true
  done
  for br in $(git for-each-ref --format='%(refname:short)' 'refs/heads/persona/test-*' 2>/dev/null); do
    git branch -D "$br" 2>/dev/null || true
  done
  git worktree prune 2>/dev/null || true
}
trap cleanup EXIT

# --- Test 1: worktree_create produces a worktree on the expected branch ---
echo "TestWorktrees_CreateAtExpectedPathAndBranch"
python3 - <<'PYEOF' || fail "TestWorktrees_CreateAtExpectedPathAndBranch" "(see stderr)"
import sys
from pathlib import Path
sys.path.insert(0, 'scripts/deliberate')
from lib.state import worktree_create, worktree_remove, reasoning_branch_name, worktree_path

persona = "test-persona-A"
epoch, slot = 1, 1

# Clean if leftover from previous run
existing = worktree_path(persona, epoch, slot)
if existing.exists():
    worktree_remove(existing)

path = worktree_create(persona, epoch, slot, "bid")
assert path.exists(), f"worktree dir not created at {path}"
assert path.is_dir(), f"worktree path is not a directory: {path}"

import subprocess
branch_in_worktree = subprocess.run(
    ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
    capture_output=True, text=True, check=True
).stdout.strip()
expected_branch = reasoning_branch_name(persona, epoch, slot, "bid")
assert branch_in_worktree == expected_branch, \
    f"worktree on wrong branch: got {branch_in_worktree}, expected {expected_branch}"

worktree_remove(path)
assert not path.exists(), "worktree directory not removed"
# Branch should persist
branches = subprocess.run(
    ["git", "branch", "--list", expected_branch],
    capture_output=True, text=True, check=True
).stdout.strip()
assert branches, f"branch {expected_branch} unexpectedly removed with worktree"

# Cleanup
subprocess.run(["git", "branch", "-D", expected_branch], capture_output=True)
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestWorktrees_CreateAtExpectedPathAndBranch"; fi

# --- Test 2: orphan worktree audit removes prior-epoch worktrees ---
echo "TestWorktrees_OrphanAuditRemovesPriorEpoch"
python3 - <<'PYEOF' || fail "TestWorktrees_OrphanAuditRemovesPriorEpoch" "(see stderr)"
import sys
from pathlib import Path
sys.path.insert(0, 'scripts/deliberate')
from lib.state import (
    worktree_create, audit_orphan_worktrees, list_persona_worktrees,
    state_dir, worktree_remove, worktree_path,
)

# Create two worktrees: one for "epoch 1" (will become orphan), one for "epoch 2" (current)
p1 = worktree_create("test-orphanA", 1, 1, "bid")
p2 = worktree_create("test-currentA", 2, 1, "bid")

# Audit with current_epoch=2 → epoch-1 worktree is orphan, epoch-2 worktree stays
removed = audit_orphan_worktrees(current_epoch=2, current_state="COLLECTING")
removed_branches = [r["branch"] for r in removed]

assert any("test-orphanA" in b for b in removed_branches), \
    f"orphan from epoch 1 not removed; got removed: {removed_branches}"
assert not any("test-currentA" in b for b in removed_branches), \
    f"current-epoch worktree incorrectly removed; got: {removed_branches}"

# gc.log should record the removal
log_path = state_dir() / "gc.log"
assert log_path.exists(), "gc.log not created by audit"
log_content = log_path.read_text()
assert "orphan-worktree-removed" in log_content
assert "test-orphanA" in log_content

# Cleanup the current worktree
worktree_remove(p2)
import subprocess
for br in ("persona/test-orphanA/bid-epoch-1-slot-1", "persona/test-currentA/bid-epoch-2-slot-1"):
    subprocess.run(["git", "branch", "-D", br], capture_output=True)
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestWorktrees_OrphanAuditRemovesPriorEpoch"; fi

# --- Test 3: orphan audit removes worktrees from a closed (REVIEW) epoch ---
echo "TestWorktrees_OrphanAuditRemovesClosedEpochWorktrees"
python3 - <<'PYEOF' || fail "TestWorktrees_OrphanAuditRemovesClosedEpochWorktrees" "(see stderr)"
import sys
from pathlib import Path
sys.path.insert(0, 'scripts/deliberate')
from lib.state import worktree_create, audit_orphan_worktrees, worktree_remove

p = worktree_create("test-closedA", 5, 1, "write")
# Same epoch as current but state is REVIEW → all worktrees are orphan
removed = audit_orphan_worktrees(current_epoch=5, current_state="REVIEW")
assert any("test-closedA" in r["branch"] for r in removed), \
    f"current-but-closed epoch worktree not removed; got: {[r['branch'] for r in removed]}"
import subprocess
subprocess.run(["git", "branch", "-D", "persona/test-closedA/write-epoch-5-slot-1"], capture_output=True)
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestWorktrees_OrphanAuditRemovesClosedEpochWorktrees"; fi

# --- Test 4: branch_isolation_check ok when only persona's own branch changes ---
echo "TestPostcheck_BranchIsolationAllowsOwnBranch"
python3 - <<'PYEOF' || fail "TestPostcheck_BranchIsolationAllowsOwnBranch" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.postcheck import branch_isolation_check

pre = {
    "refs/heads/main": "aaa",
    "refs/heads/persona/test-X/bid-epoch-1-slot-1": "bbb",
}
post = {
    "refs/heads/main": "aaa",   # unchanged
    "refs/heads/persona/test-X/bid-epoch-1-slot-1": "ccc",   # advanced
}
result = branch_isolation_check("test-X", pre, post)
assert result["ok"], f"own-branch modification should pass; got {result}"
assert "refs/heads/persona/test-X/bid-epoch-1-slot-1" in result["modified_refs"]
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestPostcheck_BranchIsolationAllowsOwnBranch"; fi

# --- Test 5: branch_isolation_check flags writes to main ---
echo "TestPostcheck_BranchIsolationRejectsMainWrite"
python3 - <<'PYEOF' || fail "TestPostcheck_BranchIsolationRejectsMainWrite" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.postcheck import branch_isolation_check

pre = {"refs/heads/main": "aaa"}
post = {"refs/heads/main": "ZZZ"}   # main modified — forbidden
result = branch_isolation_check("test-X", pre, post)
assert not result["ok"], f"main modification should fail isolation; got {result}"
assert result["failure"] == "branch-isolation-violated"
assert "refs/heads/main" in result["forbidden_refs"]
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestPostcheck_BranchIsolationRejectsMainWrite"; fi

# --- Test 6: branch_isolation_check flags writes to another persona's branch ---
echo "TestPostcheck_BranchIsolationRejectsForeignPersonaBranch"
python3 - <<'PYEOF' || fail "TestPostcheck_BranchIsolationRejectsForeignPersonaBranch" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.postcheck import branch_isolation_check

pre = {"refs/heads/persona/test-Y/bid-epoch-1-slot-1": "aaa"}
post = {"refs/heads/persona/test-Y/bid-epoch-1-slot-1": "ZZZ"}   # X writes to Y's branch
result = branch_isolation_check("test-X", pre, post)
assert not result["ok"], f"foreign-persona-branch modification should fail; got {result}"
assert "refs/heads/persona/test-Y/bid-epoch-1-slot-1" in result["forbidden_refs"]
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestPostcheck_BranchIsolationRejectsForeignPersonaBranch"; fi

# --- Test 7: reasoning_commit_message format pin ---
echo "TestState_ReasoningCommitMessageFormat"
python3 - <<'PYEOF' || fail "TestState_ReasoningCommitMessageFormat" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.state import reasoning_commit_message

msg = reasoning_commit_message("scaling-optimist", 3, 2, "bid")
assert msg == "reason(deliberation): scaling-optimist epoch-3 slot-2 bid", \
    f"unexpected commit message format: {msg}"

msg2 = reasoning_commit_message("bias-auditor", 1, 1, "write")
assert msg2 == "reason(deliberation): bias-auditor epoch-1 slot-1 write"

# Invalid mode rejected
try:
    reasoning_commit_message("x", 1, 1, "invalid")
    assert False, "invalid mode should raise"
except ValueError:
    pass
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestState_ReasoningCommitMessageFormat"; fi

echo ""
echo "TOTAL: PASS=${PASS} FAIL=${FAIL}"
[ "${FAIL}" -eq 0 ] || exit 1
