#!/usr/bin/env python3
"""
build-plan-db.py — Reads clyde input files and populates output/plan.db.

Zero external dependencies (Python 3 stdlib only).
Parses YAML frontmatter from epics, stories, and tasks, creates the
database schema, and inserts structured data.

Work-sequence parsing (phases, phase_items) is left to the AI analyzer
agent, since that content is freeform markdown that varies across projects.

Usage: python3 scripts/build-plan-db.py [--project-root PATH]
  Defaults to current working directory if --project-root is not specified.
"""

import os
import re
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# YAML frontmatter parser (handles clyde's known subset only)
# ---------------------------------------------------------------------------

def parse_frontmatter(text):
    """Parse YAML frontmatter from a markdown file's text content.

    Handles:
      key: value            -> str
      key: [a, b, c]        -> list of str
      key: []               -> []
      key: [TBD]            -> str "[TBD]"
    """
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not match:
        return None, text
    raw = match.group(1)
    body = text[match.end():]
    fields = {}
    for line in raw.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        colon_idx = line.find(': ')
        if colon_idx == -1:
            # handle "key:" with no value
            if line.endswith(':'):
                fields[line[:-1].strip()] = ''
            continue
        key = line[:colon_idx].strip()
        val = line[colon_idx + 2:].strip()
        # bracket list
        if val.startswith('[') and val.endswith(']'):
            inner = val[1:-1].strip()
            if not inner:
                fields[key] = []
            elif ',' not in inner and not _looks_like_id(inner):
                # single non-ID value like [TBD] — treat as string
                fields[key] = val
            else:
                fields[key] = [item.strip() for item in inner.split(',') if item.strip()]
        else:
            fields[key] = val
    return fields, body


def _looks_like_id(s):
    """Check if a string looks like a clyde item ID (epic-NNN, story-NNN-NNN, task-NNN-NNN-NN)."""
    return bool(re.match(r'^(epic|story|task)-\d', s))


# ---------------------------------------------------------------------------
# Markdown section extractor
# ---------------------------------------------------------------------------

def extract_section(body, heading):
    """Extract the content under a ## heading until the next ## or end of file."""
    pattern = re.compile(
        r'^##\s+' + re.escape(heading) + r'\s*\n(.*?)(?=^##\s|\Z)',
        re.MULTILINE | re.DOTALL
    )
    m = pattern.search(body)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# ID type inference
# ---------------------------------------------------------------------------

def infer_type(item_id):
    """Infer item type from ID prefix."""
    if item_id.startswith('epic-'):
        return 'epic'
    elif item_id.startswith('story-'):
        return 'story'
    elif item_id.startswith('task-'):
        return 'task'
    return None


# ---------------------------------------------------------------------------
# Main build logic
# ---------------------------------------------------------------------------

