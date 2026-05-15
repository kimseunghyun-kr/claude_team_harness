#!/usr/bin/env bash
# test-deliberation-two-turn.sh
# v0.1.2 integration tests for the two-turn BID/WRITE manifest flow.
# Tests the plumbing (manifest shape, bid memory injection, extraction
# temperature, eavesdrop off by default). Does NOT spawn real Task agents —
# that path is verified manually with /harness-deliberate run.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; echo "       $2"; }

TEST_EPOCH=88

cleanup() {
  rm -f .claude/state/deliberation/epoch-${TEST_EPOCH}-bids.jsonl
  for wt in .claude/worktrees/test-*; do
    [ -d "$wt" ] && git worktree remove --force "$wt" 2>/dev/null || true
  done
  for br in $(git for-each-ref --format='%(refname:short)' 'refs/heads/persona/test-*' 2>/dev/null); do
    git branch -D "$br" 2>/dev/null || true
  done
}
trap cleanup EXIT

mkdir -p .claude/state/deliberation

# --- Test 1: BID reasoning manifest has expected structure ---
echo "TestTwoTurn_BidReasoningManifestStructure"
python3 - <<'PYEOF' || fail "TestTwoTurn_BidReasoningManifestStructure" "(see stderr)"
import subprocess, json, sys
result = subprocess.run(
    ["bash", "scripts/deliberate/spawn-winner.sh",
     "reasoning-manifest", "scaling-optimist", "1", "1", "bid"],
    capture_output=True, text=True, check=True,
)
m = json.loads(result.stdout)
assert m["turn"] == "reasoning"
assert m["mode"] == "bid"
assert m["subagent_type"] == "scaling-optimist"
assert "worktree_path" in m and ".claude/worktrees" in m["worktree_path"]
assert m["branch"] == "persona/scaling-optimist/bid-epoch-1-slot-1"
assert m["expected_commit_msg"] == "reason(deliberation): scaling-optimist epoch-1 slot-1 bid"
assert "BID-REASONING" in m["prompt"]
assert "reasoning.md" in m["prompt"]
# Should NOT instruct JSON output in reasoning mode
assert "Output exactly one JSON line" not in m["prompt"]
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestTwoTurn_BidReasoningManifestStructure"; fi

# --- Test 2: BID extraction manifest has expected structure + temperature ---
echo "TestTwoTurn_BidExtractionManifestStructure"
python3 - <<'PYEOF' || fail "TestTwoTurn_BidExtractionManifestStructure" "(see stderr)"
import subprocess, json
result = subprocess.run(
    ["bash", "scripts/deliberate/spawn-winner.sh",
     "extraction-manifest", "scaling-optimist", "1", "1", "bid"],
    capture_output=True, text=True, check=True,
)
m = json.loads(result.stdout)
assert m["turn"] == "extraction"
assert m["mode"] == "bid"
assert m["subagent_type"] == "general-purpose"
assert m["model_config"]["temperature"] == 0.0
assert m["persona_display"] == "Scaling Optimist"
assert 'Output EXACTLY one JSON line' in m["prompt"]
assert '"bid"' in m["prompt"]
assert '"reason"' in m["prompt"]
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestTwoTurn_BidExtractionManifestStructure"; fi

# --- Test 3: WRITE reasoning manifest requires --bid + --reason ---
echo "TestTwoTurn_WriteReasoningManifestRequiresBid"
python3 - <<'PYEOF' || fail "TestTwoTurn_WriteReasoningManifestRequiresBid" "(see stderr)"
import subprocess, json
result = subprocess.run(
    ["bash", "scripts/deliberate/spawn-winner.sh",
     "reasoning-manifest", "scaling-optimist", "1", "1", "write"],
    capture_output=True, text=True,
)
assert result.returncode != 0, f"missing --bid should error; got rc={result.returncode}"
out = json.loads(result.stdout)
assert "error" in out and "write-mode-requires-bid" in out["error"]

result = subprocess.run(
    ["bash", "scripts/deliberate/spawn-winner.sh",
     "reasoning-manifest", "scaling-optimist", "1", "1", "write",
     "--bid", "0.85", "--reason", "core territory"],
    capture_output=True, text=True, check=True,
)
m = json.loads(result.stdout)
assert m["mode"] == "write"
assert m["branch"] == "persona/scaling-optimist/write-epoch-1-slot-1"
assert "WRITE-REASONING" in m["prompt"]
assert "0.85" in m["prompt"]
assert "core territory" in m["prompt"]
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestTwoTurn_WriteReasoningManifestRequiresBid"; fi

# --- Test 4: collect-bids injects bid history per persona ---
echo "TestTwoTurn_BidHistoryInjected"
bid_log=".claude/state/deliberation/epoch-${TEST_EPOCH}-bids.jsonl"
echo '{"slot":1,"persona":"scaling-optimist","bid":0.9,"reason":"prior bid","won":false}' > "${bid_log}"

