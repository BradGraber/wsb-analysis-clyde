# Implementation Phase

When the user asks to implement, build, or work on tasks, follow these steps:

## Prerequisites
- `output/plan.db` must exist
- `output/technical-brief.md` must exist
- If either is missing, run the Intake Phase first (`/analyze`)
- If `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is not set, warn the user that launching via `./clyde` is recommended to prevent context exhaustion during long implementation sessions

## Database Operations

**Never write raw SQL against plan.db.** Use `scripts/plan-ops.py` for all queries and updates:

```bash
# Find the next unblocked pending task (optionally scoped to a phase)
python3 scripts/plan-ops.py next-task [--phase PHASE_ID]

# Find all unblocked pending tasks for parallel execution (one per story, optionally capped)
python3 scripts/plan-ops.py available-tasks [--phase PHASE_ID] [--limit N]

# Get full context for a task (task + story + epic + dependencies as JSON)
python3 scripts/plan-ops.py task-context TASK_ID

# Mark a task as in_progress (cascades to story/epic)
python3 scripts/plan-ops.py start-task TASK_ID

# Mark a task as complete with files changed (cascades to story/epic when all children done)
python3 scripts/plan-ops.py complete-task TASK_ID --files file1.py file2.py --json

# Mark a task as skipped with a reason (does NOT cascade)
python3 scripts/plan-ops.py skip-task TASK_ID --reason "description"

# Reset a skipped task to pending for retry
python3 scripts/plan-ops.py retry-task TASK_ID

# List all skipped tasks (optionally scoped to a phase)
python3 scripts/plan-ops.py list-skipped [--phase PHASE_ID]

# Get aggregated files changed for a story or phase
python3 scripts/plan-ops.py story-files STORY_ID
python3 scripts/plan-ops.py phase-files PHASE_ID

# Get all stories in a phase (with descriptions containing acceptance criteria)
python3 scripts/plan-ops.py phase-stories PHASE_ID

# Get all tasks in a phase with descriptions (for test-writer structural context)
python3 scripts/plan-ops.py phase-tasks PHASE_ID

# Show overall project progress (task/story/epic counts, in-progress items, phases)
python3 scripts/plan-ops.py progress

# Show phase progress, entry/exit criteria
python3 scripts/plan-ops.py phase-status PHASE_ID

# Detect session resume state for a phase (returns JSON with routing)
python3 scripts/plan-ops.py resume-phase PHASE_ID

# Update phase lifecycle status and/or content
python3 scripts/plan-ops.py update-phase PHASE_ID [--status STATUS] [--goal G] [--entry-criteria EC] [--exit-criteria XC]

# Record story gate review result
python3 scripts/plan-ops.py update-story-gate STORY_ID --status STATUS

# Show database schema (table names, columns, types — JSON)
python3 scripts/plan-ops.py schema

# Inspect any item by ID (auto-detects type from prefix — JSON)
python3 scripts/plan-ops.py show ITEM_ID

# Update task content (title, description, acceptance criteria)
python3 scripts/plan-ops.py update-task TASK_ID [--title T] [--description D] [--acceptance-criteria AC]

# Update story content (title, description)
python3 scripts/plan-ops.py update-story STORY_ID [--title T] [--description D]

# Update epic content (title, description)
python3 scripts/plan-ops.py update-epic EPIC_ID [--title T] [--description D]

# Find the currently active phase (JSON — used by PreCompact hook and /resume)
python3 scripts/plan-ops.py active-phase

# List available reference docs from docs/ and input/docs/ (JSON)
python3 scripts/plan-ops.py list-docs

