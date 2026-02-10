-- Clyde plan.db schema
-- Canonical DDL for the plan database built during the Intake Phase (analyze)

PRAGMA foreign_keys = ON;

-- Epics: top-level work items parsed from input/epics/epic-NNN.md
CREATE TABLE IF NOT EXISTS epics (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    priority TEXT CHECK (priority IN ('high', 'medium', 'low')),
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'complete', 'skipped'))
);

-- Stories: child items of epics, parsed from input/stories/story-NNN-NNN.md
CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    epic_id TEXT NOT NULL REFERENCES epics(id),
    title TEXT NOT NULL,
    priority TEXT CHECK (priority IN ('high', 'medium', 'low')),
    story_points TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'complete', 'skipped'))
);

-- Tasks: child items of stories, parsed from input/tasks/task-NNN-NNN-NN.md
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id),
    epic_id TEXT NOT NULL REFERENCES epics(id),
    title TEXT NOT NULL,
    complexity INTEGER,
    description TEXT,
    acceptance_criteria TEXT,
    skip_reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'complete', 'skipped'))
);

-- Phases: execution phases parsed from input/work-sequence.md
CREATE TABLE IF NOT EXISTS phases (
    id TEXT PRIMARY KEY,
    sequence INTEGER NOT NULL,
    name TEXT NOT NULL,
    goal TEXT,
    entry_criteria TEXT,
    exit_criteria TEXT,
    estimated_duration TEXT
);

-- Phase items: maps which stories/epics belong to each phase
CREATE TABLE IF NOT EXISTS phase_items (
    phase_id TEXT NOT NULL REFERENCES phases(id),
    item_id TEXT NOT NULL,
    item_type TEXT NOT NULL CHECK (item_type IN ('epic', 'story')),
    PRIMARY KEY (phase_id, item_id, item_type)
);

-- Dependencies: tracks blocking relationships between items
CREATE TABLE IF NOT EXISTS dependencies (
    item_id TEXT NOT NULL,
    item_type TEXT NOT NULL CHECK (item_type IN ('epic', 'story', 'task')),
    depends_on_id TEXT NOT NULL,
    depends_on_type TEXT NOT NULL CHECK (depends_on_type IN ('epic', 'story', 'task')),
    PRIMARY KEY (item_id, item_type, depends_on_id, depends_on_type)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_stories_epic_id ON stories(epic_id);
CREATE INDEX IF NOT EXISTS idx_tasks_story_id ON tasks(story_id);
CREATE INDEX IF NOT EXISTS idx_tasks_epic_id ON tasks(epic_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_phase_items_phase ON phase_items(phase_id);
CREATE INDEX IF NOT EXISTS idx_dependencies_item ON dependencies(item_id, item_type);
CREATE INDEX IF NOT EXISTS idx_dependencies_depends ON dependencies(depends_on_id, depends_on_type);