def build_db(project_root):
    project_root = Path(project_root)
    input_dir = project_root / 'input'
    output_dir = project_root / 'output'
    schema_file = project_root / 'schema.sql'

    # Validation
    errors = []
    warnings = []

    if not schema_file.exists():
        errors.append(f'schema.sql not found at {schema_file}')
    if not input_dir.exists():
        errors.append(f'input/ directory not found at {input_dir}')
    if errors:
        for e in errors:
            print(f'ERROR: {e}', file=sys.stderr)
        return 1

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / 'plan.db'
    # Remove existing db to start fresh
    if db_path.exists():
        db_path.unlink()

    # Inventory input files
    epic_files = sorted((input_dir / 'epics').glob('epic-*.md'))
    story_files = sorted((input_dir / 'stories').glob('story-*.md'))
    task_files = sorted((input_dir / 'tasks').glob('task-*.md'))

    if not epic_files:
        warnings.append('No epic files found in input/epics/')
    if not story_files:
        warnings.append('No story files found in input/stories/')
    if not task_files:
        warnings.append('No task files found in input/tasks/')

    print(f'Input files found:')
    print(f'  Epics:   {len(epic_files)}')
    print(f'  Stories: {len(story_files)}')
    print(f'  Tasks:   {len(task_files)}')
    print()

    if errors:
        for e in errors:
            print(f'ERROR: {e}', file=sys.stderr)
        return 1

    # Create database from schema
    conn = sqlite3.connect(str(db_path))
    conn.execute('PRAGMA foreign_keys = ON')
    schema_sql = schema_file.read_text()
    conn.executescript(schema_sql)

    # Track counts
    counts = {'epics': 0, 'stories': 0, 'tasks': 0, 'dependencies': 0}
    failed_files = []

    # --- Insert epics ---
    for f in epic_files:
        try:
            text = f.read_text()
            fm, body = parse_frontmatter(text)
            if fm is None:
                warnings.append(f'{f.name}: no frontmatter found')
                failed_files.append(f.name)
                continue
            eid = fm.get('id')
            title = fm.get('title')
            priority = fm.get('priority')
            if not eid:
                warnings.append(f'{f.name}: missing required field "id"')
                failed_files.append(f.name)
                continue
            if not title:
                warnings.append(f'{f.name}: missing required field "title"')
            # Extract description from body
            desc = extract_section(body, 'Description') or body.strip()
            conn.execute(
                'INSERT INTO epics (id, title, priority, description) VALUES (?, ?, ?, ?)',
                (eid, title or '', priority, desc)
            )
            counts['epics'] += 1
        except Exception as e:
            warnings.append(f'{f.name}: error — {e}')
            failed_files.append(f.name)

    # --- Insert stories ---
    for f in story_files:
        try:
            text = f.read_text()
            fm, body = parse_frontmatter(text)
            if fm is None:
                warnings.append(f'{f.name}: no frontmatter found')
                failed_files.append(f.name)
                continue
            sid = fm.get('id')
            epic_id = fm.get('epic')
            title = fm.get('title')
            priority = fm.get('priority')
            sp = fm.get('story_points', '')
            if isinstance(sp, list):
                sp = ', '.join(sp)
            if not sid:
                warnings.append(f'{f.name}: missing required field "id"')
                failed_files.append(f.name)
                continue
            if not epic_id:
                warnings.append(f'{f.name}: missing required field "epic"')
                failed_files.append(f.name)
                continue
            desc = body.strip()
            conn.execute(
                'INSERT INTO stories (id, epic_id, title, priority, story_points, description) VALUES (?, ?, ?, ?, ?, ?)',
                (sid, epic_id, title or '', priority, sp, desc)
            )
            counts['stories'] += 1

            # Dependencies from frontmatter
            deps = fm.get('dependencies', [])
            if isinstance(deps, list):
                for dep_id in deps:
                    dep_type = infer_type(dep_id)
                    if dep_type:
                        conn.execute(
                            'INSERT OR IGNORE INTO dependencies (item_id, item_type, depends_on_id, depends_on_type) VALUES (?, ?, ?, ?)',
                            (sid, 'story', dep_id, dep_type)
                        )
                        counts['dependencies'] += 1

            # Blocks from frontmatter
            blocks = fm.get('blocks', [])
            if isinstance(blocks, list):
                for blocked_id in blocks:
                    blocked_type = infer_type(blocked_id)
                    if blocked_type:
                        conn.execute(
                            'INSERT OR IGNORE INTO dependencies (item_id, item_type, depends_on_id, depends_on_type) VALUES (?, ?, ?, ?)',
                            (blocked_id, blocked_type, sid, 'story')
                        )
                        counts['dependencies'] += 1

        except sqlite3.IntegrityError as e:
            warnings.append(f'{f.name}: integrity error — {e}')
            failed_files.append(f.name)
        except Exception as e:
            warnings.append(f'{f.name}: error — {e}')
            failed_files.append(f.name)

    # --- Insert tasks ---
    for f in task_files:
        try:
            text = f.read_text()
            fm, body = parse_frontmatter(text)
            if fm is None:
                warnings.append(f'{f.name}: no frontmatter found')
                failed_files.append(f.name)
                continue
            tid = fm.get('id')
            story_id = fm.get('story')
            epic_id = fm.get('epic')
            title = fm.get('title')
            complexity = fm.get('complexity')
            if not tid:
                warnings.append(f'{f.name}: missing required field "id"')
                failed_files.append(f.name)
                continue
            if not story_id:
                warnings.append(f'{f.name}: missing required field "story"')
                failed_files.append(f.name)
                continue
            # Infer epic_id from story_id if not present (story-NNN-NNN -> epic-NNN)
            if not epic_id and story_id:
                parts = story_id.split('-')
                if len(parts) >= 2:
                    epic_id = f'epic-{parts[1]}'

            desc = extract_section(body, 'Description')
            ac = extract_section(body, 'Acceptance Criteria')
            complexity_int = None
            if complexity is not None:
                try:
                    complexity_int = int(complexity)
                except (ValueError, TypeError):
                    warnings.append(f'{f.name}: non-integer complexity "{complexity}"')

            conn.execute(
                'INSERT INTO tasks (id, story_id, epic_id, title, complexity, description, acceptance_criteria) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (tid, story_id, epic_id, title or '', complexity_int, desc, ac)
            )
            counts['tasks'] += 1

        except sqlite3.IntegrityError as e:
            warnings.append(f'{f.name}: integrity error — {e}')
            failed_files.append(f.name)
        except Exception as e:
            warnings.append(f'{f.name}: error — {e}')
            failed_files.append(f.name)

    conn.commit()

    # --- Dependency integrity check ---
    all_ids = set()
    for table in ('epics', 'stories', 'tasks'):
        cursor = conn.execute(f'SELECT id FROM {table}')
        for row in cursor:
            all_ids.add(row[0])

    orphan_deps = conn.execute(
        'SELECT item_id, item_type, depends_on_id, depends_on_type FROM dependencies'
    ).fetchall()
    orphans = []
    for item_id, item_type, dep_id, dep_type in orphan_deps:
        if item_id not in all_ids:
            orphans.append(f'dependency references unknown item: {item_id} ({item_type})')
        if dep_id not in all_ids:
            orphans.append(f'dependency references unknown target: {dep_id} ({dep_type})')
    for o in orphans:
        warnings.append(f'Orphaned {o}')

    # --- Count reconciliation ---
    reconciliation_ok = True
    for label, file_list, table in [
        ('epics', epic_files, 'epics'),
        ('stories', story_files, 'stories'),
        ('tasks', task_files, 'tasks'),
    ]:
        file_count = len(file_list)
        row_count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        if file_count != row_count:
            warnings.append(
                f'Count mismatch for {label}: {file_count} files found, {row_count} rows inserted'
            )
            reconciliation_ok = False

    # --- Results ---
    print('=' * 60)
    print('RESULTS')
    print('=' * 60)
    print()
    print(f'Inserted:')
    print(f'  Epics:        {counts["epics"]}')
    print(f'  Stories:      {counts["stories"]}')
    print(f'  Tasks:        {counts["tasks"]}')
    print(f'  Dependencies: {counts["dependencies"]}')
    print()
    print('Note: phases and phase_items are populated separately')
    print('      (analyzer extracts JSON, insert-phases.py loads it)')
    print()

    if reconciliation_ok:
        print('Count reconciliation: PASS')
    else:
        print('Count reconciliation: FAIL (see warnings)')
    print()

    # Sample rows for eyeball verification
    print('--- Sample Rows ---')
    print()
    row = conn.execute('SELECT id, title, priority FROM epics ORDER BY id LIMIT 1').fetchone()
    if row:
        print(f'First epic:  {row[0]} | {row[1]} | priority={row[2]}')
    row = conn.execute('SELECT id, title, priority FROM epics ORDER BY id DESC LIMIT 1').fetchone()
    if row:
        print(f'Last epic:   {row[0]} | {row[1]} | priority={row[2]}')
    print()

    row = conn.execute(
        'SELECT t.id, t.title, t.story_id, t.epic_id FROM tasks t ORDER BY t.id LIMIT 1'
    ).fetchone()
    if row:
        print(f'First task:  {row[0]} | {row[1]}')
        print(f'  -> story: {row[2]}, epic: {row[3]}')
    print()

    dep_count = conn.execute('SELECT COUNT(*) FROM dependencies').fetchone()[0]
    print(f'Total dependencies in DB: {dep_count}')
    print()

    # Warnings summary
    if warnings:
        print('=' * 60)
        print(f'WARNINGS ({len(warnings)})')
        print('=' * 60)
        for w in warnings:
            print(f'  ! {w}')
        print()

    if failed_files:
        print(f'Failed files ({len(failed_files)}):')
        for ff in failed_files:
            print(f'  - {ff}')
        print()

    conn.close()

    print(f'Database written to: {db_path}')

    if failed_files:
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    root = os.getcwd()
    if '--project-root' in sys.argv:
        idx = sys.argv.index('--project-root')
        if idx + 1 < len(sys.argv):
            root = sys.argv[idx + 1]
        else:
            print('ERROR: --project-root requires a path argument', file=sys.stderr)
            sys.exit(1)

    sys.exit(build_db(root))
