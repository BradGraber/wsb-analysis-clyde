#!/bin/bash
# PreToolUse hook: auto-approve safe Bash commands, prompt for dangerous ones.
#
# Registered in settings.json with matcher: "Bash" — only fires for Bash tool calls.
# Returns permissionDecision: "allow" for safe commands (bypasses all prompting).
# Returns permissionDecision: "ask" for dangerous commands (falls back to user prompt).
# On error: exits 0 with no output (fail-safe — normal permission checking applies).
# Fail-safe exits are logged as "fail_safe" decisions for diagnostic visibility.

set -euo pipefail

# --- Decision logging ---
# Appends to output/logs/hook-decisions.jsonl when logging is enabled.
# Uses flock for concurrent-safe writes when parallel subagents fire this hook.
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
log_decision() {
    local cmd="$1" decision="$2" reason="$3"
    [ -f "$PROJECT_DIR/output/logs/.enabled" ] || return 0
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local log_file="$PROJECT_DIR/output/logs/hook-decisions.jsonl"
    (
        flock -x 200
        jq -n -c \
          --arg ts "$ts" \
          --arg hook "approve-command" \
          --arg command "$cmd" \
          --arg decision "$decision" \
          --arg reason "$reason" \
          '{ts: $ts, hook: $hook, command: $command, decision: $decision, reason: $reason}' \
          >> "$log_file"
    ) 200>"${log_file}.lock" 2>/dev/null || true
}

# --- Fail-safe logging ---
# Uses printf (not jq) to avoid circular failure when jq itself is the problem.
# Logs to the same hook-decisions.jsonl so the validator picks these up.
log_fail_safe() {
    local reason="$1" raw_input="$2"
    [ -f "$PROJECT_DIR/output/logs/.enabled" ] || return 0
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local log_file="$PROJECT_DIR/output/logs/hook-decisions.jsonl"
    # Truncate raw input to 500 chars and escape for JSON
    local safe_input
    safe_input=$(printf '%.500s' "$raw_input" | tr '\n\t' '  ' | sed 's/\\/\\\\/g; s/"/\\"/g')
    (
        flock -x 200
        printf '{"ts":"%s","hook":"approve-command","command":"","decision":"fail_safe","reason":"%s","raw_input":"%s"}\n' \
          "$ts" "$reason" "$safe_input" \
          >> "$log_file"
    ) 200>"${log_file}.lock" 2>/dev/null || true
}

# Read JSON input
INPUT=$(cat) || { log_fail_safe "stdin_read_failed" ""; exit 0; }

# Extract command — fail-safe on parse error
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || { log_fail_safe "jq_parse_error" "$INPUT"; exit 0; }
[ -z "$COMMAND" ] && { log_fail_safe "empty_command" "$INPUT"; exit 0; }

# Deny patterns — substring matches against the full command string.
# Catches dangerous operations even inside chained commands (&&, ||, |).
# Uses "ask" (user prompt) not "deny" (hard block) so users can approve
# intentional destructive ops without editing this script.
DENY_PATTERNS=(
    "rm -rf"
    "rm -fr"
    "sudo"
    "git clean -f"
    "git checkout ."
    "git restore ."
    "git branch -D"
)

for pattern in "${DENY_PATTERNS[@]}"; do
    if [[ "$COMMAND" == *"$pattern"* ]]; then
        log_decision "$COMMAND" "ask" "Contains '$pattern'"
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"Command contains '"'$pattern'"' — review before approving"}}'
        exit 0
    fi
done

# Git compound checks — flags can appear anywhere in the command, so check
# for the base command AND the dangerous flag separately.
ask_reason=""
if [[ "$COMMAND" == *"git push"* ]] && [[ "$COMMAND" == *"--force"* || "$COMMAND" == *" -f"* ]]; then
    ask_reason="git push with --force/-f"
elif [[ "$COMMAND" == *"git reset"* ]] && [[ "$COMMAND" == *"--hard"* ]]; then
    ask_reason="git reset --hard"
fi

if [ -n "$ask_reason" ]; then
    log_decision "$COMMAND" "ask" "$ask_reason"
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"Command contains '"'$ask_reason'"' — review before approving"}}'
    exit 0
fi

# No deny pattern matched — auto-approve
log_decision "$COMMAND" "allow" ""
echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
