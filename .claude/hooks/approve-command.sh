#!/bin/bash
# PreToolUse hook: auto-approve safe Bash commands, prompt for dangerous ones.
#
# Registered in settings.json with matcher: "Bash" — only fires for Bash tool calls.
# Returns permissionDecision: "allow" for safe commands (bypasses all prompting).
# Returns permissionDecision: "ask" for dangerous commands (falls back to user prompt).
# On error: exits 0 with no output (fail-safe — normal permission checking applies).

set -euo pipefail

# Read JSON input
INPUT=$(cat) || exit 0

# Extract command — fail-safe on parse error
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
[ -z "$COMMAND" ] && exit 0

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
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"Command contains '"'$ask_reason'"' — review before approving"}}'
    exit 0
fi

# No deny pattern matched — auto-approve
echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
