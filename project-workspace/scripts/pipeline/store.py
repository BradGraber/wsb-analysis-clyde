#!/usr/bin/env python3
"""Stage 3: Store scored posts and comments to SQLite and prepare analyze input.

Reads scored data from Stage 2, creates an analysis_runs record, persists posts
and comments to the database, then writes a JSON file with the comment data
needed for the AI analysis stage.

Usage:
    python scripts/pipeline/store.py [-i data/pipeline/scored.json] [-o data/pipeline/to_analyze.json] [--db-path ./data/wsb.db]

No API keys required. Creates the database and schema if they don't exist.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def _load_dotenv():
    """Load .env file into os.environ if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

from src.storage import store_posts_and_comments
from src.prompts import format_parent_chain


def ensure_db(db_path: str) -> sqlite3.Connection:
    """Open (and optionally initialize) the database."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    # Check if schema exists
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row["name"] for row in tables}

    if "analysis_runs" not in table_names:
        print("  Initializing database schema...")
        schema_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "src", "backend", "db", "schema.sql"
        )
        with open(schema_path) as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        # Re-enable FKs after executescript resets them
        conn.execute("PRAGMA foreign_keys = ON")

    return conn


def create_analysis_run(conn: sqlite3.Connection) -> int:
    """Create a new analysis_runs record and return its ID."""
    cursor = conn.execute(
        "INSERT INTO analysis_runs (status, started_at) VALUES (?, datetime('now'))",
        ("in_progress",)
    )
    conn.commit()
    return cursor.lastrowid


def main():
    parser = argparse.ArgumentParser(
        description="Stage 3: Store scored posts/comments to SQLite"
    )
    parser.add_argument("-i", "--input", default="data/pipeline/scored.json", help="Input JSON from score stage (default: data/pipeline/scored.json)")
    parser.add_argument("-o", "--output", default="data/pipeline/to_analyze.json", help="Output JSON for analyze stage (default: data/pipeline/to_analyze.json)")
    parser.add_argument("--db-path", default=None, help="SQLite database path (default: $DB_PATH or ./data/wsb.db)")
    args = parser.parse_args()

    db_path = args.db_path or os.environ.get("DB_PATH", "./data/wsb.db")

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        print("Run score.py first to create it.")
        sys.exit(1)

    with open(args.input) as f:
        data = json.load(f)

    posts = data["posts"]
    total_comments = sum(len(p.get("comments", [])) for p in posts)

    print(f"Loaded {len(posts)} posts with {total_comments} comments from {args.input}")

    # Open/create database
    print(f"  Database: {db_path}")
    conn = ensure_db(db_path)

    # Create analysis run
    run_id = create_analysis_run(conn)
    print(f"  Created analysis run #{run_id}")

    # Store posts and comments
    print(f"  Storing {len(posts)} posts and {total_comments} comments...")
    store_posts_and_comments(conn, run_id, posts)

    # Build analyze input: look up DB post_ids and format for AI stage
    analyze_comments = []
    for post in posts:
        # Look up the DB post_id for this reddit_id
        row = conn.execute(
            "SELECT id FROM reddit_posts WHERE reddit_id = ?",
            (post["reddit_id"],)
        ).fetchone()

        if not row:
            print(f"  Warning: post {post['reddit_id']} not found in DB after store")
            continue

        post_db_id = row["id"]

        for comment in post.get("comments", []):
            parent_chain_formatted = format_parent_chain(comment.get("parent_chain", []))

            analyze_comments.append({
                "reddit_id": comment["reddit_id"],
                "body": comment["body"],
                "author": comment["author"],
                "author_trust_score": comment.get("author_trust_score", 0.5),
                "post_id": post["reddit_id"],
                "post_db_id": post_db_id,
                "post_title": post["title"],
                "image_description": post.get("image_analysis"),
                "parent_chain_formatted": parent_chain_formatted,
                "score": comment.get("score", 0),
                "depth": comment.get("depth", 0),
                "created_utc": comment.get("created_utc", 0),
                "prioritization_score": comment.get("priority_score", 0.0),
            })

    conn.close()

    # Write analyze input JSON
    output_data = {
        "metadata": {
            "run_id": run_id,
            "comment_count": len(analyze_comments),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "db_path": db_path,
        },
        "comments": analyze_comments,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"\nCreated run #{run_id}, stored {len(posts)} posts + {total_comments} comments")
    print(f"  Analyze input: {args.output} ({len(analyze_comments)} comments ready for AI)")


if __name__ == "__main__":
    main()
