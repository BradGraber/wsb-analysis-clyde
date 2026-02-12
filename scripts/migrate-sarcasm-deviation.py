#!/usr/bin/env python3
"""
One-off migration: Remove sarcasm_detected=false from Quality signal filter
requirements in plan.db (task-004-002-01, task-004-007-01, story-004-002, story-004-007).

PRD Deviation: Product owner decided sarcasm_detected is metadata, not a gate.
See output/technical-brief.md "PRD Deviations" section.

Usage:
    python3 scripts/migrate-sarcasm-deviation.py --dry-run   # Preview changes
    python3 scripts/migrate-sarcasm-deviation.py              # Apply changes
"""

import argparse
import os
import sqlite3
import sys


def get_db_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    return os.path.join(project_root, "output", "plan.db")


def migrate(dry_run=False):
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"ERROR: {db_path} not found")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    updates = []

    # --- task-004-002-01 description ---
    row = conn.execute("SELECT description FROM tasks WHERE id = 'task-004-002-01'").fetchone()
    old_desc = row["description"]
    new_desc = old_desc.replace(
        "has_reasoning=true, sarcasm_detected=false, ai_confidence >= quality_min_confidence",
        "has_reasoning=true, ai_confidence >= quality_min_confidence"
    )
    updates.append(("task-004-002-01", "description", old_desc, new_desc,
                     "UPDATE tasks SET description = ? WHERE id = 'task-004-002-01'"))

    # --- task-004-002-01 acceptance_criteria ---
    row = conn.execute("SELECT acceptance_criteria FROM tasks WHERE id = 'task-004-002-01'").fetchone()
    old_ac = row["acceptance_criteria"]
    new_ac = old_ac.replace(
        "- [ ] Comments filtered by has_reasoning=true AND sarcasm_detected=false AND ai_confidence >= quality_min_confidence (default 0.6)",
        "- [ ] Comments filtered by has_reasoning=true AND ai_confidence >= quality_min_confidence (default 0.6); sarcasm_detected is retained as metadata, not used as a filter (see PRD Deviations in technical-brief.md)"
    )
    updates.append(("task-004-002-01", "acceptance_criteria", old_ac, new_ac,
                     "UPDATE tasks SET acceptance_criteria = ? WHERE id = 'task-004-002-01'"))

    # --- task-004-007-01 acceptance_criteria ---
    row = conn.execute("SELECT acceptance_criteria FROM tasks WHERE id = 'task-004-007-01'").fetchone()
    old_ac2 = row["acceptance_criteria"]
    new_ac2 = old_ac2.replace(
        "- [ ] Quality signal test: exactly 2 users with has_reasoning=true, sarcasm_detected=false, ai_confidence >= 0.6, unanimous direction produces a fired signal",
        "- [ ] Quality signal test: exactly 2 users with has_reasoning=true, ai_confidence >= 0.6, unanimous direction produces a fired signal (sarcasm_detected is metadata, not a filter)"
    )
    updates.append(("task-004-007-01", "acceptance_criteria", old_ac2, new_ac2,
                     "UPDATE tasks SET acceptance_criteria = ? WHERE id = 'task-004-007-01'"))

    # --- story-004-002 description ---
    row = conn.execute("SELECT description FROM stories WHERE id = 'story-004-002'").fetchone()
    old_story = row["description"]
    # Fix the description paragraph
    new_story = old_story.replace(
        "has_reasoning=true, sarcasm_detected=false, ai_confidence >= 0.6",
        "has_reasoning=true, ai_confidence >= 0.6"
    )
    # Fix the first acceptance criterion
    new_story = new_story.replace(
        "- [ ] Comments are filtered by has_reasoning=true AND sarcasm_detected=false AND ai_confidence >= quality_min_confidence (default 0.6 from system_config); a comment with ai_confidence = 0.6 exactly qualifies (inclusive boundary)",
        "- [ ] Comments are filtered by has_reasoning=true AND ai_confidence >= quality_min_confidence (default 0.6 from system_config); sarcasm_detected is retained as metadata, not used as a filter (see PRD Deviations in technical-brief.md); a comment with ai_confidence = 0.6 exactly qualifies (inclusive boundary)"
    )
    updates.append(("story-004-002", "description", old_story, new_story,
                     "UPDATE stories SET description = ? WHERE id = 'story-004-002'"))

    # --- story-004-007 description ---
    row = conn.execute("SELECT description FROM stories WHERE id = 'story-004-007'").fetchone()
    old_story2 = row["description"]
    new_story2 = old_story2.replace(
        "- [ ] Quality signal test: exactly 2 users with has_reasoning=true, sarcasm_detected=false, ai_confidence >= 0.6, unanimous direction produces a fired signal",
        "- [ ] Quality signal test: exactly 2 users with has_reasoning=true, ai_confidence >= 0.6, unanimous direction produces a fired signal (sarcasm_detected is metadata, not a filter)"
    )
    updates.append(("story-004-007", "description", old_story2, new_story2,
                     "UPDATE stories SET description = ? WHERE id = 'story-004-007'"))

    # --- Print and apply ---
    for record_id, field, old_val, new_val, sql in updates:
        changed = old_val != new_val
        status = "CHANGED" if changed else "NO CHANGE"
        print(f"\n{'='*60}")
        print(f"{record_id}.{field} [{status}]")
        if changed:
            # Show just the changed lines
            old_lines = old_val.split("\n")
            new_lines = new_val.split("\n")
            for i, (o, n) in enumerate(zip(old_lines, new_lines)):
                if o != n:
                    print(f"  - {o.strip()[:100]}")
                    print(f"  + {n.strip()[:100]}")

        if not dry_run and changed:
            conn.execute(sql, (new_val,))

    if dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN — no changes applied. Run without --dry-run to apply.")
    else:
        conn.commit()
        print(f"\n{'='*60}")
        print("Migration applied successfully.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate sarcasm deviation in plan.db")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