# Increment batch counter and check budget (JSON — returns {batch, budget, stop})
python3 scripts/plan-ops.py batch-check [--reset] [--budget N]
```

## Resume Detection

Before entering the execution loop, check if this is a resumed session:

```bash
python3 scripts/plan-ops.py resume-phase PHASE_ID
```

This returns a JSON object with `resume_action` telling you where to pick up. The response always includes `orphaned_tasks` and `pending_story_gates` arrays regardless of the action.

- **`start_fresh`** (phase status: `pending`) — Normal start. Go to Step 1.
- **`find_next_task`** (phase status: `tests_written` or `in_progress`, no orphans or pending gates) — Tests already exist. Skip Steps 1-2, go to Step 3. Reset batch counter: `python3 scripts/plan-ops.py batch-check --reset`.
- **`resume_orphan`** (orphaned in_progress tasks found, no pending gates) — A previous session crashed mid-task. The `orphaned_tasks` array lists them. Process as a batch:
  1. Run process cleanup to clear any tracked orphans from the crashed session: `bash .claude/hooks/cleanup-processes.sh --direct`
  2. Get context for all orphans (`task-context` for each)
  3. Do NOT call `start-task` — they're already in_progress
  4. Spawn implementers in parallel (Step 5) for all orphans
  5. Evaluate results and complete tasks (Steps 6-7)
  6. After orphans are resolved, check for any pending story gates before continuing to Step 3
- **`resume_mixed`** (both orphaned tasks AND pending story gates exist) — A previous batch session crashed partway through processing. Run process cleanup first (`bash .claude/hooks/cleanup-processes.sh --direct`), then handle orphans (they may complete more stories), then run all pending story gates (Step 8), then continue to Step 3.
- **`run_story_gate`** (pending story gates found, no orphans) — A previous session completed a story but crashed before running its gate. The `pending_story_gates` array lists them. Run Step 8 for each, then go to Step 3.
- **`run_phase_gate`** (phase status: `gate_pending`) — All tasks were completed but the phase gate never ran or user didn't approve. Go directly to Step 10.
- **`already_complete`** (phase status: `complete`) — This phase is done. Report to user and suggest the next phase.

## Execution Loop

The main conversation acts as an **orchestrator**. Files changed per task are tracked in plan.db via `complete-task --files` and aggregated via `story-files` / `phase-files` for reviews.

### 1. Check Phase Entry Criteria

`plan-ops.py phase-status PHASE_ID` — review entry criteria before starting work.

### 2. Write Tests

Run `plan-ops.py phase-stories PHASE_ID` and `plan-ops.py phase-tasks PHASE_ID` to get all stories and tasks. Then spawn **test-writer** agent (model: **sonnet**) with:
- The story acceptance criteria from `phase-stories` output
- The task descriptions from `phase-tasks` output (structural hints — file paths, naming patterns, config keys)
- Phase exit criteria (from `phase-status` in step 1)
- `output/technical-brief.md`
- If `.claude/rules/project-env.md` exists, include its content (project context and doc listing written by the `./clyde` wrapper — subagents don't inherit rules files)

The test-writer produces test files that define "done" for this phase, plus `project-workspace/tests/conventions.md` documenting structural decisions (module paths, naming conventions, import patterns). All tests are expected to fail initially — no implementation exists yet. Note the test runner command for use in steps 8 and 10.

After the test-writer completes, record that tests exist and initialize the batch counter:

```bash
python3 scripts/plan-ops.py update-phase PHASE_ID --status tests_written
python3 scripts/plan-ops.py batch-check --reset
```

### 3. Find Available Tasks

```bash
plan-ops.py available-tasks --phase PHASE_ID --limit 3
```

This returns a `tasks` array of unblocked pending tasks, **one per story**, capped at `--limit`. Tasks from different stories are safe to parallelize — they work on independent features. The default limit of 3 balances parallelism against context cost.

- If the `tasks` array is **empty** → go to Step 10 (phase gate).
- If the array has **one task** → proceed through Steps 4-8 for that single task (identical to sequential flow).
- If the array has **multiple tasks** → proceed through Steps 4-8 as a batch.

For single-task or single-story execution granularity, use `next-task` instead (unchanged).

### 4. Get Context and Start

For each task in the batch:

```bash
plan-ops.py task-context TASK_ID
plan-ops.py start-task TASK_ID
```

`task-context` calls can run in parallel (read-only). `start-task` calls run sequentially — each writes to the DB, but since batch tasks are always in different stories, the cascades don't conflict.

### 5. Spawn Implementers

Spawn **one implementer subagent per task** (model: **sonnet**), all in a **single message** (parallel Task calls). Each receives its own task context JSON + `output/technical-brief.md`. If `project-workspace/tests/conventions.md` exists (produced by the test-writer in Step 2), include it as additional context — it documents the structural conventions implementers should follow, including environment setup (e.g., venv activation) if applicable.

If `.claude/rules/project-env.md` exists, include its content (project context and doc listing — subagents don't inherit rules files).

All implementers return a JSON report with: `status` (COMPLETE / BLOCKED / PARTIAL), `files_changed` (array), `criteria` (array with `met` boolean), `concerns` (array with `level`: blocker/warning/info), and `blocked_reason`.

### 6. Evaluate Results

Parse each implementer's JSON report and route on the `status` field:

- **`"COMPLETE"`**: Check `files_changed` is non-empty and `all(c.met for c in criteria)`. If any concern has `level: "blocker"` → treat as PARTIAL (retry). Otherwise → add to **completed** list. Log any `warning` concerns.
- **`"BLOCKED"`**: Run `plan-ops.py skip-task TASK_ID --reason "<blocked_reason>"` immediately.
- **`"PARTIAL"`**: Add to **retry** list.

#### 6a. Handle Retries

For each PARTIAL task, re-spawn the implementer **sequentially** (not in parallel — retries include the previous JSON report as feedback). After retry, parse the new JSON:

- `status == "COMPLETE"` and no blocker concerns → add to completed list
- `status == "PARTIAL"` but all unmet criteria are deferrable → add to completed list
- Otherwise → run `skip-task` with the `blocked_reason` or a summary of unmet criteria

**Never retry more than once per task.** Diminishing returns waste context.

### 7. Complete Tasks

Process the completed list **sequentially**:

```bash
plan-ops.py complete-task TASK_ID --files <files_changed array from JSON report> --json
```

The `--files` flag records which files this task changed (taken directly from the implementer's `files_changed` array). The `--json` flag returns structured output — check the `story_completed` field. When a story completes, its `gate_status` is automatically set to `'pending'`.

Collect any tasks where `story_completed` is true into a **gates list**.

Sequential processing is required — `complete-task` cascades to stories/epics and we need the `story_completed` flag from each call.

### 8. Story Gates

For each story in the gates list, run two checks:

**a) Run story tests** — execute the tests the test-writer created for this story's acceptance criteria.

**b) Spawn plan-validator** (model: **sonnet**) with:
- Story acceptance criteria (from `task-context` story description, or `phase-stories`)
- Aggregated files-changed list from `plan-ops.py story-files STORY_ID`
- `output/technical-brief.md`
- Test results from (a)

**If both pass:**

```bash
python3 scripts/plan-ops.py update-story-gate STORY_ID --status passed
```

**If tests fail or review returns FAIL:**

```bash
python3 scripts/plan-ops.py update-story-gate STORY_ID --status failed
```

Present issues to the user. The user decides whether to fix now (spawn targeted implementer) or defer. Do not auto-fix.

Story gates run sequentially — each may need user attention if it fails.

### 9. Budget Check & Repeat

After completing a batch (Steps 3-8), check the context budget before continuing.

```bash
python3 scripts/plan-ops.py batch-check
```

This returns JSON: `{"batch": N, "budget": 8, "stop": false}`. The command increments the counter, writes it to disk, and checks the budget — all procedurally.

- **If `stop` is `true`:** Run `/end-session` to wrap up cleanly (summarize progress, offer git commit, update memory). The end-session report should include clear instructions: **"Run `/clear` to reset context, then `/resume` to continue."** Explain briefly that multiple compaction cycles degrade context quality, and `/clear` gives a fresh window while preserving env vars and rules. Optionally mention `/status` for a broader progress overview before resuming. **Stop — do not proceed to Step 3.**
- **If `stop` is `false`:** Go to Step 3 for the next batch.

#### Auto-Compaction

Auto-compaction may fire between batches (recommended: set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90`). The PreCompact hook (`.claude/hooks/pre-compact.sh`) re-injects critical state from plan.db and durable files. After compaction:
- Re-read `project-workspace/tests/conventions.md` for the test runner command and conventions
- Continue the execution loop from Step 3

