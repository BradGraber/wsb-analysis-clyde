# Clyde Lifecycle Reference

Complete step-by-step reference for the Clyde framework, from fresh clone through implementation. For the quick-start version, see [README.md](README.md).

## Overview

Clyde has two major phases separated by a user approval checkpoint:

```
Clone → Init → Add Inputs → Intake Phase → [approval] → Implementation Phase
                                                              ↓
                                                    Phase A → Phase B → ... → Done
```

The **Intake Phase** (`/analyze`) transforms your input files into a structured plan database and a verified technical brief. The **Implementation Phase** executes the plan phase-by-phase using a test-first, gate-checked orchestrator loop.

Throughout both phases, Clyde uses an **orchestrator + subagent** architecture to stay within context limits. The orchestrator (your main Claude Code session) stays lean — it queries the database, gathers context, and delegates heavy work to focused subagents that each get a clean context window.

---

## Phase 0: Project Setup

### Clone

```bash
git clone https://github.com/BradGraber/clyde.git my-project
cd my-project
```

### Initialize (`/init`)

The `./clyde` launcher detects a fresh clone and runs `/init` automatically. Initialization:

1. **Renames the `origin` remote to `clyde`** — preserves the upstream connection for future `/update` pulls while preventing accidental pushes to the framework repo.
2. **Optionally squashes git history** — recommended, since the framework's development history isn't relevant to your project. Creates a single clean "Initialize project" commit.
3. **Optionally sets a new `origin` remote** — point to your project's own repo if you have one ready.
4. **Removes the init gate** — deletes `.claude/rules/init-gate.md`, which blocks all other workflows until init completes.

After init, the project is standalone. The `clyde` remote remains available for pulling framework updates via `/update`.

### Configure Permissions (`/setup`, optional)

Clyde ships with conservative shared permissions (read-only git, sqlite3). `/setup` walks you through opting into broader auto-approvals:

- **Git write operations** — `Bash(git *)` (recommended) or granular per-command
- **File operations** — `Edit`, `Write`
- **Web access** — `WebFetch`, `WebSearch`
- **Build tools** — `npm`, `python`, `make`, etc.

Settings are written to `.claude/settings.local.json` (gitignored, personal to your clone). Shared deny rules (no `rm -rf`, no force push, no `reset --hard`) always apply regardless.

### Add Inputs

Place your pre-built project plan in `input/`:

```
input/
├── PRD.md                     # Product requirements document (source of truth)
├── work-sequence.md           # Phased execution plan with entry/exit criteria
├── epics/epic-NNN.md          # Epic definitions with YAML frontmatter
├── stories/story-NNN-NNN.md   # Story definitions with YAML frontmatter
└── tasks/task-NNN-NNN-NN.md   # Task definitions with YAML frontmatter
```

These files are **read-only** after this point — Clyde never modifies them. See `examples/input/` for format references.

---

## Intake Phase (`/analyze`)

The Intake Phase reads your inputs and produces two verified artifacts: `output/plan.db` and `output/technical-brief.md`. Run it with:

```
> /analyze
```

### Step 1: Scan Inputs

The orchestrator inventories `input/` without reading file contents:
- Confirms `PRD.md` and `work-sequence.md` exist (both required)
- Counts files in `epics/`, `stories/`, `tasks/`
- Presents the inventory for confirmation

### Step 2: Build Structured Data

Runs `scripts/build-plan-db.py`, a deterministic Python script (zero external dependencies) that:
- Parses YAML frontmatter from every epic, story, and task file
- Creates `output/plan.db` with the schema from `schema.sql`
- Inserts all epics, stories, tasks, and their dependency relationships
- Runs count reconciliation (files found vs rows inserted)
- Reports warnings for missing fields, parse errors, or orphaned dependencies

**Note:** Phases are not inserted here — the work-sequence format is too freeform for deterministic parsing. That's handled in step 3.

### Step 3: Extract Phases + Draft Brief (parallel)

Two subagents run in parallel:

#### Phase Extractor (sonnet)
Reads `input/work-sequence.md` and returns a JSON array of phase objects with:
- Phase ID, name, sequence order, goal
- Entry and exit criteria (full text preserved)
- Estimated duration
- Mapped items (which epics/stories belong to each phase)

The orchestrator pipes this JSON to `scripts/insert-phases.py` to populate the `phases` and `phase_items` tables.

