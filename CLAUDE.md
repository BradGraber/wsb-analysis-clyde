# Clyde

Clyde is a reusable framework for Claude Code-driven software development. Clone this repo fresh for each new project, add your input files, and let Claude analyze and build.

## Two-Phase Workflow

### Intake Phase (`/analyze`)
- Run via the `/analyze` skill — one-time project initialization
- Scans `input/`, builds `output/plan.db`, generates `output/technical-brief.md`
- Review with user before proceeding

### Implementation Phase
- Orchestrator queries `output/plan.db` for next work item
- Spawns implementer subagent with focused context (task + story + epic + technical brief)
- Subagent builds in `project-workspace/src/`, returns results
- Orchestrator updates task status in `plan.db`
- Default execution unit is phase (from work-sequence), but task/story/epic also supported

## Directory Structure

- `input/` — Pre-built project plan — READ ONLY
  - `PRD.md` — Product requirements document
  - `epics/epic-NNN.md` — Epic definitions with YAML frontmatter
  - `stories/story-NNN-NNN.md` — Story definitions with YAML frontmatter
  - `tasks/task-NNN-NNN-NN.md` — Task definitions with YAML frontmatter
  - `work-sequence.md` — Phased execution plan with entry/exit criteria
- `output/` — Generated artifacts
  - `plan.db` — SQLite database (plan + progress tracking)
  - `technical-brief.md` — Distilled tech reference from PRD
- `project-workspace/` — The project workspace (source code in `src/`)
- `.claude/rules/` — Clyde's permanent framework rules
- `.claude/agents/` — Subagent definitions
  - Intake (analyze): tech-brief-drafter, tech-brief-compressor, tech-brief-reviewer, tech-brief-fact-checker, phase-extractor
  - Implementation: implementer, test-writer, plan-validator
- `.claude/framework-manifest` — Lists framework-owned paths for `/update`

## Rules

- Never commit or push without the user explicitly asking you to
- Always use single-line commit messages — multi-line `-m` strings break `Bash(git *)` permission matching
- Never modify files in `input/` — they are read-only source material
- The PRD and plan in `input/` are the source of truth for requirements
- `output/plan.db` is the source of truth for progress and execution state
- `output/technical-brief.md` is the concise tech reference — subagents read this, not the full PRD
- All built software goes in `project-workspace/src/`
- Use the orchestrator + subagent model to manage context
