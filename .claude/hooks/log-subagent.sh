#!/bin/bash
set -e
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# Logging disabled unless opted in
[ -f "$PROJECT_DIR/output/logs/.enabled" ] || exit 0

INPUT=$(cat)
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty')
AGENT_ID=$(echo "$INPUT" | jq -r '.agent_id // empty')
TRANSCRIPT=$(echo "$INPUT" | jq -r '.agent_transcript_path // empty')

[ -z "$AGENT_TYPE" ] && exit 0
[ -z "$TRANSCRIPT" ] && exit 0
TRANSCRIPT="${TRANSCRIPT/#\~/$HOME}"
[ -f "$TRANSCRIPT" ] || exit 0

LOG_DIR="$PROJECT_DIR/output/logs"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
cp "$TRANSCRIPT" "$LOG_DIR/${TIMESTAMP}-${AGENT_TYPE}-${AGENT_ID}.jsonl" 2>/dev/null || true
exit 0
