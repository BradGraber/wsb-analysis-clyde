"""Database connection manager with FK enforcement and WAL mode."""

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator


@contextmanager
def get_connection(db_path: str = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that yields an SQLite connection with FK enforcement and WAL mode.

    Args:
        db_path: Path to the SQLite database file. If None, reads from DB_PATH
                 environment variable, falling back to './data/wsb.db'.

    Yields:
        sqlite3.Connection: Database connection with foreign keys enabled,
                           WAL mode active, and row_factory set to sqlite3.Row.

    Example:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals")
            rows = cursor.fetchall()
    """
    if db_path is None:
        db_path = os.environ.get('DB_PATH', './data/wsb.db')

    conn = None
    try:
        # Connect with cross-thread compatibility
        conn = sqlite3.connect(db_path, check_same_thread=False)

        # Enable dict-like row access
        conn.row_factory = sqlite3.Row

        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")

        # Verify and set WAL mode
        conn.execute("PRAGMA journal_mode = WAL")

        yield conn

    finally:
        if conn is not None:
            conn.close()


def get_config(key: str, db_path: str = None) -> str:
    """
    Retrieve a configuration value from the system_config table.

    Args:
        key: The configuration key to look up.
        db_path: Path to the SQLite database file. If None, reads from DB_PATH
                 environment variable, falling back to './data/wsb.db'.

    Returns:
        str: The configuration value for the given key.

    Raises:
        KeyError: If the configuration key does not exist in the database.

    Example:
        phase = get_config('phase')
        min_confidence = get_config('quality_min_confidence')
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
        row = cursor.fetchone()

        if row is None:
            raise KeyError(f"Config key not found: {key}")

        return row['value']
