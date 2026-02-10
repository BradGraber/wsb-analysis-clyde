#!/usr/bin/env python3
"""
insert-phases.py — Inserts phase data from JSON into plan.db.

Zero external dependencies (Python 3 stdlib only).
Companion to build-plan-db.py — that script handles structured data
(epics, stories, tasks); this one handles phases and phase_items
as extracted by the analyzer agent from work-sequence.md.

Expected JSON format (array of phase objects):
[
  {
    "id": "phase-a",
    "sequence": 1,
    "name": "Foundation",
    "goal": "...",
    "entry_criteria": "...",
    "exit_criteria": "...",
    "estimated_duration": "2 weeks",
    "items": [
      {"id": "epic-001", "type": "epic"},
      {"id": "story-001-001", "type": "story"}
    ]
  }
]

Usage:
  python3 scripts/insert-phases.py <db_path> <json_file>
  python3 scripts/insert-phases.py <db_path> < phases.json
"""

import json
import sqlite3
import sys


def insert_phases(db_path, phases):
    """Insert phase records and their items into plan.db."""
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')

    phase_count = 0
    item_count = 0
    warnings = []

    for phase in phases:
        pid = phase.get('id')
        if not pid:
            warnings.append('Phase missing required field "id", skipping')
            continue

        conn.execute(
            'INSERT INTO phases (id, sequence, name, goal, entry_criteria, exit_criteria, estimated_duration) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                pid,
                phase.get('sequence'),
                phase.get('name', ''),
                phase.get('goal'),
                phase.get('entry_criteria'),
                phase.get('exit_criteria'),
                phase.get('estimated_duration'),
            )
        )
        phase_count += 1

        for item in phase.get('items', []):
            item_id = item.get('id') or item.get('item_id')
            item_type = item.get('type') or item.get('item_type')
            if not item_id or not item_type:
                warnings.append(f'Phase {pid}: item missing id or type, skipping')
                continue
            if item_type not in ('epic', 'story'):
                warnings.append(f'Phase {pid}: invalid item_type "{item_type}" for {item_id}, skipping')
                continue
            conn.execute(
                'INSERT INTO phase_items (phase_id, item_id, item_type) VALUES (?, ?, ?)',
                (pid, item_id, item_type)
            )
            item_count += 1

    conn.commit()
    conn.close()

    return phase_count, item_count, warnings


def main():
    if len(sys.argv) < 2:
        print('Usage: insert-phases.py <db_path> [json_file]', file=sys.stderr)
        sys.exit(1)

    db_path = sys.argv[1]

    if len(sys.argv) >= 3:
        json_path = sys.argv[2]
        with open(json_path) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    if not isinstance(data, list):
        print('ERROR: expected a JSON array of phase objects', file=sys.stderr)
        sys.exit(1)

    phase_count, item_count, warnings = insert_phases(db_path, data)

    print(f'Inserted {phase_count} phases, {item_count} phase items')

    if warnings:
        print()
        print(f'WARNINGS ({len(warnings)}):')
        for w in warnings:
            print(f'  ! {w}')
        sys.exit(1)


if __name__ == '__main__':
    main()
