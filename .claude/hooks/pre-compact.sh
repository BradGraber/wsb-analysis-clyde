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
[ -f "$COUNTER_FILE" ] && BATCH_COUNT=$(tr -dc '0-9' < "$COUNTER_FILE" 2>/dev/null || echo 0)
BATCH_COUNT=${BATCH_COUNT:-0}

# Build context injection string
CONTEXT="=== IMPLEMENTATION STATE (from PreCompact hook) ===
Active Phase: ${PHASE_ID}
Batch Counter: ${BATCH_COUNT} / 8 budget
Test Runner: ${TEST_RUNNER}
Resume State: ${RESUME}

Continue the implementation loop per .claude/rules/implementation-phase.md.
Re-read project-workspace/tests/conventions.md for full conventions.
Re-read output/.session-batch-count for the authoritative batch counter."

# Log compaction event if logging is enabled (entire block is fire-and-forget —
# logging failures must never prevent context injection on line 71)
LOG_DIR="$PROJECT_DIR/output/logs"
if [ -f "$LOG_DIR/.enabled" ]; then
    {
        TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        PHASE_STATUS=$(echo "$RESUME" | jq -r '.phase_status // empty')
        RESUME_ACTION=$(echo "$RESUME" | jq -r '.resume_action // empty')
        ORPHANED_COUNT=$(echo "$RESUME" | jq '(.orphaned_tasks // []) | length')
        GATES_COUNT=$(echo "$RESUME" | jq '(.pending_story_gates // []) | length')

        LOG_ENTRY=$(jq -nc \
          --arg ts "$TIMESTAMP" \
          --arg phase_id "$PHASE_ID" \
          --arg phase_status "$PHASE_STATUS" \
          --argjson batch "${BATCH_COUNT}" \
          --arg resume_action "$RESUME_ACTION" \
          --argjson orphaned_tasks "${ORPHANED_COUNT:-0}" \
          --argjson pending_gates "${GATES_COUNT:-0}" \
          --arg context_injected "$CONTEXT" \
          '{ts: $ts, event: "compaction", phase_id: $phase_id, phase_status: $phase_status, batch: $batch, resume_action: $resume_action, orphaned_tasks: $orphaned_tasks, pending_gates: $pending_gates, context_injected: $context_injected}')

        LOG_FILE="$LOG_DIR/events.jsonl"
        (
            flock -x 200
            echo "$LOG_ENTRY" >> "$LOG_FILE"
        ) 200>"${LOG_FILE}.lock"
    } 2>/dev/null || true
fi

# Output context injection for Claude Code
jq -n --arg ctx "$CONTEXT" '{additionalContext: $ctx}'
