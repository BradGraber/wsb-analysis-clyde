---
name: end-session
description: Wrap up the current session — update memory, summarize progress, note open items
user_invocable: true
---

# End Session

Perform the following steps to cleanly wrap up the current session:

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
Update both memory files to reflect the current state:

### Auto-memory `MEMORY.md`
- Located in your project's auto-memory directory (referenced in the system prompt)
- Add any new decisions
- Update or resolve open questions
- Keep it concise (under 200 lines)

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

Present all of this to the user as a clear end-of-session report.
