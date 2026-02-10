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

### 2. Set Up Permissions

Run the setup skill to configure local permissions (git access, file editing, etc.):

```
./clyde
> /setup
```

Or start Claude Code directly:

```
claude
> /setup
```

### 3. Add Your Inputs

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

### 4. Analyze (Phase 1)

Start Claude Code (or use the `clyde` launcher, which auto-checks project status on startup):

```
./clyde
> /analyze
```

Claude will:
1. Read everything in `input/`
2. Build `output/plan.db` — a SQLite database with all epics, stories, tasks, phases, and dependencies
3. Generate `output/technical-brief.md` — a concise tech reference distilled from the PRD
4. Present a summary for your review

Review the plan and technical brief before proceeding.

### 5. Implement (Phase 2)

Once you approve the analysis, tell Claude to implement:

```
> implement
```

Claude acts as an orchestrator:
1. Queries `plan.db` for the next pending task (respecting dependencies and phase order)
2. Spawns a focused implementer subagent with just the context it needs (task + story + epic + technical brief)
3. The subagent writes code in `src/`
4. The orchestrator updates task status in `plan.db`
5. Repeats until the scope is complete

By default, Claude works through one phase at a time (as defined in `work-sequence.md`), checking entry/exit criteria. You can also ask it to work on a specific task, story, or epic.

## Directory Structure

```
my-project/
├── README.md
├── CLAUDE.md                       # Framework rules (read by Claude Code)
├── clyde                           # Launcher script (runs /status on startup)
├── schema.sql                      # SQLite schema for plan.db
├── scripts/
│   └── build-plan-db.py            # Parses inputs → populates plan.db (zero deps)
├── .gitignore
├── .claude/
│   ├── settings.json               # Shared permission defaults (safe ops only)
│   ├── rules/                      # Auto-loaded instruction files
│   │   └── phase2-implement.md
│   ├── agents/                     # Subagent definitions
│   │   ├── analyzer.md
│   │   ├── implementer.md
│   │   └── reviewer.md
│   └── skills/                     # User-invocable skills
│       ├── analyze/                # Phase 1: build plan.db + technical brief
│       ├── status/                 # Check project state, suggest next action
│       ├── setup/                  # Configure local permissions
│       └── end-session/            # Wrap up session, update memory
├── input/                          # Your project plan (READ ONLY)
├── output/                         # Generated artifacts (gitignored)
│   ├── plan.db                     # SQLite: plan + progress tracking
│   └── technical-brief.md          # Concise tech reference
├── src/                            # Built software goes here
└── examples/
    └── input/                      # Format reference files
```

## The `clyde` Launcher

The `clyde` script at the repo root is a convenience wrapper that starts Claude Code and immediately runs `/status` to show you where the project stands:

```bash
./clyde
```

This gives you an instant summary of progress and a suggested next action, so you can pick up right where you left off.

## Skills

Skills are slash commands you can run inside Claude Code:

| Skill | Description |
|-------|-------------|
| `/analyze` | Run Phase 1 — scan inputs, build `plan.db`, generate technical brief |
| `/status` | Check project state — shows progress, in-progress tasks, and suggests next action |
| `/setup` | Configure local permissions — git access, file editing, sqlite |
| `/end-session` | Wrap up the session — update memory, summarize progress, note open items |

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
- **All code goes in `src/`** — the implementer subagent writes here
- **The PRD is the authority** — when in doubt, the PRD wins

## License

MIT
