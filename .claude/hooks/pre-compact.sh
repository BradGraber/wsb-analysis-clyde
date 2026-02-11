#!/bin/bash
set -e
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# Only inject context if plan.db exists (implementation phase active)
[ -f "$PROJECT_DIR/output/plan.db" ] || { echo '{}'; exit 0; }

# Get active phase
ACTIVE=$(python3 "$PROJECT_DIR/scripts/plan-ops.py" active-phase 2>/dev/null || echo '{"phase_id": null}')
PHASE_ID=$(echo "$ACTIVE" | jq -r '.phase_id // empty')
[ -n "$PHASE_ID" ] || { echo '{}'; exit 0; }

# Get resume state for the active phase
RESUME=$(python3 "$PROJECT_DIR/scripts/plan-ops.py" resume-phase "$PHASE_ID" 2>/dev/null || echo "{}")

# Read test runner command from conventions.md if it exists
TEST_RUNNER=""
CONV_FILE="$PROJECT_DIR/project-workspace/tests/conventions.md"
if [ -f "$CONV_FILE" ]; then
    TEST_RUNNER=$(sed -n '/^## Test Runner/,/^## /{/^## Test Runner/d;/^## /d;p;}' "$CONV_FILE" | head -5)
fi

# Read batch counter
BATCH_COUNT=0
COUNTER_FILE="$PROJECT_DIR/output/.session-batch-count"
[ -f "$COUNTER_FILE" ] && BATCH_COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)

# Build context injection
jq -n \
  --arg phase "$PHASE_ID" \
  --arg resume "$RESUME" \
  --arg test_runner "$TEST_RUNNER" \
  --arg batches "$BATCH_COUNT" \
  '{additionalContext: "=== IMPLEMENTATION STATE (from PreCompact hook) ===\nActive Phase: \($phase)\nBatch Counter: \($batches) / 8 budget\nTest Runner: \($test_runner)\nResume State: \($resume)\n\nContinue the implementation loop per .claude/rules/implementation-phase.md.\nRe-read project-workspace/tests/conventions.md for full conventions.\nRe-read output/.session-batch-count for the authoritative batch counter."}'