### 10. Phase Gate

When no unblocked tasks remain in the phase, first mark the phase as awaiting its gate:

```bash
python3 scripts/plan-ops.py update-phase PHASE_ID --status gate_pending
```

Then:

**a) Run all phase tests** — execute the full test suite the test-writer created for this phase.

**b) Check skipped tasks**: `plan-ops.py list-skipped --phase PHASE_ID`

**c) Spawn plan-validator** (model: **sonnet**) with:
- Phase exit criteria (from `plan-ops.py phase-status`)
- All files created/modified across the phase from `plan-ops.py phase-files PHASE_ID`
- `output/technical-brief.md`
- Skipped task list (if any)
- Test results from (a)

**d) Present to user**:
- Phase test results
- Plan-validator review results
- Skipped tasks with reasons
- Exit criteria status

**User must approve before proceeding to the next phase.**

After user approval:

```bash
python3 scripts/plan-ops.py update-phase PHASE_ID --status complete
```

## Error Recovery

- **Skipped tasks**: Presented at phase boundaries with reasons. The user can:
  - `plan-ops.py retry-task TASK_ID` to reset for another attempt
  - Clarify requirements and retry
  - Defer to a later phase
  - Accept the skip — run `plan-ops.py complete-task TASK_ID` to mark it done and trigger cascade
