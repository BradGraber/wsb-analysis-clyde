---
name: status
description: Check project state and suggest what to do next
user_invocable: true
---

# Status

Check the current project state and suggest the next action.

## Steps

### 0. Check Initialization

If `.claude/rules/init-gate.md` exists (and `.claude/rules/dev-mode.md` does not), stop and tell the user:

> This project hasn't been initialized yet. Run `/init` to set up your project first.

Do not proceed to the steps below.

### 1. Detect Project Phase

Check what exists to determine where the project stands:

- **No input files** (`input/` only has `.gitkeep` or is empty):
  → Report: "No project inputs found. Add your PRD, epics, stories, tasks, and work-sequence to `input/` to get started."

- **Input files exist but no `output/plan.db`**:
  → Report: "Input files found but not yet analyzed. Run `/analyze` to build the plan database and technical brief."

- **`output/plan.db` exists but no `output/technical-brief.md`** (or vice versa):
  → Report: "Analysis appears incomplete. Run `/analyze` to finish."

- **Both `output/plan.db` and `output/technical-brief.md` exist**:
  → Query the database for progress (see step 2).

### 2. Query Progress (Phase 2 Active)

Use `plan-ops.py` to gather project state — do NOT run raw SQL against plan.db. Run these commands:

```bash
# Overall progress — task/story/epic counts, in-progress items, phase summary
python3 scripts/plan-ops.py progress

# Skipped tasks that need attention
python3 scripts/plan-ops.py list-skipped

# Next suggested action — find the next unblocked pending task
python3 scripts/plan-ops.py next-task
```

Use the output from these three commands to build the summary in step 3.

### 3. Present Summary

Format a concise report:

```
Project: [from PRD title or technical brief if available]

Progress:
  Epics:   X/Y complete
  Stories: X/Y complete
  Tasks:   X/Y complete

In Progress:
  - [task-id]: [title]

Skipped:
  - [task-id]: [title] — [reason]

Current Phase: [phase name]
  [X/Y tasks complete in this phase]

Suggested Next Action:
  → [what to do next]
```

### 4. Suggest Next Action

Based on the state, suggest one of:
- **"Run `/analyze`"** — if inputs exist but plan.db doesn't
- **"Resume task [id]: [title]"** — if a task is in-progress
- **"Start next task: [id] [title]"** — if nothing is in-progress, pick the next unblocked pending task
- **"Phase [X] complete — review exit criteria before starting Phase [Y]"** — if a phase boundary was reached
- **"All tasks complete"** — if everything is done
