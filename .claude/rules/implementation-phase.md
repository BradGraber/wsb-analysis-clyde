# Implementation Phase

When the user asks to implement, build, or work on tasks, follow these steps:

## Prerequisites
- `output/plan.db` must exist
- `output/technical-brief.md` must exist
- If either is missing, run the Intake Phase first (`/analyze`)

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

# Mark a task as skipped with a reason (does NOT cascade)
python3 scripts/plan-ops.py skip-task TASK_ID --reason "description"

# Reset a skipped task to pending for retry
python3 scripts/plan-ops.py retry-task TASK_ID

# List all skipped tasks (optionally scoped to a phase)
python3 scripts/plan-ops.py list-skipped [--phase PHASE_ID]

# Show overall project progress (task/story/epic counts, in-progress items, phases)
python3 scripts/plan-ops.py progress

# Show phase progress, entry/exit criteria
python3 scripts/plan-ops.py phase-status PHASE_ID
```

## Execution Loop

The main conversation acts as an **orchestrator**. Track files changed per story as tasks complete — this accumulated list feeds into story and phase reviews.

### 1. Check Phase Entry Criteria

`plan-ops.py phase-status PHASE_ID` — review entry criteria before starting work.

### 2. Write Tests

Spawn **test-writer** agent (model: **sonnet**) with:
- All story acceptance criteria for stories in this phase
- Phase exit criteria
- `output/technical-brief.md`

The test-writer produces test files that define "done" for this phase. All tests are expected to fail initially — no implementation exists yet. Note the test runner command for later use.

### 3. Find Next Task

`plan-ops.py next-task --phase PHASE_ID` — if no unblocked tasks remain, go to step 10.

### 4. Get Context and Start

```bash
plan-ops.py task-context TASK_ID
plan-ops.py start-task TASK_ID
```

### 5. Spawn Implementer

Spawn **implementer** subagent (model: **sonnet**) with the task context JSON + `output/technical-brief.md`.

The implementer returns a structured report with status (COMPLETE / BLOCKED / PARTIAL), files changed, acceptance criteria check, and concerns.

### 6. Evaluate Implementer Result

Read the implementer's structured report and route:

- **COMPLETE**: Verify the files-changed list is non-empty and each acceptance criterion is addressed. If concerns are listed, note them but proceed unless they indicate a real problem. → Go to step 7.
- **BLOCKED**: Run `plan-ops.py skip-task TASK_ID --reason "<reason from report>"`. → Go to step 3.
- **PARTIAL**: If unmet criteria are core to the task, retry once — re-spawn the implementer with the original context plus the partial report as feedback. If retry still returns PARTIAL or BLOCKED, skip the task. If unmet criteria are deferrable (tests, docs), complete the task and note what's deferred. → Go to step 7 or step 3.

**Never retry more than once per task.** Diminishing returns waste context.

### 7. Complete Task

`plan-ops.py complete-task TASK_ID` — track the files changed from this task for the current story.

If `complete-task` reports that the parent story auto-completed ("Story X: complete"), go to step 8. Otherwise, go to step 3.

### 8. Story Gate

When a story completes, run two checks:

**a) Run story tests** — execute the tests the test-writer created for this story's acceptance criteria.

**b) Spawn plan-validator** (model: **sonnet**) with:
- Story acceptance criteria
- Aggregated files-changed list from all tasks in this story
- `output/technical-brief.md`
- Test results from (a)

**If both pass** → go to step 3.
**If tests fail or review returns FAIL** → present issues to the user. The user decides whether to fix now (spawn targeted implementer) or defer. Do not auto-fix.

### 9. Repeat

Go to step 3 until `next-task` returns no unblocked tasks.

### 10. Phase Gate

When no unblocked tasks remain in the phase:

**a) Run all phase tests** — execute the full test suite the test-writer created for this phase.

**b) Check skipped tasks**: `plan-ops.py list-skipped --phase PHASE_ID`

**c) Spawn plan-validator** (model: **sonnet**) with:
- Phase exit criteria (from `plan-ops.py phase-status`)
- All files created/modified across the entire phase
- `output/technical-brief.md`
- Skipped task list (if any)
- Test results from (a)

**d) Present to user**:
- Phase test results
- Plan-validator review results
- Skipped tasks with reasons
- Exit criteria status

**User must approve before proceeding to the next phase.**

## Error Recovery

- **Skipped tasks**: Presented at phase boundaries with reasons. The user can:
  - `plan-ops.py retry-task TASK_ID` to reset for another attempt
  - Clarify requirements and retry
  - Defer to a later phase
  - Accept the skip (manually complete if the functionality was handled elsewhere)
- **PARTIAL retries**: Maximum one retry per task. The retry includes the original context plus the partial report from the first attempt.
- **Story review failures**: Present to user — do not auto-fix. The user decides whether to spawn a targeted fix or defer.
- **Undeclared dependencies**: If an implementer reports needing code from a task not listed as a dependency, note it as a discovered dependency. Skip the task and present at the phase boundary. Do not modify plan.db dependencies automatically.

## Execution Granularity
- **Default: Phase** — Execute all tasks within a work-sequence phase
- **Also supported:** Single task, story, or epic when the user specifies
- For single task/story execution, skip the test-writing step (step 2) — tests are phase-scoped

## Notes
- `next-task` handles dependency resolution — it only returns tasks whose dependencies are all complete
- `complete-task` handles cascading — it auto-completes the parent story/epic when all children are done
- `start-task` cascades in_progress status up to story and epic
- Skipped tasks prevent their parent story from auto-completing — this is correct behavior