- **PARTIAL retries**: Maximum one retry per task. The retry includes the original context plus the JSON report from the first attempt.
- **Story review failures**: Present to user — do not auto-fix. The user decides whether to spawn a targeted fix or defer.
- **Undeclared dependencies**: If an implementer reports needing code from a task not listed as a dependency, note it as a discovered dependency. Skip the task and present at the phase boundary. Do not modify plan.db dependencies automatically.

## Execution Granularity
- **Default: Phase** — Execute all tasks within a work-sequence phase
- **Also supported:** Single task, story, or epic when the user specifies
- For single task/story execution, skip the test-writing step (step 2) — tests are phase-scoped

## Notes
- `available-tasks` returns unblocked tasks from independent stories for parallel execution — **one task per story** to prevent file conflicts between concurrent implementers
- `next-task` handles dependency resolution — it only returns tasks whose dependencies are all complete (still used for single-task execution)
- `complete-task` handles cascading — it auto-completes the parent story/epic when all children are done
- `complete-task` also sets `gate_status = 'pending'` on the story when it completes — this is the durable signal for story gate reviews
- `complete-task --files` records files changed per task in plan.db — use `story-files`/`phase-files` to aggregate for reviews
- `complete-task --json` returns structured output with `story_completed`/`epic_completed`/`story_gate_status` for routing
- `start-task` cascades in_progress status up to story, epic, and phase
- `resume-phase` detects session state and returns routing instructions — always call it before entering the execution loop
- `resume-phase` returns `resume_mixed` when both orphaned tasks and pending story gates exist (possible after a batch session crash) — handle orphans first, then gates
- Phase lifecycle: `pending` → `tests_written` → `in_progress` → `gate_pending` → `complete`
- Skipped tasks prevent their parent story from auto-completing — this is correct behavior
- The batch counter is managed by `batch-check` (file-based at `output/.session-batch-count`) — procedural, survives compaction
- Auto-compaction is handled by the PreCompact hook (`.claude/hooks/pre-compact.sh`) which re-injects critical state from plan.db
- Static batch budget of 8 is a safety net — compaction handles the typical case. `/end-session` + `/clear` + `/resume` handle the budget-exceeded case
- When the batch budget is reached, `/clear` + `/resume` is sufficient to continue — no need to exit Claude Code. `/clear` resets the context window and reloads CLAUDE.md and rules files; env vars from `./clyde` persist in the same process. `/status` is available for a broader overview but not required — `/resume` reports the active phase state before entering the loop
- Test commands that `cd` into subdirectories must use subshell syntax `(cd ... && command)` to prevent CWD drift — bare `cd ... && command` shifts CWD for all subsequent Bash calls, breaking relative `plan-ops.py` invocations