#### Tech Brief Drafter (sonnet)
Reads `input/PRD.md` and extracts every system-wide technical detail into a draft brief:
- Tech stack, architecture, database schema, conventions, environment setup, constraints
- Only includes what the PRD explicitly states — never invents
- Excludes epic-specific details (algorithm thresholds, UI specs, endpoint lists)

The draft is typically 200-500+ lines and will be compressed in step 5.

### Step 4: Execute Subagent Output

The orchestrator takes the output from both agents:
1. Inserts the phase JSON into `plan.db` via `insert-phases.py`
2. Writes the draft brief to `output/technical-brief.md`

### Step 5: Compress Brief + Verify Database (parallel)

Two independent workflows run in parallel:

#### 5A: Compress Technical Brief (iterative loop)

Target: 50-100 non-blank lines.

1. **Check length** — if already in range, skip compression
2. **Compress** — the **tech-brief-compressor** agent (sonnet) reduces the draft while preserving all PRD-sourced system-wide context. Uses tables for dense data, bullets for conventions, prose sparingly.
3. **Review** — the **tech-brief-reviewer** agent (sonnet) checks the compressed brief on four axes:
   - **Accuracy** — contradictions with the PRD
   - **Completeness** — missing system-wide technical details
   - **Length** — within the 50-100 line target
   - **Inferences** — claims not sourced from the PRD (flagged for user review, not treated as failures)

The review result routes:
- **PASS** — compression complete
- **FAIL** — loops back to compress with the review feedback (max 3 iterations)
- **REVIEW NEEDED** — accuracy/completeness pass but inferences exist; presented to the user for approval

#### 5B: Verify Plan Database (script)

Runs `plan-ops.py verify-intake` — a fully procedural check (no AI involved):
- **Count completeness** — actual DB rows match expected file counts
- **Referential integrity** — no orphaned stories, tasks, or phase items
- **Data quality** — no missing titles, no phases without criteria
- **Status defaults** — all items start as `pending`
- **Technical brief existence** — file exists and has content

Returns a JSON report with `overall: PASS/FAIL` and an `issues` array.

### Step 6: Fact-Check Brief

After both step 5 workflows pass, the **tech-brief-fact-checker** agent (sonnet) does claim-by-claim verification:
- Works through the brief line by line
- For each factual claim (numbers, lists, formulas, named values), uses Grep to find the corresponding PRD source
- Records matches, mismatches, and claims with no PRD source

If errors are found, they're fed back through the compressor for correction, then fact-checked once more. Remaining errors are presented to the user.

### Step 7: Resolve Issues

If any verification step found problems, the orchestrator presents them to the user for resolution before proceeding.

### Step 8: Present for Approval

The orchestrator shows:
- Summary statistics (epic/story/task/phase counts)
- The technical brief content
- Any flags, concerns, or unresolved inferences
- Whether compression iterations or fact-checker corrections were needed

**The user must explicitly approve before moving to the Implementation Phase.**

---

## Implementation Phase

The Implementation Phase executes the plan one phase at a time. The main conversation acts as an orchestrator, spawning subagents for heavy work and tracking all progress in `plan.db`.

All database operations go through `scripts/plan-ops.py` — raw SQL is never written against `plan.db`.

### Step 1: Check Phase Entry Criteria

```bash
python3 scripts/plan-ops.py phase-status PHASE_ID
```

Review the phase's entry criteria before starting work. Entry criteria typically reference completion of prior phases or availability of external dependencies.

### Step 2: Write Tests (test-first)

The **test-writer** agent (sonnet) receives:
- All story acceptance criteria in the phase (from `plan-ops.py phase-stories`)
- All task descriptions in the phase (from `plan-ops.py phase-tasks`) — these provide structural hints like file paths, naming conventions, and config keys that the test-writer uses for structural decisions
- Phase exit criteria
- The technical brief

It produces:
- Behavioral test files organized by story — one test file per story or logical grouping
- Integration tests for phase-level exit criteria where applicable
- A **conventions document** (`project-workspace/tests/conventions.md`) — documents the structural decisions made (module paths, naming patterns, import conventions, fixture API) so implementers can follow them
- A test runner command for the orchestrator to use in later gates

All tests are expected to **fail initially** — no implementation exists yet. Tests define "done" for the phase.

**Note:** Test writing is skipped when executing a single task or story (tests are phase-scoped).

### Step 3: Find Available Tasks

```bash
python3 scripts/plan-ops.py available-tasks --phase PHASE_ID --limit 3
```