python3 - <<PYEOF || fail "TestTwoTurn_BidHistoryInjected" "(see stderr)"
import subprocess, json
result = subprocess.run(
    ["bash", "scripts/deliberate/collect-bids.sh", "${TEST_EPOCH}", "2"],
    capture_output=True, text=True, check=True,
)
m = json.loads(result.stdout)
opt_spawn = next(s for s in m["spawns"] if s["subagent_type"] == "scaling-optimist")
assert "Your prior bids this epoch" in opt_spawn["prompt"], "bid memory missing"
assert "bid=0.90" in opt_spawn["prompt"], "prior bid value not in prompt"
assert "won=False" in opt_spawn["prompt"], "won status not in prompt"

skeptic_spawn = next(s for s in m["spawns"] if s["subagent_type"] == "architecture-skeptic")
assert "Your prior bids this epoch" not in skeptic_spawn["prompt"], \
    "personas without prior bids should not see the memory block"
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestTwoTurn_BidHistoryInjected"; fi

# --- Test 5: collect-bids sidecars include worktree path + reasoning_branch ---
echo "TestTwoTurn_CollectBidsHasTwoTurnSidecars"
python3 - <<PYEOF || fail "TestTwoTurn_CollectBidsHasTwoTurnSidecars" "(see stderr)"
import subprocess, json
result = subprocess.run(
    ["bash", "scripts/deliberate/collect-bids.sh", "${TEST_EPOCH}", "3"],
    capture_output=True, text=True, check=True,
)
m = json.loads(result.stdout)
assert "spawn_mode" in m, "spawn_mode missing"
for s in m["spawns"]:
    p = s["subagent_type"]
    assert "reasoning_branch" in s, f"{p} missing reasoning_branch sidecar"
    assert "worktree_path" in s, f"{p} missing worktree_path sidecar"
    assert s["reasoning_branch"].startswith(f"persona/{p}/bid-epoch-${TEST_EPOCH}-slot-3"), \
        f"{p} unexpected reasoning_branch: {s['reasoning_branch']}"
    assert "bid_history" in s
    assert "eavesdrop_excerpts" in s
    assert s["eavesdrop_excerpts"] == [], \
        f"{p} should have empty eavesdrop with disabled config; got {s['eavesdrop_excerpts']}"
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestTwoTurn_CollectBidsHasTwoTurnSidecars"; fi

# --- Test 6: eavesdrop disabled by default ---
echo "TestTwoTurn_EavesdropDisabledByDefault"
python3 - <<'PYEOF' || fail "TestTwoTurn_EavesdropDisabledByDefault" "(see stderr)"
import sys
sys.path.insert(0, 'scripts/deliberate')
from lib.config import read_config
cfg = read_config()
assert cfg.eavesdrop_enabled is False, f"eavesdrop_enabled must default to False; got {cfg.eavesdrop_enabled}"
assert cfg.spawn_mode == "subagent", f"spawn_mode default must be 'subagent'; got {cfg.spawn_mode}"
assert cfg.extraction_temperature == 0.0, f"extraction_temperature default must be 0.0; got {cfg.extraction_temperature}"
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestTwoTurn_EavesdropDisabledByDefault"; fi

# --- Test 7: gc subcommand dry-run works ---
echo "TestTwoTurn_GcDryRun"
python3 - <<'PYEOF' || fail "TestTwoTurn_GcDryRun" "(see stderr)"
import subprocess, json
result = subprocess.run(
    ["bash", "scripts/deliberate/orchestrate-epoch.sh", "gc", "--dry-run"],
    capture_output=True, text=True, check=True,
)
out = json.loads(result.stdout)
assert out["dry_run"] is True
assert "current_epoch" in out
assert "cutoff_epoch" in out
assert "worktrees_removed" in out
assert "branches_deleted" in out
print("OK")
PYEOF
if [ $? -eq 0 ]; then pass "TestTwoTurn_GcDryRun"; fi

# --- Test 8: persona prompts updated for reasoning mode ---
echo "TestTwoTurn_PersonaPromptsRewrittenForReasoningMode"
all_ok=true
for persona in scaling-optimist architecture-skeptic bias-auditor; do
  if ! grep -q "TWO-TURN MODES" "agents/${persona}.md"; then
    fail "TestTwoTurn_PersonaPromptsRewrittenForReasoningMode" "agents/${persona}.md missing 'TWO-TURN MODES' section"
    all_ok=false
  fi
  if ! grep -q "reasoning.md" "agents/${persona}.md"; then
    fail "TestTwoTurn_PersonaPromptsRewrittenForReasoningMode" "agents/${persona}.md missing reasoning.md mention"
    all_ok=false
  fi
done
if ! grep -q "v0.1.2 ACCESS CONSTRAINT" agents/bias-auditor.md; then
  fail "TestTwoTurn_PersonaPromptsRewrittenForReasoningMode" "bias-auditor.md missing v0.1.2 access constraint"
  all_ok=false
fi
if [ "${all_ok}" = "true" ]; then pass "TestTwoTurn_PersonaPromptsRewrittenForReasoningMode"; fi

echo ""
echo "TOTAL: PASS=${PASS} FAIL=${FAIL}"
[ "${FAIL}" -eq 0 ] || exit 1
