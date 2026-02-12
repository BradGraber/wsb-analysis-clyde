#!/usr/bin/env python3
"""
plan-ops.py — Query and update plan.db for the Clyde framework.

Zero external dependencies (Python 3 stdlib only).
Provides subcommands for the orchestrator to find work, gather context,
update progress, and verify intake artifacts without writing raw SQL.

Usage:
  python3 scripts/plan-ops.py next-task [--phase PHASE_ID]
  python3 scripts/plan-ops.py available-tasks [--phase PHASE_ID] [--limit N]
  python3 scripts/plan-ops.py task-context TASK_ID
  python3 scripts/plan-ops.py start-task TASK_ID
  python3 scripts/plan-ops.py complete-task TASK_ID [--files F1 F2 ...] [--json]
  python3 scripts/plan-ops.py skip-task TASK_ID --reason "description"
  python3 scripts/plan-ops.py retry-task TASK_ID
  python3 scripts/plan-ops.py list-skipped [--phase PHASE_ID]
  python3 scripts/plan-ops.py story-files STORY_ID
  python3 scripts/plan-ops.py phase-files PHASE_ID
  python3 scripts/plan-ops.py phase-stories PHASE_ID
  python3 scripts/plan-ops.py phase-tasks PHASE_ID
  python3 scripts/plan-ops.py progress
  python3 scripts/plan-ops.py phase-status PHASE_ID
  python3 scripts/plan-ops.py verify-intake --expected-epics N --expected-stories N --expected-tasks N
  python3 scripts/plan-ops.py resume-phase PHASE_ID
  python3 scripts/plan-ops.py update-phase PHASE_ID [--status STATUS] [--goal G] [--entry-criteria EC] [--exit-criteria XC]
  python3 scripts/plan-ops.py update-story-gate STORY_ID --status STATUS
  python3 scripts/plan-ops.py active-phase
  python3 scripts/plan-ops.py list-docs
  python3 scripts/plan-ops.py batch-check [--reset] [--budget N]
  python3 scripts/plan-ops.py schema
  python3 scripts/plan-ops.py show ITEM_ID
  python3 scripts/plan-ops.py update-task TASK_ID [--title T] [--description D] [--acceptance-criteria AC]
  python3 scripts/plan-ops.py update-story STORY_ID [--title T] [--description D]
  python3 scripts/plan-ops.py update-epic EPIC_ID [--title T] [--description D]
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------

_project_root = None  # Set once in CLI handler


def emit_event(event_type, data):
    """Append a structured event to output/logs/events.jsonl (fire-and-forget)."""
    try:
        if _project_root is None:
            return
        root = Path(_project_root)
        if not (root / 'output' / 'logs' / '.enabled').exists():
            return
        entry = {
            'ts': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'event': event_type,
            **data,
        }
        log_path = root / 'output' / 'logs' / 'events.jsonl'
        with open(log_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def get_db(project_root):
    """Open plan.db with row_factory for dict-like access."""
    db_path = Path(project_root) / 'output' / 'plan.db'
    if not db_path.exists():
        print(f'ERROR: {db_path} not found. Run the Intake Phase (/analyze) first.', file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    conn.execute('PRAGMA foreign_keys = ON')
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

def ensure_schema(conn):
    """Auto-migrate plan.db from older schema versions if needed.

    Migrations are detected by checking for missing columns/features:
      Migration 1: Add skip_reason + skipped status (table recreation)
      Migration 2: Add files_changed column to tasks
      Migration 3: Add status column to phases (table recreation)
      Migration 4: Add gate_status column to stories
    """
    columns = conn.execute('PRAGMA table_info(tasks)').fetchall()
    col_names = [col['name'] for col in columns]

    # Migration 1: add skipped status support (requires table recreation)
    if 'skip_reason' not in col_names:
        print('Migrating plan.db schema (adding skipped status support)...',
              file=sys.stderr)

        conn.execute('PRAGMA foreign_keys = OFF')

        try:
            # -- Migrate epics --
            conn.execute('ALTER TABLE epics RENAME TO _old_epics')
            conn.execute(
                'CREATE TABLE epics ('
                '  id TEXT PRIMARY KEY,'
                '  title TEXT NOT NULL,'
                '  priority TEXT CHECK (priority IN (\'high\', \'medium\', \'low\')),'
                '  description TEXT,'
                '  status TEXT NOT NULL DEFAULT \'pending\''
                '    CHECK (status IN (\'pending\', \'in_progress\', \'complete\', \'skipped\'))'
                ')'
            )
            conn.execute(
                'INSERT INTO epics (id, title, priority, description, status) '
                'SELECT id, title, priority, description, status FROM _old_epics'
            )
            conn.execute('DROP TABLE _old_epics')

            # -- Migrate stories --
            conn.execute('ALTER TABLE stories RENAME TO _old_stories')
            conn.execute(
                'CREATE TABLE stories ('
                '  id TEXT PRIMARY KEY,'
                '  epic_id TEXT NOT NULL REFERENCES epics(id),'
                '  title TEXT NOT NULL,'
                '  priority TEXT CHECK (priority IN (\'high\', \'medium\', \'low\')),'
                '  story_points TEXT,'
                '  description TEXT,'
                '  status TEXT NOT NULL DEFAULT \'pending\''
                '    CHECK (status IN (\'pending\', \'in_progress\', \'complete\', \'skipped\'))'
                ')'
            )
            conn.execute(
                'INSERT INTO stories (id, epic_id, title, priority, story_points, description, status) '
                'SELECT id, epic_id, title, priority, story_points, description, status FROM _old_stories'
            )
            conn.execute('DROP TABLE _old_stories')

            # -- Migrate tasks --
            conn.execute('ALTER TABLE tasks RENAME TO _old_tasks')
            conn.execute(
                'CREATE TABLE tasks ('
                '  id TEXT PRIMARY KEY,'
                '  story_id TEXT NOT NULL REFERENCES stories(id),'
                '  epic_id TEXT NOT NULL REFERENCES epics(id),'
                '  title TEXT NOT NULL,'
                '  complexity INTEGER,'
                '  description TEXT,'
                '  acceptance_criteria TEXT,'
                '  skip_reason TEXT,'
                '  files_changed TEXT,'
                '  status TEXT NOT NULL DEFAULT \'pending\''
                '    CHECK (status IN (\'pending\', \'in_progress\', \'complete\', \'skipped\'))'
                ')'
            )
            conn.execute(
                'INSERT INTO tasks (id, story_id, epic_id, title, complexity, '
                '  description, acceptance_criteria, skip_reason, files_changed, status) '
                'SELECT id, story_id, epic_id, title, complexity, '
                '  description, acceptance_criteria, NULL, NULL, status '
                'FROM _old_tasks'
            )
            conn.execute('DROP TABLE _old_tasks')

            # -- Recreate indexes on migrated tables --
            conn.execute('CREATE INDEX IF NOT EXISTS idx_stories_epic_id ON stories(epic_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_story_id ON tasks(story_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_epic_id ON tasks(epic_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')

            conn.commit()
            print('Migration complete.', file=sys.stderr)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute('PRAGMA foreign_keys = ON')

        # Re-read columns after migration 1
        col_names = [col['name'] for col in conn.execute('PRAGMA table_info(tasks)').fetchall()]

    # Migration 2: add files_changed column (simple ALTER TABLE)
    if 'files_changed' not in col_names:
        print('Migrating plan.db schema (adding files_changed column)...',
              file=sys.stderr)
        conn.execute('ALTER TABLE tasks ADD COLUMN files_changed TEXT')
        conn.commit()
        print('Migration complete.', file=sys.stderr)

    # Migration 3: add status column to phases (requires table recreation for CHECK constraint)
    phase_columns = conn.execute('PRAGMA table_info(phases)').fetchall()
    phase_col_names = [col['name'] for col in phase_columns]
    if 'status' not in phase_col_names:
        print('Migrating plan.db schema (adding phase status column)...',
              file=sys.stderr)

        conn.execute('PRAGMA foreign_keys = OFF')
        try:
            conn.execute('ALTER TABLE phases RENAME TO _old_phases')
            conn.execute(
                'CREATE TABLE phases ('
                '  id TEXT PRIMARY KEY,'
                '  sequence INTEGER NOT NULL,'
                '  name TEXT NOT NULL,'
                '  goal TEXT,'
                '  entry_criteria TEXT,'
                '  exit_criteria TEXT,'
                '  estimated_duration TEXT,'
                '  status TEXT NOT NULL DEFAULT \'pending\''
                '    CHECK (status IN (\'pending\', \'tests_written\', \'in_progress\','
                '                      \'gate_pending\', \'complete\'))'
                ')'
            )
            conn.execute(
                'INSERT INTO phases (id, sequence, name, goal, entry_criteria, '
                '  exit_criteria, estimated_duration, status) '
                'SELECT id, sequence, name, goal, entry_criteria, '
                '  exit_criteria, estimated_duration, \'pending\' '
                'FROM _old_phases'
            )
            conn.execute('DROP TABLE _old_phases')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_phase_items_phase ON phase_items(phase_id)')
            conn.commit()
            print('Migration complete.', file=sys.stderr)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute('PRAGMA foreign_keys = ON')

    # Migration 4: add gate_status column to stories (simple ALTER TABLE)
    story_columns = conn.execute('PRAGMA table_info(stories)').fetchall()
    story_col_names = [col['name'] for col in story_columns]
    if 'gate_status' not in story_col_names:
        print('Migrating plan.db schema (adding story gate_status column)...',
              file=sys.stderr)
        conn.execute('ALTER TABLE stories ADD COLUMN gate_status TEXT')
        conn.commit()
        print('Migration complete.', file=sys.stderr)


# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------

def is_blocked(conn, item_id, item_type):
    """Check if an item has unmet dependencies.

    Returns a list of blocking items (empty = not blocked).
    Checks direct dependencies only — callers handle hierarchy.
    """
    deps = conn.execute(
        'SELECT depends_on_id, depends_on_type FROM dependencies '
        'WHERE item_id = ? AND item_type = ?',
        (item_id, item_type)
    ).fetchall()

    blockers = []
    for dep in deps:
        table = {'epic': 'epics', 'story': 'stories', 'task': 'tasks'}[dep['depends_on_type']]
        row = conn.execute(
            f'SELECT id, status FROM {table} WHERE id = ?',
            (dep['depends_on_id'],)
        ).fetchone()
        if not row or row['status'] != 'complete':
            blockers.append({
                'id': dep['depends_on_id'],
                'type': dep['depends_on_type'],
                'status': row['status'] if row else 'missing',
            })
    return blockers


def is_task_blocked(conn, task):
    """Check if a task is blocked at any level (task, story, or epic)."""
    # Direct task dependencies
    blockers = is_blocked(conn, task['id'], 'task')
    if blockers:
        return blockers

    # Parent story dependencies
    blockers = is_blocked(conn, task['story_id'], 'story')
    if blockers:
        return blockers

    # Parent epic dependencies
    blockers = is_blocked(conn, task['epic_id'], 'epic')
    if blockers:
        return blockers

    return []


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_next_task(conn, phase_id=None):
    """Find the next unblocked pending task."""
    if phase_id:
        # Tasks in this phase via phase_items (story or epic mappings)
        tasks = conn.execute(
            'SELECT DISTINCT t.id, t.title, t.story_id, t.epic_id '
            'FROM tasks t '
            'JOIN phase_items pi ON '
            '  (pi.item_type = \'story\' AND pi.item_id = t.story_id) '
            '  OR (pi.item_type = \'epic\' AND pi.item_id = t.epic_id) '
            'WHERE pi.phase_id = ? AND t.status = \'pending\' '
            'ORDER BY t.id',
            (phase_id,)
        ).fetchall()
    else:
        tasks = conn.execute(
            'SELECT id, title, story_id, epic_id '
            'FROM tasks WHERE status = \'pending\' '
            'ORDER BY id'
        ).fetchall()

    for task in tasks:
        blockers = is_task_blocked(conn, task)
        if not blockers:
            result = {
                'id': task['id'],
                'title': task['title'],
                'story_id': task['story_id'],
                'epic_id': task['epic_id'],
            }
            print(json.dumps(result, indent=2))
            return

    # Nothing found
    if phase_id:
        msg = f'No unblocked pending tasks in phase {phase_id}'
    else:
        msg = 'No unblocked pending tasks found'
    print(json.dumps({'message': msg}))


def cmd_available_tasks(conn, phase_id=None, limit=None):
    """Find all unblocked pending tasks, max one per story.

    Returns tasks from independent stories that can safely run in parallel.
    Tasks are ordered by ID; the first unblocked task per story wins.
    """
    if phase_id:
        tasks = conn.execute(
            'SELECT DISTINCT t.id, t.title, t.story_id, t.epic_id '
            'FROM tasks t '
            'JOIN phase_items pi ON '
            '  (pi.item_type = \'story\' AND pi.item_id = t.story_id) '
            '  OR (pi.item_type = \'epic\' AND pi.item_id = t.epic_id) '
            'WHERE pi.phase_id = ? AND t.status = \'pending\' '
            'ORDER BY t.id',
            (phase_id,)
        ).fetchall()
    else:
        tasks = conn.execute(
            'SELECT id, title, story_id, epic_id '
            'FROM tasks WHERE status = \'pending\' '
            'ORDER BY id'
        ).fetchall()

    available = []
    seen_stories = set()
    for task in tasks:
        if task['story_id'] in seen_stories:
            continue
        blockers = is_task_blocked(conn, task)
        if not blockers:
            available.append({
                'id': task['id'],
                'title': task['title'],
                'story_id': task['story_id'],
                'epic_id': task['epic_id'],
            })
            seen_stories.add(task['story_id'])
            if limit and len(available) >= limit:
                break

    if not available:
        if phase_id:
            msg = f'No unblocked pending tasks in phase {phase_id}'
        else:
            msg = 'No unblocked pending tasks found'
        print(json.dumps({'tasks': [], 'message': msg}))
    else:
        print(json.dumps({'tasks': available}, indent=2))


def cmd_task_context(conn, task_id):
    """Return full context for a task (task + story + epic + dependencies)."""
    task = conn.execute(
        'SELECT id, title, story_id, epic_id, complexity, '
        'description, acceptance_criteria, status '
        'FROM tasks WHERE id = ?',
        (task_id,)
    ).fetchone()

    if not task:
        print(f'ERROR: task {task_id} not found', file=sys.stderr)
        sys.exit(1)

    story = conn.execute(
        'SELECT id, title, epic_id, priority, story_points, description, status '
        'FROM stories WHERE id = ?',
        (task['story_id'],)
    ).fetchone()

    epic = conn.execute(
        'SELECT id, title, priority, description, status '
        'FROM epics WHERE id = ?',
        (task['epic_id'],)
    ).fetchone()

    deps = conn.execute(
        'SELECT depends_on_id, depends_on_type FROM dependencies '
        'WHERE item_id = ? AND item_type = \'task\'',
        (task_id,)
    ).fetchall()

    result = {
        'task': dict(task),
        'story': dict(story) if story else None,
        'epic': dict(epic) if epic else None,
        'dependencies': [dict(d) for d in deps],
    }
    print(json.dumps(result, indent=2))


def cmd_start_task(conn, task_id):
    """Mark a task as in_progress, cascade to story and epic."""
    task = conn.execute(
        'SELECT id, title, story_id, epic_id, status FROM tasks WHERE id = ?',
        (task_id,)
    ).fetchone()

    if not task:
        print(f'ERROR: task {task_id} not found', file=sys.stderr)
        sys.exit(1)

    if task['status'] != 'pending':
        print(f'WARNING: task {task_id} is already {task["status"]}', file=sys.stderr)

    conn.execute(
        'UPDATE tasks SET status = \'in_progress\' WHERE id = ?',
        (task_id,)
    )

    # Cascade: set story and epic to in_progress if still pending
    conn.execute(
        'UPDATE stories SET status = \'in_progress\' '
        'WHERE id = ? AND status = \'pending\'',
        (task['story_id'],)
    )
    conn.execute(
        'UPDATE epics SET status = \'in_progress\' '
        'WHERE id = ? AND status = \'pending\'',
        (task['epic_id'],)
    )

    # Cascade: set phase to in_progress if still pending or tests_written
    phase_row = conn.execute(
        'SELECT DISTINCT pi.phase_id FROM phase_items pi '
        'WHERE (pi.item_type = \'story\' AND pi.item_id = ?) '
        '  OR (pi.item_type = \'epic\' AND pi.item_id = ?)',
        (task['story_id'], task['epic_id'])
    ).fetchone()
    if phase_row:
        conn.execute(
            'UPDATE phases SET status = \'in_progress\' '
            'WHERE id = ? AND status IN (\'pending\', \'tests_written\')',
            (phase_row['phase_id'],)
        )

    conn.commit()

    emit_event('task_started', {
        'task_id': task_id,
        'story_id': task['story_id'],
        'epic_id': task['epic_id'],
        'phase_id': phase_row['phase_id'] if phase_row else None,
    })

    print(f'Started: {task_id} — {task["title"]}')
    story_status = conn.execute(
        'SELECT status FROM stories WHERE id = ?', (task['story_id'],)
    ).fetchone()
    epic_status = conn.execute(
        'SELECT status FROM epics WHERE id = ?', (task['epic_id'],)
    ).fetchone()
    print(f'  Story {task["story_id"]}: {story_status["status"]}')
    print(f'  Epic {task["epic_id"]}: {epic_status["status"]}')


def cmd_complete_task(conn, task_id, files=None, output_json=False):
    """Mark a task as complete, cascade to story and epic if all children done."""
    task = conn.execute(
        'SELECT id, title, story_id, epic_id, status FROM tasks WHERE id = ?',
        (task_id,)
    ).fetchone()

    if not task:
        print(f'ERROR: task {task_id} not found', file=sys.stderr)
        sys.exit(1)

    if files:
        conn.execute(
            'UPDATE tasks SET status = \'complete\', files_changed = ? WHERE id = ?',
            (json.dumps(files), task_id)
        )
    else:
        conn.execute(
            'UPDATE tasks SET status = \'complete\' WHERE id = ?',
            (task_id,)
        )
    # Check if all tasks in the story are complete
    remaining = conn.execute(
        'SELECT COUNT(*) AS count FROM tasks '
        'WHERE story_id = ? AND status != \'complete\'',
        (task['story_id'],)
    ).fetchone()['count']
    skipped_tasks = conn.execute(
        'SELECT COUNT(*) AS count FROM tasks '
        'WHERE story_id = ? AND status = \'skipped\'',
        (task['story_id'],)
    ).fetchone()['count']

    story_completed = (remaining == 0)
    epic_completed = False

    if story_completed:
        conn.execute(
            'UPDATE stories SET status = \'complete\', gate_status = \'pending\' '
            'WHERE id = ?',
            (task['story_id'],)
        )

        remaining_stories = conn.execute(
            'SELECT COUNT(*) AS count FROM stories '
            'WHERE epic_id = ? AND status != \'complete\'',
            (task['epic_id'],)
        ).fetchone()['count']

        if remaining_stories == 0:
            conn.execute(
                'UPDATE epics SET status = \'complete\' WHERE id = ?',
                (task['epic_id'],)
            )
            epic_completed = True

    conn.commit()

    emit_event('task_completed', {
        'task_id': task_id,
        'files': files or [],
        'story_completed': story_completed,
        'epic_completed': epic_completed,
    })

    if output_json:
        result = {
            'task_id': task_id,
            'task_title': task['title'],
            'story_id': task['story_id'],
            'story_completed': story_completed,
            'story_gate_status': 'pending' if story_completed else None,
            'epic_id': task['epic_id'],
            'epic_completed': epic_completed,
            'remaining_tasks': remaining,
            'skipped_tasks': skipped_tasks,
        }
        if files:
            result['files_recorded'] = files
        print(json.dumps(result, indent=2))
    else:
        print(f'Completed: {task_id} — {task["title"]}')
        if story_completed:
            print(f'  Story {task["story_id"]}: complete (all tasks done)')
            if epic_completed:
                print(f'  Epic {task["epic_id"]}: complete (all stories done)')
            else:
                skipped_stories = conn.execute(
                    'SELECT COUNT(*) AS count FROM stories '
                    'WHERE epic_id = ? AND status = \'skipped\'',
                    (task['epic_id'],)
                ).fetchone()['count']
                remaining_stories = conn.execute(
                    'SELECT COUNT(*) AS count FROM stories '
                    'WHERE epic_id = ? AND status != \'complete\'',
                    (task['epic_id'],)
                ).fetchone()['count']
                suffix = f' ({skipped_stories} skipped)' if skipped_stories else ''
                print(f'  Epic {task["epic_id"]}: {remaining_stories} stories remaining{suffix}')
        else:
            suffix = f' ({skipped_tasks} skipped)' if skipped_tasks else ''
            print(f'  Story {task["story_id"]}: {remaining} tasks remaining{suffix}')


def cmd_progress(conn):
    """Show overall project progress — task/story/epic counts and in-progress items."""
    # Task counts by status
    task_stats = conn.execute(
        'SELECT status, COUNT(*) AS count FROM tasks GROUP BY status'
    ).fetchall()
    task_total = sum(s['count'] for s in task_stats)
    task_by = {s['status']: s['count'] for s in task_stats}

    # Story counts by status
    story_stats = conn.execute(
        'SELECT status, COUNT(*) AS count FROM stories GROUP BY status'
    ).fetchall()
    story_total = sum(s['count'] for s in story_stats)
    story_by = {s['status']: s['count'] for s in story_stats}

    # Epic counts by status
    epic_stats = conn.execute(
        'SELECT status, COUNT(*) AS count FROM epics GROUP BY status'
    ).fetchall()
    epic_total = sum(s['count'] for s in epic_stats)
    epic_by = {s['status']: s['count'] for s in epic_stats}

    print('Overall Progress:')
    task_skipped = task_by.get('skipped', 0)
    story_skipped = story_by.get('skipped', 0)
    epic_skipped = epic_by.get('skipped', 0)

    print(f'  Tasks:   {task_by.get("complete", 0)}/{task_total} complete, '
          f'{task_by.get("in_progress", 0)} in progress, '
          f'{task_by.get("pending", 0)} pending'
          + (f', {task_skipped} skipped' if task_skipped else ''))
    print(f'  Stories: {story_by.get("complete", 0)}/{story_total} complete, '
          f'{story_by.get("in_progress", 0)} in progress, '
          f'{story_by.get("pending", 0)} pending'
          + (f', {story_skipped} skipped' if story_skipped else ''))
    print(f'  Epics:   {epic_by.get("complete", 0)}/{epic_total} complete, '
          f'{epic_by.get("in_progress", 0)} in progress, '
          f'{epic_by.get("pending", 0)} pending'
          + (f', {epic_skipped} skipped' if epic_skipped else ''))

    # List in-progress tasks
    in_progress = conn.execute(
        'SELECT id, title, story_id, epic_id FROM tasks WHERE status = \'in_progress\' ORDER BY id'
    ).fetchall()
    if in_progress:
        print()
        print('In-Progress Tasks:')
        for t in in_progress:
            print(f'  {t["id"]}: {t["title"]} (story: {t["story_id"]}, epic: {t["epic_id"]})')

    # Phase summary (if phases exist)
    phases = conn.execute('SELECT id, name, status FROM phases ORDER BY sequence').fetchall()
    if phases:
        print()
        print('Phases:')
        for p in phases:
            stats = conn.execute(
                'SELECT t.status, COUNT(DISTINCT t.id) AS count '
                'FROM tasks t '
                'JOIN phase_items pi ON '
                '  (pi.item_type = \'story\' AND pi.item_id = t.story_id) '
                '  OR (pi.item_type = \'epic\' AND pi.item_id = t.epic_id) '
                'WHERE pi.phase_id = ? '
                'GROUP BY t.status',
                (p['id'],)
            ).fetchall()
            total = sum(s['count'] for s in stats)
            complete = next((s['count'] for s in stats if s['status'] == 'complete'), 0)
            pct = round(complete / total * 100) if total else 0
            print(f'  {p["id"]}: {p["name"]} [{p["status"]}] — {complete}/{total} tasks ({pct}%)')


def cmd_batch_check(project_root, reset=False, budget=8):
    """Manage the session batch counter (file-based, no DB needed)."""
    counter_file = Path(project_root) / 'output' / '.session-batch-count'
    counter_file.parent.mkdir(parents=True, exist_ok=True)

    if reset:
        counter_file.write_text('0')
        emit_event('batch_check', {'batch': 0, 'budget': budget, 'stop': False, 'reset': True})
        print(json.dumps({'batch': 0, 'budget': budget, 'stop': False}))
        return

    # Read current count
    try:
        current = int(counter_file.read_text().strip())
    except (FileNotFoundError, ValueError):
        current = 0

    # Increment and write back
    new_count = current + 1
    counter_file.write_text(str(new_count))

    stop = new_count >= budget
    emit_event('batch_check', {'batch': new_count, 'budget': budget, 'stop': stop, 'reset': False})

    print(json.dumps({
        'batch': new_count,
        'budget': budget,
        'stop': stop
    }))


def cmd_active_phase(conn):
    """Find the currently active phase (in_progress, tests_written, or gate_pending)."""
    phase = conn.execute(
        "SELECT id, name, status FROM phases "
        "WHERE status IN ('in_progress', 'tests_written', 'gate_pending') "
        "ORDER BY sequence LIMIT 1"
    ).fetchone()
    if phase:
        print(json.dumps({
            'phase_id': phase['id'],
            'status': phase['status'],
            'name': phase['name']
        }))
    else:
        print(json.dumps({'phase_id': None}))


def cmd_phase_status(conn, phase_id):
    """Show progress for a phase."""
    phase = conn.execute(
        'SELECT * FROM phases WHERE id = ?', (phase_id,)
    ).fetchone()

    if not phase:
        print(f'ERROR: phase {phase_id} not found', file=sys.stderr)
        sys.exit(1)

    print(f'Phase: {phase["name"]} ({phase["id"]})')
    print(f'Status: {phase["status"]}')
    print(f'Goal: {phase["goal"]}')
    print(f'Duration: {phase["estimated_duration"]}')
    print()

    # Task counts by status (via phase_items → stories/epics → tasks)
    stats = conn.execute(
        'SELECT t.status, COUNT(DISTINCT t.id) AS count '
        'FROM tasks t '
        'JOIN phase_items pi ON '
        '  (pi.item_type = \'story\' AND pi.item_id = t.story_id) '
        '  OR (pi.item_type = \'epic\' AND pi.item_id = t.epic_id) '
        'WHERE pi.phase_id = ? '
        'GROUP BY t.status',
        (phase_id,)
    ).fetchall()

    total = sum(s['count'] for s in stats)
    by_status = {s['status']: s['count'] for s in stats}
    complete = by_status.get('complete', 0)
    in_progress = by_status.get('in_progress', 0)
    pending = by_status.get('pending', 0)

    skipped = by_status.get('skipped', 0)

    print(f'Tasks: {complete}/{total} complete, {in_progress} in progress, {pending} pending, {skipped} skipped')
    print()

    print('Entry Criteria:')
    for line in (phase['entry_criteria'] or 'None').split('\n'):
        print(f'  {line}')
    print()
    print('Exit Criteria:')
    for line in (phase['exit_criteria'] or 'None').split('\n'):
        print(f'  {line}')


def cmd_skip_task(conn, task_id, reason):
    """Mark a task as skipped with a reason. Does NOT cascade to parent story/epic."""
    task = conn.execute(
        'SELECT id, title, story_id, epic_id, status FROM tasks WHERE id = ?',
        (task_id,)
    ).fetchone()

    if not task:
        print(f'ERROR: task {task_id} not found', file=sys.stderr)
        sys.exit(1)

    if task['status'] not in ('pending', 'in_progress'):
        print(f'WARNING: task {task_id} is {task["status"]}, expected pending or in_progress',
              file=sys.stderr)

    conn.execute(
        'UPDATE tasks SET status = \'skipped\', skip_reason = ? WHERE id = ?',
        (reason, task_id)
    )
    conn.commit()

    emit_event('task_skipped', {'task_id': task_id, 'reason': reason})

    print(f'Skipped: {task_id} — {task["title"]}')
    print(f'  Reason: {reason}')


def cmd_retry_task(conn, task_id):
    """Reset a skipped task to pending for retry."""
    task = conn.execute(
        'SELECT id, title, status FROM tasks WHERE id = ?',
        (task_id,)
    ).fetchone()

    if not task:
        print(f'ERROR: task {task_id} not found', file=sys.stderr)
        sys.exit(1)

    if task['status'] != 'skipped':
        print(f'ERROR: task {task_id} is {task["status"]}, not skipped', file=sys.stderr)
        sys.exit(1)

    conn.execute(
        'UPDATE tasks SET status = \'pending\', skip_reason = NULL WHERE id = ?',
        (task_id,)
    )
    conn.commit()

    emit_event('task_retried', {'task_id': task_id})

    print(f'Reset to pending: {task_id} — {task["title"]}')


def cmd_list_skipped(conn, phase_id=None):
    """List all skipped tasks with their reasons."""
    if phase_id:
        tasks = conn.execute(
            'SELECT DISTINCT t.id, t.title, t.skip_reason, t.story_id, t.epic_id '
            'FROM tasks t '
            'JOIN phase_items pi ON '
            '  (pi.item_type = \'story\' AND pi.item_id = t.story_id) '
            '  OR (pi.item_type = \'epic\' AND pi.item_id = t.epic_id) '
            'WHERE pi.phase_id = ? AND t.status = \'skipped\' '
            'ORDER BY t.id',
            (phase_id,)
        ).fetchall()
    else:
        tasks = conn.execute(
            'SELECT id, title, skip_reason, story_id, epic_id '
            'FROM tasks WHERE status = \'skipped\' '
            'ORDER BY id'
        ).fetchall()

    if not tasks:
        scope = f' in phase {phase_id}' if phase_id else ''
        print(f'No skipped tasks{scope}')
        return

    print(f'Skipped Tasks ({len(tasks)}):')
    for t in tasks:
        print(f'  {t["id"]}: {t["title"]}')
        print(f'    Reason: {t["skip_reason"] or "no reason given"}')
        print(f'    Story: {t["story_id"]}, Epic: {t["epic_id"]}')


def _aggregate_files(rows):
    """Collect files_changed JSON arrays from task rows into a deduplicated list."""
    seen = set()
    result = []
    for row in rows:
        raw = row['files_changed']
        if not raw:
            continue
        try:
            files = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            print(f'WARNING: malformed files_changed JSON, skipping', file=sys.stderr)
            continue
        for f in files:
            if f not in seen:
                seen.add(f)
                result.append(f)
    return result


def cmd_story_files(conn, story_id):
    """Return aggregated files_changed for all complete tasks in a story."""
    tasks = conn.execute(
        'SELECT files_changed FROM tasks '
        'WHERE story_id = ? AND status = \'complete\' AND files_changed IS NOT NULL',
        (story_id,)
    ).fetchall()
    print(json.dumps(_aggregate_files(tasks), indent=2))


def cmd_phase_files(conn, phase_id):
    """Return aggregated files_changed for all complete tasks in a phase."""
    tasks = conn.execute(
        'SELECT DISTINCT t.files_changed FROM tasks t '
        'JOIN phase_items pi ON '
        '  (pi.item_type = \'story\' AND pi.item_id = t.story_id) '
        '  OR (pi.item_type = \'epic\' AND pi.item_id = t.epic_id) '
        'WHERE pi.phase_id = ? AND t.status = \'complete\' '
        'AND t.files_changed IS NOT NULL',
        (phase_id,)
    ).fetchall()
    print(json.dumps(_aggregate_files(tasks), indent=2))


def cmd_phase_stories(conn, phase_id):
    """Return all stories in a phase with their details (including acceptance criteria)."""
    stories = conn.execute(
        'SELECT DISTINCT s.id, s.title, s.description '
        'FROM stories s '
        'JOIN phase_items pi ON '
        '  (pi.item_type = \'story\' AND pi.item_id = s.id) '
        '  OR (pi.item_type = \'epic\' AND pi.item_id = s.epic_id) '
        'WHERE pi.phase_id = ? '
        'ORDER BY s.id',
        (phase_id,)
    ).fetchall()
    result = [{'id': s['id'], 'title': s['title'], 'description': s['description']}
              for s in stories]
    print(json.dumps(result, indent=2))


def cmd_phase_tasks(conn, phase_id):
    """Return all tasks in a phase with descriptions and acceptance criteria."""
    tasks = conn.execute(
        'SELECT DISTINCT t.id, t.title, t.story_id, t.description, '
        't.acceptance_criteria, t.complexity '
        'FROM tasks t '
        'JOIN phase_items pi ON '
        '  (pi.item_type = \'story\' AND pi.item_id = t.story_id) '
        '  OR (pi.item_type = \'epic\' AND pi.item_id = t.epic_id) '
        'WHERE pi.phase_id = ? '
        'ORDER BY t.id',
        (phase_id,)
    ).fetchall()
    result = [dict(t) for t in tasks]
    print(json.dumps(result, indent=2))


def cmd_verify_intake(conn, project_root, expected_epics, expected_stories, expected_tasks):
    """Verify plan.db completeness and integrity after the Intake Phase.

    Replaces the plan-validator agent for intake verification — all checks
    are purely mechanical (counts, referential integrity, data quality).
    """
    issues = []

    # -- Completeness: compare actual counts to expected --
    actual_epics = conn.execute('SELECT COUNT(*) AS c FROM epics').fetchone()['c']
    actual_stories = conn.execute('SELECT COUNT(*) AS c FROM stories').fetchone()['c']
    actual_tasks = conn.execute('SELECT COUNT(*) AS c FROM tasks').fetchone()['c']
    actual_phases = conn.execute('SELECT COUNT(*) AS c FROM phases').fetchone()['c']
    actual_phase_items = conn.execute('SELECT COUNT(*) AS c FROM phase_items').fetchone()['c']
    actual_deps = conn.execute('SELECT COUNT(*) AS c FROM dependencies').fetchone()['c']

    completeness = {
        'epics': {'actual': actual_epics, 'expected': expected_epics,
                  'pass': actual_epics == expected_epics},
        'stories': {'actual': actual_stories, 'expected': expected_stories,
                    'pass': actual_stories == expected_stories},
        'tasks': {'actual': actual_tasks, 'expected': expected_tasks,
                  'pass': actual_tasks == expected_tasks},
        'phases': actual_phases,
        'phase_items': actual_phase_items,
        'dependencies': actual_deps,
    }
    if not completeness['epics']['pass']:
        issues.append(f'Epic count mismatch: {actual_epics} in DB vs {expected_epics} expected')
    if not completeness['stories']['pass']:
        issues.append(f'Story count mismatch: {actual_stories} in DB vs {expected_stories} expected')
    if not completeness['tasks']['pass']:
        issues.append(f'Task count mismatch: {actual_tasks} in DB vs {expected_tasks} expected')
    if actual_phases == 0:
        issues.append('No phases found in DB')
    if actual_phase_items == 0:
        issues.append('No phase_items found — stories not mapped to phases')

    # -- Referential integrity --
    orphan_stories = conn.execute(
        'SELECT COUNT(*) AS c FROM stories WHERE epic_id NOT IN (SELECT id FROM epics)'
    ).fetchone()['c']
    orphan_tasks_story = conn.execute(
        'SELECT COUNT(*) AS c FROM tasks WHERE story_id NOT IN (SELECT id FROM stories)'
    ).fetchone()['c']
    orphan_tasks_epic = conn.execute(
        'SELECT COUNT(*) AS c FROM tasks WHERE epic_id NOT IN (SELECT id FROM epics)'
    ).fetchone()['c']
    orphan_phase_items = conn.execute(
        'SELECT COUNT(*) AS c FROM phase_items WHERE phase_id NOT IN (SELECT id FROM phases)'
    ).fetchone()['c']

    integrity = {
        'orphan_stories': orphan_stories,
        'orphan_tasks_story': orphan_tasks_story,
        'orphan_tasks_epic': orphan_tasks_epic,
        'orphan_phase_items': orphan_phase_items,
    }
    if orphan_stories:
        issues.append(f'{orphan_stories} stories reference non-existent epics')
    if orphan_tasks_story:
        issues.append(f'{orphan_tasks_story} tasks reference non-existent stories')
    if orphan_tasks_epic:
        issues.append(f'{orphan_tasks_epic} tasks reference non-existent epics')
    if orphan_phase_items:
        issues.append(f'{orphan_phase_items} phase_items reference non-existent phases')

    # -- Data quality --
    missing_titles = conn.execute(
        'SELECT COUNT(*) AS c FROM epics WHERE title IS NULL OR title = \'\''
    ).fetchone()['c']
    missing_titles += conn.execute(
        'SELECT COUNT(*) AS c FROM stories WHERE title IS NULL OR title = \'\''
    ).fetchone()['c']
    missing_titles += conn.execute(
        'SELECT COUNT(*) AS c FROM tasks WHERE title IS NULL OR title = \'\''
    ).fetchone()['c']
    if missing_titles:
        issues.append(f'{missing_titles} items missing titles')

    missing_criteria = conn.execute(
        'SELECT COUNT(*) AS c FROM phases '
        'WHERE entry_criteria IS NULL OR exit_criteria IS NULL'
    ).fetchone()['c']
    if missing_criteria:
        issues.append(f'{missing_criteria} phases missing entry/exit criteria')

    # -- Status defaults --
    non_pending = conn.execute(
        'SELECT '
        '  (SELECT COUNT(*) FROM epics WHERE status != \'pending\') + '
        '  (SELECT COUNT(*) FROM stories WHERE status != \'pending\') + '
        '  (SELECT COUNT(*) FROM tasks WHERE status != \'pending\') AS c'
    ).fetchone()['c']
    if non_pending:
        issues.append(f'{non_pending} items not in pending status (expected all pending after intake)')

    # -- Technical brief --
    brief_path = Path(project_root) / 'output' / 'technical-brief.md'
    brief_exists = brief_path.exists()
    brief_has_content = brief_exists and brief_path.stat().st_size > 0
    if not brief_exists:
        issues.append('output/technical-brief.md not found')
    elif not brief_has_content:
        issues.append('output/technical-brief.md is empty')

    overall = 'PASS' if not issues else 'FAIL'

    report = {
        'overall': overall,
        'completeness': completeness,
        'integrity': integrity,
        'technical_brief': {'exists': brief_exists, 'has_content': brief_has_content},
        'issues': issues,
    }
    print(json.dumps(report, indent=2))


def cmd_resume_phase(conn, phase_id):
    """Detect session resume state for a phase and return routing instructions."""
    phase = conn.execute(
        'SELECT * FROM phases WHERE id = ?', (phase_id,)
    ).fetchone()

    if not phase:
        print(f'ERROR: phase {phase_id} not found', file=sys.stderr)
        sys.exit(1)

    result = {
        'phase_id': phase_id,
        'phase_status': phase['status'],
    }

    # Check for in_progress orphans (tasks started but not completed)
    orphans = conn.execute(
        'SELECT DISTINCT t.id, t.title, t.story_id, t.epic_id '
        'FROM tasks t '
        'JOIN phase_items pi ON '
        '  (pi.item_type = \'story\' AND pi.item_id = t.story_id) '
        '  OR (pi.item_type = \'epic\' AND pi.item_id = t.epic_id) '
        'WHERE pi.phase_id = ? AND t.status = \'in_progress\' '
        'ORDER BY t.id',
        (phase_id,)
    ).fetchall()
    result['orphaned_tasks'] = [dict(o) for o in orphans]

    # Check for stories with pending gates (completed but gate not run)
    pending_gates = conn.execute(
        'SELECT DISTINCT s.id, s.title '
        'FROM stories s '
        'JOIN phase_items pi ON '
        '  (pi.item_type = \'story\' AND pi.item_id = s.id) '
        '  OR (pi.item_type = \'epic\' AND pi.item_id = s.epic_id) '
        'WHERE pi.phase_id = ? AND s.gate_status = \'pending\' '
        'ORDER BY s.id',
        (phase_id,)
    ).fetchall()
    result['pending_story_gates'] = [dict(g) for g in pending_gates]

    # Determine resume point
    phase_status = phase['status']

    if phase_status == 'pending':
        result['resume_step'] = 1
        result['resume_action'] = 'start_fresh'
    elif phase_status == 'tests_written':
        if orphans:
            result['resume_step'] = 5
            result['resume_action'] = 'resume_orphan'
        else:
            result['resume_step'] = 3
            result['resume_action'] = 'find_next_task'
    elif phase_status == 'in_progress':
        if orphans and pending_gates:
            result['resume_step'] = 5
            result['resume_action'] = 'resume_mixed'
        elif orphans:
            result['resume_step'] = 5
            result['resume_action'] = 'resume_orphan'
        elif pending_gates:
            result['resume_step'] = 8
            result['resume_action'] = 'run_story_gate'
        else:
            result['resume_step'] = 3
            result['resume_action'] = 'find_next_task'
    elif phase_status == 'gate_pending':
        result['resume_step'] = 10
        result['resume_action'] = 'run_phase_gate'
    elif phase_status == 'complete':
        result['resume_step'] = None
        result['resume_action'] = 'already_complete'

    print(json.dumps(result, indent=2))


def cmd_update_phase(conn, phase_id, status=None, goal=None,
                     entry_criteria=None, exit_criteria=None):
    """Update phase lifecycle status and/or content fields."""
    phase = conn.execute(
        'SELECT id, name FROM phases WHERE id = ?', (phase_id,)
    ).fetchone()
    if not phase:
        print(f'ERROR: phase {phase_id} not found', file=sys.stderr)
        sys.exit(1)

    fields, values, updated = [], [], []

    if status is not None:
        valid = ('pending', 'tests_written', 'in_progress', 'gate_pending', 'complete')
        if status not in valid:
            print(f'ERROR: invalid status "{status}". '
                  f'Must be one of: {", ".join(valid)}', file=sys.stderr)
            sys.exit(1)
        fields.append('status = ?'); values.append(status); updated.append('status')
    if goal is not None:
        fields.append('goal = ?'); values.append(goal); updated.append('goal')
    if entry_criteria is not None:
        fields.append('entry_criteria = ?'); values.append(entry_criteria); updated.append('entry_criteria')
    if exit_criteria is not None:
        fields.append('exit_criteria = ?'); values.append(exit_criteria); updated.append('exit_criteria')

    if not fields:
        print('ERROR: no fields to update. Use --status, --goal, --entry-criteria, or --exit-criteria.',
              file=sys.stderr)
        sys.exit(1)

    values.append(phase_id)
    conn.execute(f'UPDATE phases SET {", ".join(fields)} WHERE id = ?', values)
    conn.commit()

    emit_event('phase_updated', {
        'phase_id': phase_id,
        'status': status,
        'fields': updated,
    })

    if status and len(updated) == 1:
        print(f'Phase {phase_id} ({phase["name"]}): status → {status}')
    elif status:
        content_fields = [f for f in updated if f != 'status']
        print(f'Phase {phase_id} ({phase["name"]}): status → {status}, updated {", ".join(content_fields)}')
    else:
        print(f'Phase {phase_id} ({phase["name"]}): updated {", ".join(updated)}')


def cmd_list_docs(project_root):
    """List available reference documentation from docs/ and input/docs/."""
    root = Path(project_root)
    framework_dir = root / 'docs'
    project_dir = root / 'input' / 'docs'
    framework_docs = sorted(framework_dir.iterdir()) if framework_dir.is_dir() else []
    project_docs = sorted(project_dir.iterdir()) if project_dir.is_dir() else []

    # Filter to .md files, exclude .gitkeep
    framework = [f.name for f in framework_docs if f.suffix == '.md' and f.name != '.gitkeep']
    project = [f.name for f in project_docs if f.suffix == '.md' and f.name != '.gitkeep']

    result = {
        'framework_docs': framework,
        'project_docs': project,
        'all_docs': framework + project,
        'count': len(framework) + len(project),
    }
    print(json.dumps(result, indent=2))


def cmd_update_story_gate(conn, story_id, status):
    """Update story gate review status."""
    valid = ('pending', 'passed', 'failed')
    if status not in valid:
        print(f'ERROR: invalid gate status "{status}". '
              f'Must be one of: {", ".join(valid)}', file=sys.stderr)
        sys.exit(1)

    story = conn.execute(
        'SELECT id, title FROM stories WHERE id = ?', (story_id,)
    ).fetchone()
    if not story:
        print(f'ERROR: story {story_id} not found', file=sys.stderr)
        sys.exit(1)

    conn.execute(
        'UPDATE stories SET gate_status = ? WHERE id = ?', (status, story_id)
    )
    conn.commit()

    emit_event('story_gate_updated', {'story_id': story_id, 'status': status})

    print(f'Story {story_id} ({story["title"]}): gate_status → {status}')


def cmd_schema(conn):
    """Dump database table names, column names, and types as JSON."""
    tables_raw = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        r"AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '\_%' ESCAPE '\' "
        "ORDER BY name"
    ).fetchall()

    tables = {}
    for t in tables_raw:
        cols = conn.execute(f"PRAGMA table_info({t['name']})").fetchall()
        tables[t['name']] = [
            {'name': c['name'], 'type': c['type'], 'notnull': bool(c['notnull']),
             'pk': bool(c['pk'])}
            for c in cols
        ]

    print(json.dumps({'tables': tables}, indent=2))


def cmd_show(conn, item_id):
    """Show all fields for any item by ID (auto-detects type from prefix)."""
    prefix_map = {
        'epic-': 'epics',
        'story-': 'stories',
        'task-': 'tasks',
        'phase-': 'phases',
    }

    table = None
    for prefix, tbl in prefix_map.items():
        if item_id.startswith(prefix):
            table = tbl
            break

    if not table:
        print(f'ERROR: cannot detect type from ID "{item_id}". '
              f'Expected prefix: {", ".join(prefix_map.keys())}', file=sys.stderr)
        sys.exit(1)

    row = conn.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,)).fetchone()
    if not row:
        print(f'ERROR: {item_id} not found in {table}', file=sys.stderr)
        sys.exit(1)

    print(json.dumps(dict(row), indent=2))


def cmd_update_task(conn, task_id, title=None, description=None, acceptance_criteria=None):
    """Update content fields on a task."""
    task = conn.execute(
        'SELECT id, title, status FROM tasks WHERE id = ?', (task_id,)
    ).fetchone()
    if not task:
        print(f'ERROR: task {task_id} not found', file=sys.stderr)
        sys.exit(1)

    if task['status'] == 'complete':
        print(f'WARNING: updating completed task {task_id}', file=sys.stderr)

    fields, values, updated = [], [], []
    if title is not None:
        fields.append('title = ?'); values.append(title); updated.append('title')
    if description is not None:
        fields.append('description = ?'); values.append(description); updated.append('description')
    if acceptance_criteria is not None:
        fields.append('acceptance_criteria = ?'); values.append(acceptance_criteria); updated.append('acceptance_criteria')

    if not fields:
        print('ERROR: no fields to update. Use --title, --description, or --acceptance-criteria.', file=sys.stderr)
        sys.exit(1)

    values.append(task_id)
    conn.execute(f'UPDATE tasks SET {", ".join(fields)} WHERE id = ?', values)
    conn.commit()

    emit_event('task_content_updated', {'task_id': task_id, 'fields': updated})
    print(f'Updated: {task_id} — {", ".join(updated)}')


def cmd_update_story(conn, story_id, title=None, description=None):
    """Update content fields on a story."""
    story = conn.execute(
        'SELECT id, title, status FROM stories WHERE id = ?', (story_id,)
    ).fetchone()
    if not story:
        print(f'ERROR: story {story_id} not found', file=sys.stderr)
        sys.exit(1)

    if story['status'] == 'complete':
        print(f'WARNING: updating completed story {story_id}', file=sys.stderr)

    fields, values, updated = [], [], []
    if title is not None:
        fields.append('title = ?'); values.append(title); updated.append('title')
    if description is not None:
        fields.append('description = ?'); values.append(description); updated.append('description')

    if not fields:
        print('ERROR: no fields to update. Use --title or --description.', file=sys.stderr)
        sys.exit(1)

    values.append(story_id)
    conn.execute(f'UPDATE stories SET {", ".join(fields)} WHERE id = ?', values)
    conn.commit()

    emit_event('story_content_updated', {'story_id': story_id, 'fields': updated})
    print(f'Updated: {story_id} — {", ".join(updated)}')


def cmd_update_epic(conn, epic_id, title=None, description=None):
    """Update content fields on an epic."""
    epic = conn.execute(
        'SELECT id, title, status FROM epics WHERE id = ?', (epic_id,)
    ).fetchone()
    if not epic:
        print(f'ERROR: epic {epic_id} not found', file=sys.stderr)
        sys.exit(1)

    if epic['status'] == 'complete':
        print(f'WARNING: updating completed epic {epic_id}', file=sys.stderr)

    fields, values, updated = [], [], []
    if title is not None:
        fields.append('title = ?'); values.append(title); updated.append('title')
    if description is not None:
        fields.append('description = ?'); values.append(description); updated.append('description')

    if not fields:
        print('ERROR: no fields to update. Use --title or --description.', file=sys.stderr)
        sys.exit(1)

    values.append(epic_id)
    conn.execute(f'UPDATE epics SET {", ".join(fields)} WHERE id = ?', values)
    conn.commit()

    emit_event('epic_content_updated', {'epic_id': epic_id, 'fields': updated})
    print(f'Updated: {epic_id} — {", ".join(updated)}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Clyde plan.db operations (intake verification + implementation phase)'
    )
    parser.add_argument(
        '--project-root', default=str(Path(__file__).resolve().parent.parent),
        help='Project root directory (default: derived from script location)'
    )

    sub = parser.add_subparsers(dest='command')
    sub.required = True

    p_next = sub.add_parser('next-task', help='Find next unblocked pending task')
    p_next.add_argument('--phase', help='Filter to a specific phase ID')

    p_avail = sub.add_parser('available-tasks',
                             help='Find all unblocked pending tasks (one per story)')
    p_avail.add_argument('--phase', help='Filter to a specific phase ID')
    p_avail.add_argument('--limit', type=int, help='Max tasks to return')

    p_ctx = sub.add_parser('task-context', help='Get full context for a task')
    p_ctx.add_argument('task_id', help='Task ID')

    p_start = sub.add_parser('start-task', help='Mark task as in_progress')
    p_start.add_argument('task_id', help='Task ID')

    p_done = sub.add_parser('complete-task', help='Mark task as complete')
    p_done.add_argument('task_id', help='Task ID')
    p_done.add_argument('--files', nargs='+', help='Files changed by this task')
    p_done.add_argument('--json', action='store_true', dest='output_json',
                        help='Output JSON instead of human text')

    sub.add_parser('progress', help='Show overall project progress')

    p_phase = sub.add_parser('phase-status', help='Show phase progress')
    p_phase.add_argument('phase_id', help='Phase ID')

    p_skip = sub.add_parser('skip-task', help='Mark task as skipped')
    p_skip.add_argument('task_id', help='Task ID')
    p_skip.add_argument('--reason', required=True, help='Why the task was skipped')

    p_retry = sub.add_parser('retry-task', help='Reset skipped task to pending')
    p_retry.add_argument('task_id', help='Task ID')

    p_list_skip = sub.add_parser('list-skipped', help='List all skipped tasks')
    p_list_skip.add_argument('--phase', help='Filter to a specific phase ID')

    p_story_files = sub.add_parser('story-files', help='List files changed in a story')
    p_story_files.add_argument('story_id', help='Story ID')

    p_phase_files = sub.add_parser('phase-files', help='List files changed in a phase')
    p_phase_files.add_argument('phase_id', help='Phase ID')

    p_phase_stories = sub.add_parser('phase-stories', help='List stories in a phase')
    p_phase_stories.add_argument('phase_id', help='Phase ID')

    p_phase_tasks = sub.add_parser('phase-tasks',
                                   help='List tasks in a phase with descriptions')
    p_phase_tasks.add_argument('phase_id', help='Phase ID')

    p_verify = sub.add_parser('verify-intake', help='Verify plan.db after intake')
    p_verify.add_argument('--expected-epics', type=int, required=True)
    p_verify.add_argument('--expected-stories', type=int, required=True)
    p_verify.add_argument('--expected-tasks', type=int, required=True)

    p_resume = sub.add_parser('resume-phase', help='Detect session resume state for a phase')
    p_resume.add_argument('phase_id', help='Phase ID')

    p_uphase = sub.add_parser('update-phase', help='Update phase status or content')
    p_uphase.add_argument('phase_id', help='Phase ID')
    p_uphase.add_argument('--status',
                          choices=['pending', 'tests_written', 'in_progress',
                                   'gate_pending', 'complete'],
                          help='New phase status')
    p_uphase.add_argument('--goal', help='New phase goal')
    p_uphase.add_argument('--entry-criteria', help='New entry criteria')
    p_uphase.add_argument('--exit-criteria', help='New exit criteria')

    p_ugate = sub.add_parser('update-story-gate', help='Update story gate review status')
    p_ugate.add_argument('story_id', help='Story ID')
    p_ugate.add_argument('--status', required=True,
                         choices=['pending', 'passed', 'failed'],
                         help='Gate review result')

    sub.add_parser('active-phase', help='Find the currently active phase (JSON)')

    sub.add_parser('list-docs',
                   help='List available reference docs from docs/ and input/docs/ (JSON)')

    p_batch = sub.add_parser('batch-check',
                             help='Increment batch counter and check budget (JSON)')
    p_batch.add_argument('--reset', action='store_true',
                         help='Reset counter to 0 instead of incrementing')
    p_batch.add_argument('--budget', type=int, default=8,
                         help='Batch budget (default: 8)')

    sub.add_parser('schema', help='Show database table structure (JSON)')

    p_show = sub.add_parser('show', help='Inspect any item by ID (JSON)')
    p_show.add_argument('item_id', help='Item ID (auto-detects type from prefix)')

    p_utask = sub.add_parser('update-task', help='Update task content fields')
    p_utask.add_argument('task_id', help='Task ID')
    p_utask.add_argument('--title', help='New task title')
    p_utask.add_argument('--description', help='New task description')
    p_utask.add_argument('--acceptance-criteria', help='New acceptance criteria')

    p_ustory = sub.add_parser('update-story', help='Update story content fields')
    p_ustory.add_argument('story_id', help='Story ID')
    p_ustory.add_argument('--title', help='New story title')
    p_ustory.add_argument('--description', help='New story description')

    p_uepic = sub.add_parser('update-epic', help='Update epic content fields')
    p_uepic.add_argument('epic_id', help='Epic ID')
    p_uepic.add_argument('--title', help='New epic title')
    p_uepic.add_argument('--description', help='New epic description')

    args = parser.parse_args()

    _project_root = args.project_root  # noqa: F841 — used by emit_event()

    # Commands that don't need a DB connection
    if args.command == 'list-docs':
        cmd_list_docs(args.project_root)
        sys.exit(0)
    if args.command == 'batch-check':
        cmd_batch_check(args.project_root, reset=args.reset, budget=args.budget)
        sys.exit(0)

    conn = get_db(args.project_root)

    if args.command == 'next-task':
        cmd_next_task(conn, args.phase)
    elif args.command == 'available-tasks':
        cmd_available_tasks(conn, args.phase, args.limit)
    elif args.command == 'task-context':
        cmd_task_context(conn, args.task_id)
    elif args.command == 'start-task':
        cmd_start_task(conn, args.task_id)
    elif args.command == 'complete-task':
        cmd_complete_task(conn, args.task_id, files=args.files,
                          output_json=args.output_json)
    elif args.command == 'progress':
        cmd_progress(conn)
    elif args.command == 'phase-status':
        cmd_phase_status(conn, args.phase_id)
    elif args.command == 'skip-task':
        cmd_skip_task(conn, args.task_id, args.reason)
    elif args.command == 'retry-task':
        cmd_retry_task(conn, args.task_id)
    elif args.command == 'list-skipped':
        cmd_list_skipped(conn, args.phase)
    elif args.command == 'story-files':
        cmd_story_files(conn, args.story_id)
    elif args.command == 'phase-files':
        cmd_phase_files(conn, args.phase_id)
    elif args.command == 'phase-stories':
        cmd_phase_stories(conn, args.phase_id)
    elif args.command == 'phase-tasks':
        cmd_phase_tasks(conn, args.phase_id)
    elif args.command == 'verify-intake':
        cmd_verify_intake(conn, args.project_root,
                          args.expected_epics, args.expected_stories, args.expected_tasks)
    elif args.command == 'resume-phase':
        cmd_resume_phase(conn, args.phase_id)
    elif args.command == 'update-phase':
        cmd_update_phase(conn, args.phase_id, status=args.status,
                         goal=args.goal,
                         entry_criteria=args.entry_criteria,
                         exit_criteria=args.exit_criteria)
    elif args.command == 'update-story-gate':
        cmd_update_story_gate(conn, args.story_id, args.status)
    elif args.command == 'active-phase':
        cmd_active_phase(conn)
    elif args.command == 'schema':
        cmd_schema(conn)
    elif args.command == 'show':
        cmd_show(conn, args.item_id)
    elif args.command == 'update-task':
        cmd_update_task(conn, args.task_id, title=args.title,
                        description=args.description,
                        acceptance_criteria=args.acceptance_criteria)
    elif args.command == 'update-story':
        cmd_update_story(conn, args.story_id, title=args.title,
                         description=args.description)
    elif args.command == 'update-epic':
        cmd_update_epic(conn, args.epic_id, title=args.title,
                        description=args.description)

    conn.close()