Returns a `tasks` array of unblocked pending tasks, **one per story**, capped at `--limit`. Tasks from different stories are safe to parallelize — they work on independent features. The one-per-story constraint prevents file conflicts between concurrent implementers.

- If the `tasks` array is **empty** → go to Step 10 (Phase Gate).
- If the array has **one task** → proceed through Steps 4-8 for that single task.
- If the array has **multiple tasks** → proceed through Steps 4-8 as a batch.

Dependency resolution is automatic — a task is only returned if all of its dependencies (at the task, story, and epic levels) are complete.

### Step 4: Get Context and Start

For each task in the batch:

```bash
python3 scripts/plan-ops.py task-context TASK_ID
python3 scripts/plan-ops.py start-task TASK_ID
```

`task-context` returns a JSON object with the full task details, parent story (with acceptance criteria), parent epic, and dependency list. `start-task` sets the task to `in_progress` and cascades the status up to its story, epic, and phase if they're still `pending` (or `tests_written` for phases).

`task-context` calls can run in parallel (read-only). `start-task` calls run sequentially.

### Step 5: Spawn Implementers

Spawn **one implementer agent** (sonnet) per task, all in a **single message** (parallel Task calls). Each receives:
- Its own task context JSON from Step 4
- `output/technical-brief.md`
- `project-workspace/tests/conventions.md` (if it exists) — structural conventions from the test-writer that the implementer should follow

Each implementer reads the technical brief and conventions document, reviews existing code in `project-workspace/`, writes code in `project-workspace/src/`, and returns a **JSON report**:

```json
{
  "status": "COMPLETE",
  "files_changed": ["project-workspace/src/path/to/file.py"],
  "criteria": [
    {"criterion": "description", "met": true, "evidence": "how it was met"}
  ],
  "concerns": [
    {"level": "warning", "text": "description of concern"}
  ],
  "blocked_reason": null
}
```

- `status`: `COMPLETE`, `BLOCKED`, or `PARTIAL`
- `files_changed`: relative paths for every file created or modified
- `criteria`: one entry per acceptance criterion with a `met` boolean
- `concerns`: array with explicit `level` — `blocker` (prevents completion), `warning` (proceed but flag), or `info` (informational)
- `blocked_reason`: what's needed to unblock (only when BLOCKED)

### Step 6: Evaluate Results

Parse each implementer's JSON report and route on the `status` field:

- **`"COMPLETE"`** — check `files_changed` is non-empty and `all(c.met for c in criteria)`. If any concern has `level: "blocker"` → treat as PARTIAL (retry). Otherwise → add to **completed** list. Log any `warning` concerns.
- **`"BLOCKED"`** — skip immediately: `plan-ops.py skip-task TASK_ID --reason "<blocked_reason>"`.
- **`"PARTIAL"`** — add to **retry** list.

#### Step 6a: Handle Retries

For each PARTIAL task, re-spawn the implementer **sequentially** (not in parallel — retries include the previous JSON report as feedback). After retry, parse the new JSON:
- `status == "COMPLETE"` and no blocker concerns → add to completed list
- `status == "PARTIAL"` but all unmet criteria are deferrable → add to completed list
- Otherwise → skip the task with the `blocked_reason` or a summary of unmet criteria

**Never retry more than once per task.** Diminishing returns waste context.

### Step 7: Complete Tasks

Process the completed list **sequentially**:

```bash
python3 scripts/plan-ops.py complete-task TASK_ID --files file1.py file2.py --json
```

Records which files the task changed (stored in `plan.db` for downstream reviews) and returns structured JSON:

```json
{
  "task_id": "task-001-001-01",
  "story_completed": true,
  "story_gate_status": "pending",
  "epic_completed": false,
  "remaining_tasks": 0,
  "skipped_tasks": 0,
  "files_recorded": ["file1.py", "file2.py"]
}
```

When a story completes, its `gate_status` is automatically set to `'pending'` in the database — this is the durable signal that a story gate review is needed.

Collect any tasks where `story_completed` is true into a **gates list**. Sequential processing is required — `complete-task` cascades to stories/epics and we need the `story_completed` flag from each call.

### Step 8: Story Gates

For each story in the gates list, two quality checks run:

#### a) Run Story Tests
Execute the tests the test-writer created for this story's acceptance criteria.

