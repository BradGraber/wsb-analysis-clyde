#!/usr/bin/env python3
"""
plan-ops.py — Query and update plan.db during Phase 2 implementation.

Zero external dependencies (Python 3 stdlib only).
Provides subcommands for the Phase 2 orchestrator to find work,
gather context, and update progress without writing raw SQL.

Usage:
  python3 scripts/plan-ops.py next-task [--phase PHASE_ID]
  python3 scripts/plan-ops.py task-context TASK_ID
  python3 scripts/plan-ops.py start-task TASK_ID
  python3 scripts/plan-ops.py complete-task TASK_ID
  python3 scripts/plan-ops.py progress
  python3 scripts/plan-ops.py phase-status PHASE_ID
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def get_db(project_root):
    """Open plan.db with row_factory for dict-like access."""
    db_path = Path(project_root) / 'output' / 'plan.db'
    if not db_path.exists():
        print(f'ERROR: {db_path} not found. Run Phase 1 first.', file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    conn.execute('PRAGMA foreign_keys = ON')
    conn.row_factory = sqlite3.Row
    return conn


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
        table = dep['depends_on_type'] + 's'  # epic→epics, story→stories, task→tasks
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

    conn.commit()

    print(f'Started: {task_id} — {task["title"]}')
    story_status = conn.execute(
        'SELECT status FROM stories WHERE id = ?', (task['story_id'],)
    ).fetchone()
    epic_status = conn.execute(
        'SELECT status FROM epics WHERE id = ?', (task['epic_id'],)
    ).fetchone()
    print(f'  Story {task["story_id"]}: {story_status["status"]}')
    print(f'  Epic {task["epic_id"]}: {epic_status["status"]}')


def cmd_complete_task(conn, task_id):
    """Mark a task as complete, cascade to story and epic if all children done."""
    task = conn.execute(
        'SELECT id, title, story_id, epic_id, status FROM tasks WHERE id = ?',
        (task_id,)
    ).fetchone()

    if not task:
        print(f'ERROR: task {task_id} not found', file=sys.stderr)
        sys.exit(1)

    conn.execute(
        'UPDATE tasks SET status = \'complete\' WHERE id = ?',
        (task_id,)
    )
    print(f'Completed: {task_id} — {task["title"]}')

    # Check if all tasks in the story are complete
    remaining = conn.execute(
        'SELECT COUNT(*) AS count FROM tasks '
        'WHERE story_id = ? AND status != \'complete\'',
        (task['story_id'],)
    ).fetchone()

    if remaining['count'] == 0:
        conn.execute(
            'UPDATE stories SET status = \'complete\' WHERE id = ?',
            (task['story_id'],)
        )
        print(f'  Story {task["story_id"]}: complete (all tasks done)')

        # Check if all stories in the epic are complete
        remaining_stories = conn.execute(
            'SELECT COUNT(*) AS count FROM stories '
            'WHERE epic_id = ? AND status != \'complete\'',
            (task['epic_id'],)
        ).fetchone()

        if remaining_stories['count'] == 0:
            conn.execute(
                'UPDATE epics SET status = \'complete\' WHERE id = ?',
                (task['epic_id'],)
            )
            print(f'  Epic {task["epic_id"]}: complete (all stories done)')
        else:
            print(f'  Epic {task["epic_id"]}: {remaining_stories["count"]} stories remaining')
    else:
        print(f'  Story {task["story_id"]}: {remaining["count"]} tasks remaining')

    conn.commit()


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
    print(f'  Tasks:   {task_by.get("complete", 0)}/{task_total} complete, '
          f'{task_by.get("in_progress", 0)} in progress, '
          f'{task_by.get("pending", 0)} pending')
    print(f'  Stories: {story_by.get("complete", 0)}/{story_total} complete, '
          f'{story_by.get("in_progress", 0)} in progress, '
          f'{story_by.get("pending", 0)} pending')
    print(f'  Epics:   {epic_by.get("complete", 0)}/{epic_total} complete, '
          f'{epic_by.get("in_progress", 0)} in progress, '
          f'{epic_by.get("pending", 0)} pending')

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
    phases = conn.execute('SELECT id, name FROM phases ORDER BY id').fetchall()
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
            print(f'  {p["id"]}: {p["name"]} — {complete}/{total} tasks ({pct}%)')


def cmd_phase_status(conn, phase_id):
    """Show progress for a phase."""
    phase = conn.execute(
        'SELECT * FROM phases WHERE id = ?', (phase_id,)
    ).fetchone()

    if not phase:
        print(f'ERROR: phase {phase_id} not found', file=sys.stderr)
        sys.exit(1)

    print(f'Phase: {phase["name"]} ({phase["id"]})')
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

    print(f'Tasks: {complete}/{total} complete, {in_progress} in progress, {pending} pending')
    print()

    print('Entry Criteria:')
    for line in (phase['entry_criteria'] or 'None').split('\n'):
        print(f'  {line}')
    print()
    print('Exit Criteria:')
    for line in (phase['exit_criteria'] or 'None').split('\n'):
        print(f'  {line}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Phase 2 plan.db operations'
    )
    parser.add_argument(
        '--project-root', default='.',
        help='Project root directory (default: cwd)'
    )

    sub = parser.add_subparsers(dest='command')
    sub.required = True

    p_next = sub.add_parser('next-task', help='Find next unblocked pending task')
    p_next.add_argument('--phase', help='Filter to a specific phase ID')

    p_ctx = sub.add_parser('task-context', help='Get full context for a task')
    p_ctx.add_argument('task_id', help='Task ID')

    p_start = sub.add_parser('start-task', help='Mark task as in_progress')
    p_start.add_argument('task_id', help='Task ID')

    p_done = sub.add_parser('complete-task', help='Mark task as complete')
    p_done.add_argument('task_id', help='Task ID')

    sub.add_parser('progress', help='Show overall project progress')

    p_phase = sub.add_parser('phase-status', help='Show phase progress')
    p_phase.add_argument('phase_id', help='Phase ID')

    args = parser.parse_args()
    conn = get_db(args.project_root)

    if args.command == 'next-task':
        cmd_next_task(conn, args.phase)
    elif args.command == 'task-context':
        cmd_task_context(conn, args.task_id)
    elif args.command == 'start-task':
        cmd_start_task(conn, args.task_id)
    elif args.command == 'complete-task':
        cmd_complete_task(conn, args.task_id)
    elif args.command == 'progress':
        cmd_progress(conn)
    elif args.command == 'phase-status':
        cmd_phase_status(conn, args.phase_id)

    conn.close()
