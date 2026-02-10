# Clyde

A reusable framework for Claude Code-driven software development. Clone it fresh for each new project, drop in your pre-built plan, and let Claude analyze and build.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed and authenticated
- [Python 3](https://www.python.org/) (3.8+, no external dependencies required)
- [SQLite3](https://www.sqlite.org/) installed and on your PATH (used for plan storage and progress tracking)
- A pre-built project plan consisting of:
  - A Product Requirements Document (PRD)
  - Epics, stories, and tasks as markdown files with YAML frontmatter
  - A work-sequence file defining phased execution order

See `examples/input/` for format references.

## Quick Start

### 1. Clone

```bash
git clone https://github.com/BradGraber/clyde.git my-project
cd my-project
```

### 2. Launch

```bash
./clyde
```

The `clyde` launcher is a small script that starts Claude Code and auto-detects project state. On a fresh clone it runs `/init`; on an initialized project it runs `/status` to show progress and suggest the next action. Use it every time — it's the single entry point.

### 3. Initialize (`/init`)

On first launch, `./clyde` detects the fresh clone and kicks off `/init` automatically. It walks you through three choices:

- **Renames the Clyde remote** from `origin` to `clyde` — keeps it for future `/update` pulls, prevents accidental pushes to the framework
- **Squash or keep history** — squashing to a single clean commit is recommended, since the framework's development history isn't relevant to your project
- **Set a new remote** if you already have a repo ready, or skip and add one later

A gate rule blocks `/analyze` and all other workflows until `/init` has been completed.

### 4. Set Up Permissions (`/setup`, optional)

Clyde ships with conservative shared permissions (read-only git, sqlite3). `/setup` lets you opt into broader auto-approvals for your local environment — git writes, file editing, web access, build tools — so Claude doesn't prompt you for every operation.

```
> /setup
```

You can skip this and approve actions individually as they come up, or run `/setup` later. Your choices are saved to `.claude/settings.local.json` (gitignored, personal to your clone).

### 5. Add Your Inputs

Place your pre-built project plan files in `input/`:

```
input/
├── PRD.md                          # Product requirements document
├── work-sequence.md                # Phased execution plan with entry/exit criteria
├── epics/
│   └── epic-NNN.md                 # Epic definitions
├── stories/
│   └── story-NNN-NNN.md            # Story definitions
└── tasks/
    └── task-NNN-NNN-NN.md          # Task definitions
```

Each epic, story, and task file uses YAML frontmatter for structured fields (id, dependencies, priority, etc.) with the markdown body providing the full description and acceptance criteria.

### 6. Analyze (Intake Phase)

Launch with `./clyde` — it will show your project status and suggest running `/analyze`:

```
./clyde
> /analyze
```

The Intake Phase builds two artifacts from your inputs:

1. **`output/plan.db`** — A SQLite database with all epics, stories, tasks, phases, and dependencies. Built by a deterministic Python script, then enriched with phase data extracted from `work-sequence.md`.
2. **`output/technical-brief.md`** — A concise (50-100 line) tech reference distilled from the PRD. Goes through a multi-agent pipeline: draft extraction, iterative compression with review, and claim-by-claim fact-checking against the PRD.

Both artifacts are verified — the database via automated integrity checks (counts, referential integrity, status defaults), the brief via accuracy, completeness, and length review. You approve the results before moving to implementation.

See [LIFECYCLE.md](LIFECYCLE.md) for the full step-by-step breakdown.

### 7. Implement (Implementation Phase)

Once you approve the analysis, tell Claude to implement:

```
> implement phase-a
```

Claude works through one phase at a time using a **test-first, gate-checked** execution loop:

1. **Write tests** — A test-writer agent generates failing tests from the phase's acceptance criteria before any code is written
2. **Execute tasks** — For each task (in dependency order), the orchestrator spawns a focused implementer subagent with just the context it needs. The implementer returns a structured report (COMPLETE / BLOCKED / PARTIAL) with files changed and acceptance criteria checks.
3. **Story gates** — When all tasks in a story complete, tests run and a plan-validator reviews the implementation against the story's acceptance criteria. Failures are presented to you — not auto-fixed.
4. **Phase gate** — When the phase is done, the full test suite runs, skipped tasks are reviewed, and the plan-validator checks exit criteria. You approve before the next phase begins.

Tasks that can't be completed are **skipped with a reason** and surfaced at phase boundaries, where you decide whether to retry, defer, or accept. Blocked tasks are never retried more than once.

You can also target a specific task, story, or epic instead of a full phase. See [LIFECYCLE.md](LIFECYCLE.md) for the complete step-by-step reference.

## Directory Structure

```
my-project/
├── README.md
├── LIFECYCLE.md                    # Full lifecycle reference (intake + implementation details)
├── CLAUDE.md                       # Framework rules (read by Claude Code)
├── clyde                           # Launcher script (auto-detects state, runs /init or /status)
├── schema.sql                      # SQLite schema for plan.db
├── scripts/
│   └── build-plan-db.py            # Parses inputs → populates plan.db (zero deps)
├── .gitignore
├── .claude/
│   ├── settings.json               # Shared permission defaults (safe ops only)
│   ├── rules/                      # Auto-loaded instruction files
│   │   └── implementation-phase.md
│   ├── agents/                     # Subagent definitions
│   │   ├── tech-brief-drafter.md   #   Intake: drafts brief from PRD
│   │   ├── tech-brief-compressor.md#   Intake: compresses brief to target length
│   │   ├── tech-brief-reviewer.md  #   Intake: reviews brief for accuracy
│   │   ├── tech-brief-fact-checker.md # Intake: claim-by-claim verification
│   │   ├── plan-validator.md       #   Intake: validates plan.db integrity
│   │   ├── phase-extractor.md      #   Intake: extracts phases from work-sequence
│   │   ├── implementer.md          #   Implementation: writes code for a single task
│   │   └── test-writer.md         #   Implementation: writes tests from acceptance criteria
│   └── skills/                     # User-invocable skills
│       ├── init/                   # One-time project initialization
│       ├── analyze/                # Intake: build plan.db + technical brief
│       ├── update/                 # Pull framework updates from upstream
│       ├── status/                 # Check project state, suggest next action
│       ├── setup/                  # Configure local permissions
│       └── end-session/            # Wrap up session, update memory
├── input/                          # Your project plan (READ ONLY)
├── output/                         # Generated artifacts (gitignored)
│   ├── plan.db                     # SQLite: plan + progress tracking
│   └── technical-brief.md          # Concise tech reference
├── project-workspace/              # The project's own workspace
│   └── src/                       # Built software goes here
└── examples/
    └── input/                      # Format reference files
```

## The `clyde` Launcher

The `clyde` script at the repo root is the recommended way to start every session. It launches Claude Code and auto-detects project state:

- **Fresh clone** (not yet initialized) → runs `/init` to walk you through setup
- **Initialized project** → runs `/status` to show progress and suggest the next action

```bash
./clyde
```

Use `./clyde` instead of bare `claude` — it ensures you always start with the right context.

## Skills

Skills are slash commands you can run inside Claude Code:

| Skill | Description |
|-------|-------------|
| `/init` | One-time project setup — detach from Clyde remote, clean git history, prepare standalone project |
| `/analyze` | Run the Intake Phase — scan inputs, build `plan.db`, generate technical brief |
| `/status` | Check project state — shows progress, in-progress tasks, and suggests next action |
| `/setup` | Configure local permissions — git access, file editing, sqlite |
| `/update` | Pull latest framework files from upstream Clyde repo |
| `/end-session` | Wrap up the session — update memory, summarize progress, note open items |

## Updating the Framework

After initializing a project with `/init`, the upstream Clyde repo is kept as a git remote named `clyde`. To pull framework updates (new agents, improved skills, bug fixes) without affecting your project code:

```
> /update
```

This fetches the latest framework files, shows a diff, and applies changes with your confirmation. It never touches `project-workspace/`, `input/`, or `output/`.

If you initialized your project before `/update` existed, it will guide you through adding the `clyde` remote.

## How It Works

### Context Management

Clyde uses an **orchestrator + subagent** model to stay within context limits:

- The **orchestrator** (your main Claude Code session) keeps a lean context — it queries the database, gathers task context, and spawns subagents
- Each **implementer subagent** gets a clean, focused context: just the task, its parent story/epic, and the technical brief
- The **SQLite database** is the durable state layer — it survives context window limits and session boundaries, so you can pick up where you left off

### Input File Format

**Epics** (`epics/epic-NNN.md`):
```yaml
---
id: epic-001
title: Your Epic Title
requirements: [REQ-1, REQ-2]
priority: high
---
# Epic: Your Epic Title
## Description
...
```

**Stories** (`stories/story-NNN-NNN.md`):
```yaml
---
id: story-001-001
epic: epic-001
title: Your Story Title
priority: high
story_points: 5
dependencies: []
blocks: [story-001-002]
---
# Story: Your Story Title
## Acceptance Criteria
...
```

**Tasks** (`tasks/task-NNN-NNN-NN.md`):
```yaml
---
id: task-001-001-01
story: story-001-001
epic: epic-001
title: Your Task Title
complexity: 2
---
# Task: Your Task Title
## Description
...
## Acceptance Criteria
...
```

### Progress Tracking

All progress is tracked in `output/plan.db` via status columns:

- `pending` — not started
- `in_progress` — currently being worked on
- `complete` — finished

Task completion cascades: when all tasks in a story are done, the story is marked complete. When all stories in an epic are done, the epic is marked complete.

## Rules

- **Never modify `input/`** — these files are your source of truth, treated as read-only
- **`output/` is gitignored** — it contains generated artifacts specific to each project run
- **All code goes in `project-workspace/src/`** — the implementer subagent writes here; project READMEs, configs, and scripts also live under `project-workspace/`
- **The PRD is the authority** — when in doubt, the PRD wins

## License

MIT
