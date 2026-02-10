---
name: init
description: One-time project initialization — detach from Clyde framework, clean git history, set up as standalone project
user_invocable: true
---

# Init

One-time setup for a fresh Clyde clone. Detaches from the framework repo, cleans git history, and prepares the project for standalone use.

## Steps

### 1. Verify This Is Needed

Check if `.claude/rules/init-gate.md` exists. If it doesn't, tell the user:
> "This project is already initialized. Nothing to do."

And stop.

### 2. Inspect Git State

Run these commands and report findings to the user:

```bash
git remote get-url origin 2>/dev/null
git log --oneline | wc -l
git log --oneline -3
```

Summarize: "Your repo still points to [remote] with [N] commits of Clyde framework history."

### 3. Ask the User

Ask the user the following questions using AskUserQuestion:

**Project name:**
- Ask: "What should this project be called?" (free text — this is used for the commit message and CLAUDE.md header)

**Git history:**
- **Squash to clean start (Recommended)** — Reset to a single initial commit. Clyde framework history is removed.
- **Keep full history** — Preserve the Clyde commit log as-is.

**Remote repository:**
- **Set up a new remote now** — Ask for the URL and configure it.
- **Skip for now** — No remote, they can add one later.

### 4. Execute Initialization

Based on the user's choices, perform the following. **Always confirm the actions with the user before executing.**

**a) Rename the Clyde remote** (keeps it for future `/update` pulls):
```bash
git remote rename origin clyde
```

**b) If squashing history:**
```bash
git checkout --orphan init-branch
git add -A
git commit -m "Initialize project from Clyde framework"
git branch -M main
```

Note: If they were on a branch other than main, adjust accordingly (use their current branch name).

**c) If setting up a new remote:**
```bash
git remote add origin <user-provided-url>
```
Do NOT push — just configure it. Tell the user they can push when ready.

### 5. Remove the Init Gate

Delete the rule file that triggers this flow:

```bash
rm .claude/rules/init-gate.md
```

Then run `git add -A` to stage the deletion (and any other changes from the init process).

### 6. Final Commit

If history was NOT squashed (so the deletion isn't already folded in), create a commit:

```bash
git commit -m "Complete project initialization"
```

If history WAS squashed, amend the init commit to include the gate removal:

```bash
git add -A
git commit --amend --no-edit
```

### 7. Report Completion

Show the user a summary:

```
Project initialized!

  Project: [name]
  Branch:  [branch name]
  Remote:  [url or "none configured"]
  Clyde:   [clyde remote URL] (for framework updates via /update)
  History: [squashed / preserved]

Next steps:
  1. Add your PRD, epics, stories, tasks, and work-sequence to input/
  2. Run /analyze to build the plan database
  3. Optionally run /setup to configure local permissions
  4. Run /update anytime to pull framework updates from the Clyde repo
```
