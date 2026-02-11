---
name: setup
description: Configure local permissions for this project — git, file editing, web access
user_invocable: true
---

# Setup

Walk the user through configuring their local permissions for this project. Choices are written to `.claude/settings.local.json` (gitignored, personal to this clone).

## How Security Works

Clyde uses a two-layer security model for Bash commands:

**Layer 1 — PreToolUse hook** (primary): The hook `.claude/hooks/approve-command.sh` inspects every Bash command before execution. Safe commands are auto-approved without prompting. Dangerous commands (recursive deletes, sudo, force push, reset --hard, etc.) fall back to a user prompt — you can approve or deny each one. This works even for chained commands (`cd dir && rm -rf stuff`), because the hook does substring matching on the full command string.

**Layer 2 — settings.json patterns** (fallback): If the hook fails to run, Claude Code falls back to the permission patterns in `.claude/settings.json`. The shared file ships with conservative defaults (read-only git, sqlite3). Your local `.claude/settings.local.json` (configured by this skill) adds broader patterns for your environment.

**What `/setup` configures**: The hook handles Bash auto-approval for implementation. This skill configures *additional* local permissions — git write operations, file editing, web access — that complement the hook. For example, `Bash(git *)` in your local settings ensures single git commands (add, commit, push) don't prompt even if the hook is disabled.

## Steps

### 1. Read Current State

Check if `.claude/settings.local.json` exists. If it does, read it and show the user what's currently configured.

### 2. Ask Permission Questions

Ask the user which categories they want to allow without prompting:

**Git write operations** — choose one:
- **All git operations** (recommended): `Bash(git *)` — single pattern covers add, commit, push, checkout, merge, stash, and everything else. The shared deny rules still block force push, reset --hard, and clean -f.
- **Granular control**: Allow specific git commands individually (add, commit, push, checkout, merge, stash)

**File operations:**
- `Edit` — modify existing files
- `Write` — create new files

**Web access:**
- `WebFetch` — fetch URLs
- `WebSearch` — search the web

**Build/run tools** (if applicable to the project):
- `Bash(npm *)`, `Bash(python *)`, `Bash(make *)`, etc.

### 3. Write Settings

Based on the user's choices, write `.claude/settings.local.json` with the correct wildcard patterns.

**Critical: Permission syntax rules:**
- Bash wildcards use a SPACE before `*`: `Bash(git *)`
- The legacy `:*` colon syntax is deprecated — always use a space
- `*` can appear anywhere in the pattern: beginning, middle, or end
- Chained `&&` commands don't match simple patterns (Claude Code matches the whole string) — the PreToolUse hook handles these automatically
- Include no-argument variants where appropriate: `Bash(git stash)` alongside `Bash(git stash *)`

**Example: All git + file edits (recommended):**
```json
{
  "permissions": {
    "allow": [
      "Bash(git *)",
      "Edit",
      "Write"
    ]
  }
}
```

**Example: Granular git + file edits:**
```json
{
  "permissions": {
    "allow": [
      "Bash(git add *)",
      "Bash(git commit *)",
      "Bash(git push *)",
      "Bash(git push)",
      "Bash(git checkout *)",
      "Bash(git merge *)",
      "Bash(git stash *)",
      "Bash(git stash)",
      "Edit",
      "Write"
    ]
  }
}
```

### 4. Verify

After writing, confirm the settings were saved and summarize what was configured. Remind the user:
- These settings are personal (gitignored) and won't affect other users
- They can re-run `/setup` anytime to change their preferences
- The PreToolUse hook blocks dangerous commands (rm -rf, sudo, force push, reset --hard, clean -f, checkout ., restore ., branch -D) regardless of your local settings
- The shared deny rules in settings.json serve as an additional fallback layer
- `Bash(git *)` is safe — the hook blocks destructive git operations even in chained commands
