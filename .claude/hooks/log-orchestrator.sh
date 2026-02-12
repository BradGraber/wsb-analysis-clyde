#!/bin/bash
set -e
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# Logging disabled unless opted in
[ -f "$PROJECT_DIR/output/logs/.enabled" ] || exit 0

INPUT=$(cat)
LOG_FILE="$PROJECT_DIR/output/logs/orchestrator.jsonl"
EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // empty')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')

# Concurrent-safe append using flock (parallel subagent hooks write to the same file)
atomic_log() {
    (
        flock -x 200
        echo "$1" >> "$LOG_FILE"
    ) 200>"${LOG_FILE}.lock" 2>/dev/null || true
}

case "$EVENT" in
  PostToolUse|PostToolUseFailure)
    TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
    TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}')
    TOOL_RESPONSE=$(echo "$INPUT" | jq -c '.tool_response // {}')
    JSON=$(jq -n -c \
      --arg ts "$TIMESTAMP" \
      --arg event "$EVENT" \
      --arg session "$SESSION_ID" \
      --arg tool "$TOOL_NAME" \
      --argjson input "$TOOL_INPUT" \
      --argjson response "$TOOL_RESPONSE" \
      '{ts: $ts, event: $event, session: $session, tool: $tool, input: $input, response: $response}')
    atomic_log "$JSON"
    ;;
  SessionStart|SessionEnd)
    JSON=$(jq -n -c \
      --arg ts "$TIMESTAMP" \
      --arg event "$EVENT" \
      --arg session "$SESSION_ID" \
      '{ts: $ts, event: $event, session: $session}')
    atomic_log "$JSON"
    ;;
esac

exit 0
