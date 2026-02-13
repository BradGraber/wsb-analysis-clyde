---
name: end-session
description: Wrap up the current session — update memory, summarize progress, note open items
user_invocable: true
---

# End Session

Perform the following steps to cleanly wrap up the current session:

## 0. Check Mode

If `.claude/rules/dev-mode.md` exists, this is a **dev-mode session** (framework development). Adjust the steps below:
- Step 1: Summarize framework areas changed (hooks, agents, skills, rules, scripts) instead of task completions
- Step 2: Skip entirely — no plan.db in dev mode
- Step 3: When reporting uncommitted changes, categorize by framework area:
  - Hooks (`.claude/hooks/`), Agents (`.claude/agents/`), Skills (`.claude/skills/`), Rules (`.claude/rules/`), Scripts (`scripts/`), Other
- Steps 4-5: Run normally

## 1. Session Summary
Summarize what was accomplished in this session:
- Decisions made
- Files created or modified
- Tasks completed (if in the Implementation Phase)
- Problems encountered and how they were resolved

## 2. Project State Check
Check existence of key artifacts and report their status:

### If `output/plan.db` exists:
Run `python3 scripts/plan-ops.py progress` to get a full snapshot:
- Overall task/story/epic counts by status
- Any tasks currently in_progress (these need resuming next session)
- Phase-by-phase completion percentages

**In-progress task note:** `next-task` only returns *pending* tasks, so any tasks left in `in_progress` status must be explicitly resumed by the next session. List them prominently in the report.

### If `output/plan.db` does NOT exist:
- The Intake Phase has not been run (or did not complete). Note this — no plan-ops.py calls.
- Check if `output/technical-brief.md` exists — if plan.db is missing but the brief exists, something went wrong during the Intake Phase.

## 3. Git Check
Run `git status` to check for uncommitted changes.
- If there are **no** uncommitted changes, note it and move on.
- If there **are** uncommitted changes (staged or unstaged), ask the user whether they want to commit before ending:
  - **If yes:** Follow the normal commit flow — stage relevant files, write a clear commit message summarizing the session's work, and commit. Do NOT push unless the user explicitly asks.
  - **If no:** Flag the uncommitted changes in the session report under Open Items so they aren't lost.

## 4. Update Memory Files

### Auto-memory `MEMORY.md`

Update the following sections (see [project-design.md](./project-design.md) "Memory Structure Contract" for the full spec):

**Session History** — Prepend a new entry to `## Session History`. Keep the last 3 entries, drop the oldest if at capacity. Format:

```markdown
### YYYY-MM-DD
- **Completed:** [1-3 bullet summary of what was done]
- **Open:** [uncommitted changes, in-progress tasks, unresolved issues — or "None"]
- **Next:** [specific suggested action for the next session]
```

**Current State** — Update `## Current State` to reflect the new project state (latest commits, phase progress, etc.).

**Other sections** — Update TODO, Investigate (dev mode) or Known Issues, Deferred Items (project mode) as needed. Move detailed content to linked topic files if MEMORY.md approaches 200 lines.

### Auto-memory `project-design.md`
- Located alongside MEMORY.md in the auto-memory directory
- Update with any structural or design changes
- Add new sections if significant topics were discussed
- Keep it comprehensive but organized

## 5. Open Items
List anything that needs attention next session:
- Unfinished work (including any in-progress tasks from step 2)
- Uncommitted changes (if the user declined to commit in step 3)
- Unresolved questions
- Next logical step

If this session was ended because the batch budget was reached (Step 9 of the implementation loop), include this as the first open item:
- **Reset context before continuing:** Run `/clear` to reset the context window, then `/resume` to pick up where you left off. No need to exit Claude Code. (Run `/status` first if you want a broader progress overview before diving back in.)

Present all of this to the user as a clear end-of-session report.
