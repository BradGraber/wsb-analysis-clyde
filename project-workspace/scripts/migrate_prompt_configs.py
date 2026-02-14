#!/usr/bin/env python3
"""Migration: Add prompt_configs and tuning_runs tables, seed default config.

Applies schema changes to an existing wsb.db:
1. Creates prompt_configs table
2. Creates tuning_runs table
3. Adds prompt_config_id column to comments table
4. Seeds default prompt config from current SYSTEM_PROMPT

Safe to run multiple times (uses IF NOT EXISTS / try-except for ALTER).

Usage:
    python scripts/migrate_prompt_configs.py [--db-path ./data/wsb.db]
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prompts import SYSTEM_PROMPT


def migrate(db_path: str):
    """Run the migration."""
    if not os.path.exists(db_path):
        print(f"Error: Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # 1. Create prompt_configs table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prompt_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            system_prompt TEXT NOT NULL,
            provider VARCHAR(20) NOT NULL DEFAULT 'openai',
            api_base_url VARCHAR(500),
            model VARCHAR(50) NOT NULL DEFAULT 'gpt-4o-mini',
            temperature REAL NOT NULL DEFAULT 0.3,
            top_p REAL NOT NULL DEFAULT 1.0,
            max_tokens INT NOT NULL DEFAULT 500,
            top_k INT,
            frequency_penalty REAL,
            presence_penalty REAL,
            response_format VARCHAR(20),
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            is_fine_tuned BOOLEAN NOT NULL DEFAULT FALSE,
            base_model VARCHAR(50),
            fine_tune_job_id VARCHAR(100),
            fine_tune_suffix VARCHAR(100),
            created_at TIMESTAMP DEFAULT (datetime('now'))
        )
    """)
    print("  prompt_configs table: OK")

    # 2. Create tuning_runs table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tuning_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id INT NOT NULL,
            prompt_config_id INT NOT NULL,
            market_context_used TEXT,
            user_prompt TEXT,
            sentiment VARCHAR(10),
            ai_confidence FLOAT,
            sarcasm_detected BOOLEAN,
            has_reasoning BOOLEAN,
            reasoning_summary TEXT,
            tickers TEXT,
            ticker_sentiments TEXT,
            prompt_tokens INT,
            completion_tokens INT,
            cost REAL,
            mode VARCHAR(20),
            label VARCHAR(20),
            tag VARCHAR(100),
            created_at TIMESTAMP DEFAULT (datetime('now')),
            FOREIGN KEY (comment_id) REFERENCES comments(id),
            FOREIGN KEY (prompt_config_id) REFERENCES prompt_configs(id)
        )
    """)
    print("  tuning_runs table: OK")

    # 3. Add prompt_config_id to comments (safe if already exists)
    try:
        conn.execute(
            "ALTER TABLE comments ADD COLUMN prompt_config_id INT REFERENCES prompt_configs(id)"
        )
        print("  comments.prompt_config_id column: added")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("  comments.prompt_config_id column: already exists")
        else:
            raise

    # 4. Seed default prompt config (only if none exists)
    existing = conn.execute(
        "SELECT id FROM prompt_configs WHERE is_default = 1"
    ).fetchone()

    if existing:
        print(f"  Default prompt config: already exists (id={existing[0]})")
    else:
        conn.execute("""
            INSERT INTO prompt_configs (name, system_prompt, provider, model,
                temperature, top_p, max_tokens, response_format, is_default)
            VALUES (?, ?, 'openai', 'gpt-4o-mini', 0.3, 1.0, 500, 'json_object', 1)
        """, ("default", SYSTEM_PROMPT))
        print("  Default prompt config: seeded")

    conn.commit()
    conn.close()
    print("\nMigration complete.")


def main():
    parser = argparse.ArgumentParser(description="Migrate DB for prompt configs + tuning runs")
    parser.add_argument("--db-path", default=None,
                        help="SQLite database path (default: $DB_PATH or ./data/wsb.db)")
    args = parser.parse_args()

    db_path = args.db_path or os.environ.get("DB_PATH", "./data/wsb.db")
    print(f"Migrating {db_path}...")
    migrate(db_path)


if __name__ == "__main__":
    main()
