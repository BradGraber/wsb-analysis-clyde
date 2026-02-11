"""
Shared pytest fixtures for Phase A (Foundation) tests.

These fixtures provide test databases, schema setup, and common test data.
All tests are behavioral - they verify what the code should do, not how it does it.
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from datetime import date

# Paths to SQL files relative to the project-workspace directory
_DB_DIR = Path(__file__).parent.parent / "src" / "backend" / "db"
SCHEMA_SQL_PATH = _DB_DIR / "schema.sql"
SEED_SQL_PATH = _DB_DIR / "seed.sql"


def _exec_sql_file(conn, path):
    """Execute a .sql file on an open connection, handling PRAGMAs separately."""
    sql = path.read_text()
    # executescript auto-commits and resets per-connection PRAGMAs, so run them separately
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    lines = [line for line in sql.splitlines()
             if not line.strip().upper().startswith("PRAGMA")]
    conn.executescript("\n".join(lines))


def _load_schema(conn):
    """Execute schema.sql on an open connection."""
    _exec_sql_file(conn, SCHEMA_SQL_PATH)


def _load_seed(conn):
    """Execute seed.sql on an open connection (schema must already be loaded)."""
    _exec_sql_file(conn, SEED_SQL_PATH)


@pytest.fixture
def temp_db_path():
    """Provide a temporary database file path that is cleaned up after test."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)
    # Also cleanup WAL files if they exist
    for suffix in ['-wal', '-shm']:
        wal_file = db_path + suffix
        if os.path.exists(wal_file):
            os.unlink(wal_file)


@pytest.fixture
def db_connection(temp_db_path):
    """Provide a raw SQLite connection to a temporary database."""
    conn = sqlite3.connect(temp_db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def schema_initialized_db(temp_db_path):
    """
    Provide a database with schema initialized by executing schema.sql.

    Loads the SQL file directly and runs PRAGMAs on the returned connection.
    """
    conn = sqlite3.connect(temp_db_path)
    conn.row_factory = sqlite3.Row
    if SCHEMA_SQL_PATH.exists():
        _load_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def seeded_db(temp_db_path):
    """
    Provide a database with schema, config, and portfolios seeded.

    Loads schema.sql then seed.sql directly via sqlite3.
    """
    conn = sqlite3.connect(temp_db_path)
    conn.row_factory = sqlite3.Row
    if SCHEMA_SQL_PATH.exists():
        _load_schema(conn)
    if SEED_SQL_PATH.exists():
        _load_seed(conn)
    # Re-enable foreign keys after executescript resets them
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def expected_tables():
    """Return list of all 16 expected table names."""
    return [
        'system_config',
        'authors',
        'reddit_posts',
        'signals',
        'portfolios',
        'positions',
        'price_history',
        'evaluation_periods',
        'comments',
        'analysis_runs',
        'signal_comments',
        'comment_tickers',
        'position_exits',
        'predictions',
        'prediction_outcomes',
        'prediction_exits'
    ]


@pytest.fixture
def expected_config_keys():
    """Return list of all 34 expected system_config keys."""
    return [
        # System state (2)
        'system_start_date',
        'phase',
        # Signal threshold (5)
        'quality_min_users',
        'quality_min_confidence',
        'consensus_min_comments',
        'consensus_min_users',
        'consensus_min_alignment',
        # Confidence weights (4) - must sum to 1.0
        'confidence_weight_volume',
        'confidence_weight_alignment',
        'confidence_weight_ai_confidence',
        'confidence_weight_author_trust',
        # Author trust (6)
        'trust_weight_quality',
        'trust_weight_accuracy',
        'trust_weight_tenure',
        'trust_default_accuracy',
        'trust_tenure_saturation_days',
        'accuracy_ema_weight',
        # Stock exit (10)
        'stock_stop_loss_pct',
        'stock_take_profit_pct',
        'stock_trailing_stop_pct',
        'stock_breakeven_trigger_pct',
        'stock_breakeven_min_days',
        'stock_time_stop_base_days',
        'stock_time_stop_base_min_gain',
        'stock_time_stop_extended_days',
        'stock_time_stop_max_days',
        'stock_take_profit_exit_pct',
        # Options exit (6)
        'option_stop_loss_pct',
        'option_take_profit_pct',
        'option_trailing_stop_pct',
        'option_time_stop_days',
        'option_expiration_protection_dte',
        'option_take_profit_exit_pct',
        # Position management (1)
        'signal_min_confidence'
    ]


@pytest.fixture
def expected_portfolios():
    """Return expected portfolio configurations."""
    return [
        {'name': 'stocks_quality', 'instrument_type': 'stock', 'signal_type': 'quality'},
        {'name': 'stocks_consensus', 'instrument_type': 'stock', 'signal_type': 'consensus'},
        {'name': 'options_quality', 'instrument_type': 'option', 'signal_type': 'quality'},
        {'name': 'options_consensus', 'instrument_type': 'option', 'signal_type': 'consensus'}
    ]


@pytest.fixture
def test_client(temp_db_path):
    """Provide a FastAPI TestClient backed by a temporary schema-initialized database.

    Sets DB_PATH env var so the app lifespan connects to the temp database.
    Uses context manager to ensure lifespan startup/shutdown run properly.
    """
    try:
        from src.api.app import app
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI app not available yet")

    old_db_path = os.environ.get('DB_PATH')
    os.environ['DB_PATH'] = temp_db_path

    # Initialize schema in the temp DB
    conn = sqlite3.connect(temp_db_path)
    conn.row_factory = sqlite3.Row
    if SCHEMA_SQL_PATH.exists():
        _load_schema(conn)
    if SEED_SQL_PATH.exists():
        _load_seed(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()

    with TestClient(app) as client:
        yield client

    # Restore original DB_PATH
    if old_db_path is not None:
        os.environ['DB_PATH'] = old_db_path
    elif 'DB_PATH' in os.environ:
        del os.environ['DB_PATH']


@pytest.fixture
def mock_schwab_token():
    """Return a mock Schwab token structure for testing."""
    from datetime import datetime, timedelta

    now = datetime.now()
    return {
        'access_token': 'mock_access_token_12345',
        'refresh_token': 'mock_refresh_token_67890',
        'expires_at': (now + timedelta(minutes=30)).isoformat(),
        'refresh_expires_at': (now + timedelta(days=7)).isoformat()
    }
