---
name: setup
description: Configure local permissions for this project — git, file editing, web access
user_invocable: true
---

# Setup

Walk the user through configuring their local permissions for this project. Choices are written to `.claude/settings.local.json` (gitignored, personal to this clone).

## How It Works

The shared `.claude/settings.json` ships with safe defaults (read-only git, sqlite3, deny destructive commands). This skill lets users opt in to additional permissions.

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
- Chained `&&` commands are never auto-approved (Claude Code security feature) — each command needs its own pattern
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
- The shared deny rules (no `rm -rf`, no `sudo`, no force push, no reset --hard, no clean -f) still apply regardless
- Deny rules take precedence over allow rules, so `Bash(git *)` is safe — destructive git ops are still blocked
