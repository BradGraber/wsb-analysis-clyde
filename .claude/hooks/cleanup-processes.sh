#!/bin/bash
set -e
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PID_FILE="$PROJECT_DIR/output/.spawned-pids"

# --- Filtering ---
# When called as a SubagentStop hook: only run after implementer subagents.
# When called as SessionEnd hook or with --direct: always run.
if [ "${1:-}" != "--direct" ]; then
    INPUT=$(cat)
    AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null)
    # SubagentStop for non-implementer agents: skip
    if [ -n "$AGENT_TYPE" ] && [ "$AGENT_TYPE" != "implementer" ]; then
        exit 0
    fi
fi

# --- Cleanup ---
# Only kill PIDs explicitly recorded in the tracking file.
# Never scan ports or pattern-match — avoids killing user's own processes.
[ -f "$PID_FILE" ] || exit 0
[ -s "$PID_FILE" ] || exit 0  # empty file

CLEANED=""
while IFS= read -r PID; do
    PID=$(echo "$PID" | tr -d '[:space:]')
    [ -z "$PID" ] && continue
    # Check if PID is still alive
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null || true
        sleep 0.2
        if ! kill -0 "$PID" 2>/dev/null; then
            CLEANED="${CLEANED}PID ${PID} "
        fi
    fi
done < "$PID_FILE"

# Truncate the file after processing
: > "$PID_FILE"

# --- Output ---
# Only output if something was cleaned (zero context cost otherwise)
if [ -n "$CLEANED" ]; then
    echo "Cleaned tracked processes: ${CLEANED}"
    # Also log to file if log dir exists
    LOG_DIR="$PROJECT_DIR/output/logs"
    [ -d "$LOG_DIR" ] && echo "$(date +%Y%m%d-%H%M%S) Cleaned: ${CLEANED}" >> "$LOG_DIR/cleanup.log" || true
fi

exit 0
