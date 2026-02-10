---
name: analyze
description: Analyze input files to build plan.db and technical brief (Intake Phase)
user_invocable: true
---

# Intake Phase: Analyze

Follow this orchestrator workflow. The main conversation stays lean — heavy work is delegated to subagents.

## Step 1: Scan Inputs (you do this)

Quickly inventory `input/` without reading file contents:
- Glob for `input/PRD.md` and `input/work-sequence.md` — both are required
- Count files in `input/epics/`, `input/stories/`, `input/tasks/`
- Present the inventory to the user:
  ```
  Found: PRD.md, work-sequence.md
  Epics: X files
  Stories: Y files
  Tasks: Z files
  ```
- If PRD.md or work-sequence.md is missing, stop and ask the user
- If any directory is empty, flag it and confirm with the user before proceeding

## Step 2: Build Structured Data (you do this)

Run the build script to create `output/plan.db` with epics, stories, tasks, and dependencies:

```bash
python3 scripts/build-plan-db.py
```

This creates the `output/` directory and database. Check the output for warnings or count mismatches. If there are errors, investigate before proceeding.

## Step 3: Extract Phases + Generate Draft Brief (parallel subagents)

Spawn **two agents in parallel** using the exact prompts below. Replace `{{placeholders}}` with actual values from steps 1-2.

### 3a: Phase Extractor (model: **sonnet**)

```
Input scan found {{X}} epics, {{Y}} stories, {{Z}} tasks.
Build script result: {{build output summary}}

Read input/work-sequence.md and extract phase data.
Return the result in the format specified in your instructions.
```

### 3b: Tech Brief Drafter (model: **sonnet**)

```
Read input/PRD.md and extract all system-wide technical details into a draft technical brief.
Return the result in the format specified in your instructions.
```

## Step 4: Execute Subagent Output (you do this)

Take the returned content from both agents and execute it:
1. Extract the JSON array from the phase-extractor's "Phase JSON" section
2. Pipe the JSON to the insert script via stdin: `echo '<json>' | python3 scripts/insert-phases.py output/plan.db`
3. Write the technical brief draft to `output/technical-brief.md`

## Step 5: Compress Brief + Verify Database (parallel)

After step 4, two independent workflows can run in parallel:

### 5A: Compress Technical Brief (iterative loop)

The tech-brief-drafter's output will likely be too long (200-500+ lines). This compresses it to 50-100 lines while preserving accuracy against the PRD.

#### 5A.1: Check Length

Count the non-blank lines in `output/technical-brief.md`. If already 50-100 lines, skip compression.

#### 5A.2: Compress

Spawn the **tech-brief-compressor** agent (model: **sonnet**) with this prompt. On retries, include the review feedback section.

```
Compress the technical brief to 50-100 non-blank lines.
Read output/technical-brief.md as the draft to compress.
Read input/PRD.md as ground truth — remove anything not sourced from the PRD.

{{IF RETRY: --- REVIEW FEEDBACK ---
{{review feedback from 5A.3}}
--- END FEEDBACK ---}}
```

Write the tech-brief-compressor's returned markdown to `output/technical-brief.md`. **Do NOT manually edit the brief** — if the content needs changes, route it back through the compress-review loop.

#### 5A.3: Review

Spawn the **tech-brief-reviewer** agent (model: **sonnet**) with this prompt:

```
Review the technical brief for accuracy and completeness against the PRD.
Read output/technical-brief.md and input/PRD.md, then return your assessment.
```

**Handling the result:**

- **PASS** → compression complete
- **FAIL** (accuracy, completeness, or length issues) → go to 5A.2 with the review feedback. Maximum 3 iterations of the compress-review loop. If still failing after 3 iterations, stop and present issues to the user.
- **REVIEW NEEDED** (accuracy/completeness pass, but inferences flagged) → compression complete. Present the inferences to the user during Step 7 so they can approve or reject each one. Do NOT auto-iterate on inferences — they require human judgment.

**Important:** The orchestrator must never edit `output/technical-brief.md` directly. All brief content comes from the tech-brief-compressor (or tech-brief-drafter if no compression needed). If the tech-brief-compressor undershoots or overshoots the line target, that's a length FAIL for the tech-brief-reviewer to catch — do not fix it manually.

### 5B: Verify Plan Database (plan-validator agent)

Spawn the **plan-validator** agent (model: **sonnet**) with this prompt. Launch in parallel with 5A.

```
Verify output/plan.db for Intake Phase completeness.
Expected counts: {{X}} epics, {{Y}} stories, {{Z}} tasks.
Run the checks specified in your instructions and return your report.
```

The plan-validator does not depend on the final brief — it only checks that the file exists and has content.

## Step 6: Fact-Check Brief (one-time, after compression loop)

After the compress-review loop (5A) passes and the plan-validator (5B) passes, run a final claim-by-claim verification of the brief.

Spawn the **tech-brief-fact-checker** agent (model: **sonnet**) with this prompt:

```
Verify every factual claim in the technical brief against the PRD.
Read output/technical-brief.md and use Grep to search input/PRD.md for each claim.
Return your fact check report as specified in your instructions.
```

**Handling the result:**

- **PASS** → proceed to Step 8
- **FAIL** → feed the errors back to the tech-brief-compressor as review feedback (same as a 5A.2 retry), then re-run the tech-brief-fact-checker once. If it still fails, present the remaining errors to the user in Step 8.

## Step 7: Resolve Issues (you do this, if needed)

If the plan-validator (5B) or tech-brief-fact-checker (Step 6) found issues:
- Present the issues to the user
- Decide whether to re-run agents for fixes, manually correct, or accept as-is
- Re-verify if corrections were made

## Step 8: Present for Approval (you do this)

Once verification passes, run:

```bash
python3 scripts/plan-ops.py progress
```

Then:
- Show the summary stats to the user
- Show the technical brief content (or a summary if the user prefers)
- Present any flags or concerns from the tech-brief-drafter
- Note if the brief required compression iterations, tech-brief-fact-checker corrections, or any unresolved issues
- Wait for user approval before moving to the Implementation Phase

**Do not proceed to the Implementation Phase until the user explicitly approves.**
