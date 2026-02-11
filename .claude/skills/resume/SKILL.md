---
name: resume
description: Resume implementation from where the last session left off
user_invocable: true
---

# Resume

Auto-detect the active phase and resume the implementation loop from where the last session left off.

## Steps

### 1. Find Active Phase

```bash
python3 scripts/plan-ops.py active-phase
```

This returns JSON with the currently active phase (status: `in_progress`, `tests_written`, or `gate_pending`).

- If `phase_id` is `null`:
  - Run `python3 scripts/plan-ops.py progress` to check if all phases are complete or all are pending.
  - **All complete** → Report: "All phases are complete."
  - **All pending** → Report: "No implementation in progress. Use `implement phase-X` to begin a phase."
  - Stop here — do not proceed.

### 2. Detect Resume State

```bash
python3 scripts/plan-ops.py resume-phase PHASE_ID
```

Report the detected state to the user:
- Phase name and status
- Resume action and what it means
- Any orphaned tasks or pending story gates

### 3. Reset Batch Counter

```bash
python3 scripts/plan-ops.py batch-check --reset
```

### 4. Enter Implementation Loop

Follow the `resume_action` from step 2 per the Resume Detection section in `.claude/rules/implementation-phase.md`. The batch budget is 8.

- **`find_next_task`** → Go to Step 3 (Find Available Tasks) in the execution loop
- **`resume_orphan`** → Process orphaned tasks as a batch (Step 5), then continue to Step 3
- **`resume_mixed`** → Handle orphans first, then pending story gates, then Step 3
- **`run_story_gate`** → Run pending story gates (Step 8), then Step 3
- **`run_phase_gate`** → Go directly to Step 10 (Phase Gate)
- **`start_fresh`** → Go to Step 1 (Check Phase Entry Criteria) — note: this is unusual for `/resume`, it means the phase was started but never got past entry criteria
- **`already_complete`** → Report that the phase is done and suggest the next pending phase
