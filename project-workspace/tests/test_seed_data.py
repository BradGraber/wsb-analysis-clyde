"""
Tests for story-007-004: Seed Test Data Script

These tests verify the seed data script:
- Creates completed analysis runs
- Populates 4 portfolios with positions
- Creates 10+ signals across tickers
- Creates 8+ positions (mix of open/closed, stock/options)
- Creates position_exits with 4+ exit_reason types
- Creates evaluation periods
- Creates author, comment, price_history records
- Is idempotent
"""

import pytest
import sqlite3
import os
import sys
from pathlib import Path


# Add project-workspace to path so scripts.seed_data can be imported
_PROJECT_DIR = Path(__file__).parent.parent
_SCRIPTS_DIR = _PROJECT_DIR / "scripts"


def _run_seed(db_path):
    """Run all seed functions against the given database."""
    sys.path.insert(0, str(_PROJECT_DIR))
    try:
        from scripts.seed_data import (
            connect_db, seed_authors, seed_analysis_runs, seed_reddit_posts,
            seed_signals, seed_positions, seed_position_exits, seed_comments,
            seed_signal_comments, seed_comment_tickers, seed_evaluation_periods,
            seed_price_history,
        )
    except ImportError:
        pytest.skip("Seed data script not available yet")
    finally:
        sys.path.pop(0)

    os.environ['DB_PATH'] = db_path
    conn = connect_db(db_path)
    seed_authors(conn)
    run_ids = seed_analysis_runs(conn)
    post_ids = seed_reddit_posts(conn)
    signal_ids = seed_signals(conn)
    closed_positions = seed_positions(conn, signal_ids)
    seed_position_exits(conn, closed_positions)
    comment_ids = seed_comments(conn, run_ids, post_ids)
    seed_signal_comments(conn, signal_ids, comment_ids)
    seed_comment_tickers(conn, comment_ids)
    seed_evaluation_periods(conn)
    seed_price_history(conn)
    conn.close()


@pytest.fixture
def seeded_test_db(temp_db_path):
    """Provide a database with schema, base seed, and test seed data loaded."""
    from tests.conftest import SCHEMA_SQL_PATH, SEED_SQL_PATH, _load_schema, _load_seed

    conn = sqlite3.connect(temp_db_path)
    conn.row_factory = sqlite3.Row
    if SCHEMA_SQL_PATH.exists():
        _load_schema(conn)
    if SEED_SQL_PATH.exists():
        _load_seed(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()

    _run_seed(temp_db_path)
    return temp_db_path


class TestSeedDataScript:
    """Verify seed data script exists and runs."""

    def test_seed_data_script_exists(self):
        """Seed data script should exist."""
        assert (_SCRIPTS_DIR / "seed_data.py").exists(), \
            "scripts/seed_data.py should exist"

    def test_seed_data_runs_without_errors(self, seeded_test_db):
        """Seed data script should run without errors on initialized database."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals")
        count = cursor.fetchone()[0]
        conn.close()
        assert count > 0, "Seed data should have created records"


class TestAnalysisRunsSeeding:
    """Verify analysis runs are created."""

    def test_creates_analysis_runs(self, seeded_test_db):
        """Should create at least 2 analysis runs with varied statuses."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM analysis_runs")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT status) FROM analysis_runs")
        statuses = cursor.fetchone()[0]
        conn.close()

        assert total >= 2, f"Should create at least 2 analysis runs, found {total}"
        assert statuses >= 2, f"Should have at least 2 different statuses, found {statuses}"


class TestSignalsSeeding:
    """Verify signals are created."""

    def test_creates_10_plus_signals(self, seeded_test_db):
        """Should create 10+ signals."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals")
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 10, f"Should create at least 10 signals, found {count}"

    def test_signals_across_multiple_tickers(self, seeded_test_db):
        """Signals should span multiple tickers."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT ticker) FROM signals")
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 3, f"Signals should span at least 3 tickers, found {count}"

    def test_signals_have_both_types(self, seeded_test_db):
        """Should create both quality and consensus signals."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT signal_type) FROM signals")
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 2, "Should create both quality and consensus signals"


class TestPositionsSeeding:
    """Verify positions are created."""

    def test_creates_8_plus_positions(self, seeded_test_db):
        """Should create 8+ positions."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM positions")
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 8, f"Should create at least 8 positions, found {count}"

    def test_positions_include_open_and_closed(self, seeded_test_db):
        """Should create mix of open and closed positions."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM positions WHERE status = 'open'")
        open_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM positions WHERE status = 'closed'")
        closed_count = cursor.fetchone()[0]
        conn.close()

        assert open_count > 0, "Should create some open positions"
        assert closed_count > 0, "Should create some closed positions"

    def test_positions_include_stocks_and_options(self, seeded_test_db):
        """Should create mix of stock and option positions."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT instrument_type) FROM positions")
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 2, "Should create both stock and option positions"


class TestPositionExitsSeeding:
    """Verify position_exits are created."""

    def test_creates_position_exits(self, seeded_test_db):
        """Should create position_exits for closed positions."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM position_exits")
        count = cursor.fetchone()[0]
        conn.close()

        assert count > 0, "Should create position_exits for closed positions"

    def test_position_exits_have_varied_reasons(self, seeded_test_db):
        """position_exits should have at least 4 different exit_reason types."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT exit_reason) FROM position_exits")
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 4, \
            f"Should have at least 4 different exit reasons, found {count}"


class TestEvaluationPeriodsSeeding:
    """Verify evaluation periods are created."""

    def test_creates_evaluation_periods(self, seeded_test_db):
        """Should create at least 1 evaluation period per portfolio."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM evaluation_periods")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT portfolio_id) FROM evaluation_periods")
        portfolios = cursor.fetchone()[0]
        conn.close()

        assert count >= 4, f"Should create at least 4 evaluation periods, found {count}"
        assert portfolios >= 4, \
            f"Should cover at least 4 portfolios, found {portfolios}"


class TestAdditionalSeeding:
    """Verify additional entity tables are seeded."""

    def test_creates_authors(self, seeded_test_db):
        """Should create author records."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM authors")
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 5, f"Should create at least 5 authors, found {count}"

    def test_creates_comments(self, seeded_test_db):
        """Should create comments with AI annotations."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM comments")
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 10, f"Should create at least 10 comments, found {count}"

    def test_creates_price_history(self, seeded_test_db):
        """Should create price_history records for sparklines."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM price_history")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT ticker) FROM price_history")
        tickers = cursor.fetchone()[0]
        conn.close()

        assert count >= 50, f"Should create at least 50 price records, found {count}"
        assert tickers >= 5, f"Should cover at least 5 tickers, found {tickers}"


class TestPortfoliosPopulated:
    """Verify all 4 portfolios have positions."""

    def test_all_4_portfolios_have_positions(self, seeded_test_db):
        """All 4 portfolios should have positions."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(DISTINCT portfolio_id) FROM positions"
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 4, \
            f"At least 4 portfolios should have positions, found {count}"


class TestSeedIdempotence:
    """Verify seed data script is idempotent."""

    def test_seed_data_is_idempotent(self, seeded_test_db):
        """Running seed twice should not create duplicate records."""
        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals")
        first_count = cursor.fetchone()[0]
        conn.close()

        # Seed again
        _run_seed(seeded_test_db)

        conn = sqlite3.connect(seeded_test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals")
        second_count = cursor.fetchone()[0]
        conn.close()

        assert second_count == first_count, \
            f"Idempotent seed should not create duplicates: {first_count} -> {second_count}"
