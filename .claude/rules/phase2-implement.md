# Phase 2: Implement

When the user asks to implement, build, or work on tasks, follow these steps:

## Prerequisites
- `output/plan.db` must exist
- `output/technical-brief.md` must exist
- If either is missing, run Phase 1 first

## Database Operations

**Never write raw SQL against plan.db.** Use `scripts/plan-ops.py` for all queries and updates:

```bash
# Find the next unblocked pending task (optionally scoped to a phase)
python3 scripts/plan-ops.py next-task [--phase PHASE_ID]

# Get full context for a task (task + story + epic + dependencies as JSON)
python3 scripts/plan-ops.py task-context TASK_ID

# Mark a task as in_progress (cascades to story/epic)
python3 scripts/plan-ops.py start-task TASK_ID

# Mark a task as complete (cascades to story/epic when all children done)
python3 scripts/plan-ops.py complete-task TASK_ID

# Show overall project progress (task/story/epic counts, in-progress items, phases)
python3 scripts/plan-ops.py progress

# Show phase progress, entry/exit criteria
python3 scripts/plan-ops.py phase-status PHASE_ID
```

## Execution Loop

The main conversation acts as an **orchestrator**:

1. **Check phase entry criteria**: `plan-ops.py phase-status PHASE_ID`
2. **Find next task**: `plan-ops.py next-task --phase PHASE_ID`
3. **Get context**: `plan-ops.py task-context TASK_ID`
4. **Start task**: `plan-ops.py start-task TASK_ID`
5. **Spawn implementer** subagent (model: **sonnet**) with the task context JSON + `output/technical-brief.md`
6. **Subagent builds** in `src/` and returns results
7. **Complete task**: `plan-ops.py complete-task TASK_ID`
8. **Repeat** from step 2 until `next-task` returns no unblocked tasks
9. **Check phase exit criteria**: `plan-ops.py phase-status PHASE_ID`

This keeps the orchestrator context lean and gives each subagent clean, focused context.

## Execution Granularity
- **Default: Phase** — Execute all tasks within a work-sequence phase
- **Also supported:** Single task, story, or epic when the user specifies
- Check entry criteria before starting a phase
- Check exit criteria after completing a phase

## Notes
- `next-task` handles dependency resolution — it only returns tasks whose dependencies are all complete
- `complete-task` handles cascading — it auto-completes the parent story/epic when all children are done
- `start-task` cascades in_progress status up to story and epic
