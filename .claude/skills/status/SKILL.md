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

### 2. Query Progress (Implementation Phase Active)

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

### 2a. Detect Project Environment

Check for runtime environment details to include in the summary:

```bash
ls -d project-workspace/venv project-workspace/.venv 2>/dev/null
```

If a Python venv is found, include the Environment section in the summary (step 3). The `./clyde` wrapper writes the durable rule file (`.claude/rules/project-env.md`) procedurally — `/status` only reports what it finds.

### 3. Present Summary

Format a concise report. The `progress` command output includes phase lifecycle status (`pending`, `tests_written`, `in_progress`, `gate_pending`, `complete`) next to each phase name.

```
Project: [from PRD title or technical brief if available]

Progress:
  Epics:   X/Y complete
  Stories: X/Y complete
  Tasks:   X/Y complete

Phases:
  phase-a: [name] [status] — X/Y tasks (N%)
  phase-b: [name] [status] — X/Y tasks (N%)

In Progress:
  - [task-id]: [title]

Pending Story Gates:
  - [story-id]: [title] — gate awaiting review

Skipped:
  - [task-id]: [title] — [reason]

Environment:
  Python venv: project-workspace/venv/ — activate before all Python commands

Suggested Next Action:
  → [what to do next]
```

Note: "Pending Story Gates", "In Progress", and "Environment" sections should only appear if there are items to show. To detect pending story gates, look for in-progress tasks reported by `progress`. The `resume-phase` command provides full detail if needed.

### 4. Suggest Next Action

Based on the state, suggest one of:
- **"Run `/analyze`"** — if inputs exist but plan.db doesn't
- **"Resume orphaned task [id]: [title]"** — if a task is in_progress (left over from a previous session)
- **"Run pending story gate for [story-id]"** — if a story completed but its gate review hasn't run
- **"Run phase gate for [phase-id]"** — if a phase status is `gate_pending`
- **"Start next task: [id] [title]"** — if nothing is in-progress, pick the next unblocked pending task
- **"Phase [X] complete — start Phase [Y]"** — if a phase status is `complete` and the next phase is `pending`
- **"All tasks complete"** — if everything is done