#### b) Story Review
The **plan-validator** agent (sonnet) receives:
- Story acceptance criteria
- Aggregated files changed across the story (from `plan-ops.py story-files STORY_ID`)
- The technical brief
- Test results from (a)

It reads every changed file and returns:
- Per-criterion assessment (MET / NOT MET)
- Technical brief alignment check
- Specific issues with file paths and line references
- Overall: PASS / FAIL

**If both pass** → `plan-ops.py update-story-gate STORY_ID --status passed`.

**If tests fail or review returns FAIL** → `plan-ops.py update-story-gate STORY_ID --status failed`. Issues are presented to the user. The user decides whether to fix now (spawn a targeted implementer) or defer. The orchestrator does **not** auto-fix.

Story gates run sequentially — each may need user attention if it fails.

### Step 9: Budget Check & Repeat

After completing a batch (Steps 3-8), check the context budget before continuing.

The batch counter is stored in `output/.session-batch-count` (a file, not conversation context — survives compaction). It's initialized to 0 at the start of each session and incremented after each batch. The budget is **8 batches per session**.

- **If counter >= 8:** Run `/end-session` to wrap up cleanly, then stop. The user resumes with `/resume`.
- **If counter < 8:** Return to Step 3 for the next batch.

Auto-compaction may fire between batches. The PreCompact hook (`.claude/hooks/pre-compact.sh`) re-injects critical state from plan.db so the orchestrator can continue working after compaction. See [Context Management](#context-management) below for details.

### Step 10: Phase Gate

When no unblocked tasks remain in the phase, four things happen:

#### a) Run All Phase Tests
Execute the full test suite the test-writer created for this phase.

#### b) Check Skipped Tasks
```bash
python3 scripts/plan-ops.py list-skipped --phase PHASE_ID
```

#### c) Phase Review
The **plan-validator** agent (sonnet) receives:
- Phase exit criteria (from `plan-ops.py phase-status`)
- All files created/modified across the phase (from `plan-ops.py phase-files PHASE_ID`)
- The technical brief
- Skipped task list (if any)
- Test results from (a)

It returns:
- Per-exit-criterion assessment (MET / NOT MET)
- Cross-story integration check (API mismatches, shared state conflicts)
- Skipped task impact assessment
- Overall: PASS / FAIL

#### d) Present to User
The orchestrator shows:
- Phase test results
- Plan-validator review results
- Skipped tasks with reasons
- Exit criteria status

**The user must approve before proceeding to the next phase.**

---

## Error Recovery

### Skipped Tasks

Tasks are skipped when the implementer returns BLOCKED or when a PARTIAL retry fails. Each skip includes a reason stored in `plan.db`. Skipped tasks:

- Are surfaced at phase boundaries with their reasons
- Prevent their parent story from auto-completing (by design)
- Can be retried: `plan-ops.py retry-task TASK_ID` resets to `pending`
- Can be force-completed: `plan-ops.py complete-task TASK_ID` marks done and triggers cascade
- Can be deferred to a later phase

### Partial Retries

Maximum one retry per task. The retry includes the original context plus the JSON report from the first attempt, so the implementer can build on what was already done.

### Story Review Failures

When the plan-validator or tests fail at a story gate, the issues are presented to the user. Options:
- Spawn a targeted implementer to fix specific issues
- Defer the fix to a later phase
- Accept the current state

The orchestrator never auto-fixes review failures.

### Undeclared Dependencies

If an implementer reports needing code from a task not listed as a dependency, the task is skipped with a note about the discovered dependency. The issue is presented at the phase boundary. `plan.db` dependencies are never modified automatically.

---

## Session Resumability

The Implementation Phase is designed to survive session crashes and be resumable from any point. All durable state lives in `plan.db`.

### How Resume Detection Works

At the start of any "implement phase X" request, the orchestrator runs:

```bash
python3 scripts/plan-ops.py resume-phase PHASE_ID
```

This returns a JSON object with a `resume_action` field that routes to the correct step:

| Phase Status | Condition | `resume_action` | Resume Point |
|-------------|-----------|-----------------|--------------|
| `pending` | — | `start_fresh` | Step 1 (normal start) |
| `tests_written` | No orphans | `find_next_task` | Step 3 (skip test writing) |
| `tests_written` or `in_progress` | In-progress tasks exist (no pending gates) | `resume_orphan` | Step 5 (re-implement orphaned tasks as batch) |
| `in_progress` | Both orphans AND pending gates | `resume_mixed` | Step 5 (orphans first, then gates, then Step 3) |
| `in_progress` | Pending story gates (no orphans) | `run_story_gate` | Step 8 (run skipped gate) |
| `gate_pending` | — | `run_phase_gate` | Step 10 (re-run phase gate) |
| `complete` | — | `already_complete` | Done (suggest next phase) |

### Crash Scenarios and Recovery

**Crash after test writing, before any task starts:**
Phase status is `tests_written`. Resume skips to Step 3 — tests already exist on disk.

**Crash mid-task (after `start-task`, before `complete-task`):**
One or more tasks are left `in_progress` in the database. `resume-phase` detects them as orphans. The orchestrator spawns implementers for all orphaned tasks as a batch (parallel Task calls) without calling `start-task` again, then continues normally.

**Crash mid-batch (some tasks completed, others still in progress):**
With batch execution, a session crash can leave both completed stories (with `gate_status = 'pending'`) and orphaned `in_progress` tasks. `resume-phase` detects this mixed state and returns `resume_mixed`. The orchestrator handles orphans first (they may complete more stories), then runs all pending story gates, then continues to Step 3.

**Crash after task completion, before story gate:**
The story's `gate_status` is `'pending'` (set atomically by `complete-task`). `resume-phase` detects the pending gate and routes to Step 8.

**Crash after all tasks done, before phase gate:**
Phase status is `gate_pending` (set at the start of Step 10). `resume-phase` routes directly to Step 10 to re-run tests and the phase review.

**Crash after phase gate passes, before user approval:**
Phase status is still `gate_pending` (only set to `complete` after user approves). `resume-phase` routes to Step 10 — the gate re-runs and presents results again.

---

## Status Tracking

### Task / Story / Epic State Machine

Every epic, story, and task follows this status progression:

```
pending → in_progress → complete
                ↘
               skipped
```

- `start-task` cascades `in_progress` upward (task → story → epic → phase)
- `complete-task` cascades `complete` upward when all siblings are done
- `complete-task` also sets `gate_status = 'pending'` on the story when it completes
- `skip-task` does **not** cascade — skipped tasks block story auto-completion
- `retry-task` resets `skipped` → `pending`

### Phase Lifecycle

Phases have their own status column tracking the execution lifecycle:

```
pending → tests_written → in_progress → gate_pending → complete
```

- `pending` — phase has never been started
- `tests_written` — Step 2 (test-writer) has run, tests exist on disk
- `in_progress` — at least one task has been started (set automatically by `start-task`)
- `gate_pending` — all tasks done/skipped, awaiting phase gate review
- `complete` — phase gate passed and user approved

### Story Gate Tracking

Stories have a `gate_status` column that tracks whether their quality gate has been run:

- `NULL` — story has not completed yet (no gate needed)
- `'pending'` — story completed (all tasks done) but gate review has not run
- `'passed'` — story gate (tests + plan-validator) passed
- `'failed'` — story gate failed (presented to user)

This is set automatically by `complete-task` when a story completes, and updated by the orchestrator after the gate review runs.

### Files Changed Tracking

Each task records which files it created or modified (stored as JSON in `plan.db`). This data aggregates at higher levels:

- `story-files STORY_ID` — all files changed across a story's tasks
- `phase-files PHASE_ID` — all files changed across a phase's tasks

These aggregations feed into the plan-validator at story and phase gates.

### Progress Queries

```bash
plan-ops.py progress           # Overall counts + phase percentages + phase statuses
plan-ops.py phase-status ID    # Phase detail with entry/exit criteria and lifecycle status
plan-ops.py list-skipped       # All skipped tasks with reasons
plan-ops.py next-task          # Next unblocked pending task (single task)
plan-ops.py available-tasks    # All unblocked pending tasks, one per story (for batch execution)
plan-ops.py resume-phase ID    # Session resume detection with routing instructions
plan-ops.py search "term"      # Full-text search across all plan items (JSON)
```

---

## Session Management

### `/status`

Shows current project state: progress counts, in-progress tasks, skipped tasks, and suggests the next action.

### `/resume`

Resumes implementation from where the last session left off. Auto-detects the active phase via `plan-ops.py active-phase`, resets the batch counter, and enters the implementation loop at the correct step based on `resume-phase` routing. Use after `/clear` to continue a phase.

### `/end-session`

Wraps up the current session:
1. Summarizes what was accomplished
2. Checks `plan.db` progress (highlights in-progress tasks that need resuming)
3. Checks for uncommitted git changes
4. Updates memory files
5. Lists open items for next session

### `/logs`

Manages implementation phase logging. Logging captures subagent transcripts and orchestrator tool calls for debugging and prompt improvement. Off by default — opt in per project.

```
> /logs           # Show status (on/off, file count, size)
> /logs on        # Enable logging
> /logs off       # Disable logging (preserves existing logs)
> /logs clear     # Delete log files
```

When enabled, hook scripts in `.claude/hooks/` capture:
- **Subagent transcripts** (`SubagentStop` hook) — full JSONL copy of each subagent's conversation, saved as individual files in `output/logs/`
- **Orchestrator tool calls** (`PostToolUse`/`PostToolUseFailure` hooks) — every `Bash` and `Task` call with input and response, appended to `output/logs/orchestrator.jsonl`
- **Session boundaries** (`SessionStart`/`SessionEnd` hooks) — markers in `orchestrator.jsonl`

Logs are stored in `output/logs/` (gitignored). A flag file `output/logs/.enabled` controls whether the hooks write anything — no flag means zero overhead.

### `/update`

Pulls framework updates from the upstream `clyde` remote:
1. Runs `scripts/update-framework.py diff` to show what changed
2. Asks for confirmation
3. Applies changes — only touches framework-owned paths (listed in `.claude/framework-manifest`)
4. Never modifies `project-workspace/`, `input/`, or `output/`

---

## Context Management

The Implementation Phase uses a two-layer approach to manage context window usage:

### Layer 1: Compaction Guardrails (primary)

Auto-compaction fires when the context window fills up. By default this can cause unpredictable information loss. Clyde makes compaction reliable through:

- **Compact Instructions** (in `CLAUDE.md`) — tells the orchestrator what to preserve during compaction and where to re-read critical data from durable sources
- **PreCompact hook** (`.claude/hooks/pre-compact.sh`) — fires before compaction and re-injects critical orchestrator state from plan.db: active phase, resume routing, test runner command, and batch counter
- **Durable storage** — the test runner command is stored in `project-workspace/tests/conventions.md` (on disk), the batch counter in `output/.session-batch-count`, and all task/story/phase state in `output/plan.db`

The orchestrator can continue working after compaction because all critical state is reconstructed from durable sources.

**Recommended:** Set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90` in your environment. This triggers compaction at 90% capacity instead of the default 95%, giving 10% headroom for the PreCompact hook to inject state before the context limit.

### Layer 2: Safety Budget (backstop)

After multiple compaction cycles, summary quality degrades (summary of a summary). A static batch budget of **8 batches per session** acts as an emergency brake:

- The batch counter is stored in `output/.session-batch-count`
- After 8 batches, the orchestrator runs `/end-session` and stops
- The user resumes with `/clear` → `/resume`
- `resume-phase` handles all mid-session states cleanly — no progress is lost

In practice, compaction handles the typical case and the budget rarely fires.

---

## Subagent Summary

| Agent | Phase | Model | Role |
|-------|-------|-------|------|
| phase-extractor | Intake | sonnet | Extracts phase data from work-sequence.md as JSON |
| tech-brief-drafter | Intake | sonnet | Extracts system-wide technical details from PRD into draft brief |
| tech-brief-compressor | Intake | sonnet | Compresses draft brief to 50-100 lines preserving accuracy |
| tech-brief-reviewer | Intake | sonnet | Reviews brief for accuracy, completeness, length, and inferences |
| tech-brief-fact-checker | Intake | sonnet | Claim-by-claim verification of brief against PRD using Grep |
| test-writer | Implementation | sonnet | Writes failing tests from acceptance criteria + task structural hints, produces conventions document |
| implementer | Implementation | sonnet | Writes code for a single task following conventions document, returns JSON report |
| plan-validator | Implementation | sonnet | Reviews implementation at story and phase gates |

---

## Script Summary

| Script | Purpose |
|--------|---------|
| `scripts/build-plan-db.py` | Parses input files, creates plan.db with epics/stories/tasks/dependencies |
| `scripts/insert-phases.py` | Inserts phase JSON (from phase-extractor) into plan.db |
| `scripts/plan-ops.py` | All runtime queries and updates against plan.db (15+ subcommands) |
| `scripts/update-framework.py` | Diff and apply framework updates from the clyde remote |
| `scripts/manage-logs.sh` | Enable, disable, clear, or check status of implementation phase logging |
