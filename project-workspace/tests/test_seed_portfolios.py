"""
Tests for story-001-003: Initialize Portfolio Records with Four Portfolios at $100k Each

These tests verify that the portfolio seeding logic:
- Creates exactly 4 portfolios with correct names
- Sets instrument_type to 'stock' or 'option' (not plural)
- Sets signal_type to 'quality' or 'consensus'
- Initializes each portfolio with $100,000 starting capital
- Sets current_value and cash_available to $100,000
- Is idempotent (can be run multiple times safely)
"""

import pytest


class TestPortfolioSeeding:
    """Verify all 4 portfolios are created with correct configuration."""

    def test_exactly_four_portfolios_created(self, seeded_db):
        """SELECT COUNT(*) FROM portfolios must return exactly 4."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT COUNT(*) FROM portfolios")
        count = cursor.fetchone()[0]

        assert count == 4, f"Expected exactly 4 portfolios, found {count}"

    def test_portfolio_names_correct(self, seeded_db):
        """All four portfolio names must match expected values."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT name FROM portfolios ORDER BY name")
        names = [row[0] for row in cursor.fetchall()]

        expected_names = [
            'options_consensus',
            'options_quality',
            'stocks_consensus',
            'stocks_quality'
        ]

        assert sorted(names) == sorted(expected_names), \
            f"Expected portfolios {expected_names}, got {names}"

    def test_instrument_type_values(self, seeded_db):
        """instrument_type must be 'stock' or 'option' (singular, not plural)."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT name, instrument_type FROM portfolios")
        portfolios = cursor.fetchall()

        for name, instrument_type in portfolios:
            assert instrument_type in ['stock', 'option'], \
                f"Portfolio {name} has invalid instrument_type: {instrument_type} " \
                f"(expected 'stock' or 'option')"

            # Ensure it's not plural
            assert instrument_type not in ['stocks', 'options'], \
                f"Portfolio {name} has plural instrument_type: {instrument_type}"

    def test_signal_type_values(self, seeded_db):
        """signal_type must be 'quality' or 'consensus'."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT name, signal_type FROM portfolios")
        portfolios = cursor.fetchall()

        for name, signal_type in portfolios:
            assert signal_type in ['quality', 'consensus'], \
                f"Portfolio {name} has invalid signal_type: {signal_type}"

    def test_correct_instrument_and_signal_combinations(self, seeded_db, expected_portfolios):
        """Each portfolio must have the correct instrument_type and signal_type combination."""
        cursor = seeded_db.cursor()
        cursor.execute("""
            SELECT name, instrument_type, signal_type
            FROM portfolios
            ORDER BY name
        """)
        actual = [{'name': row[0], 'instrument_type': row[1], 'signal_type': row[2]}
                  for row in cursor.fetchall()]

        for expected in expected_portfolios:
            found = False
            for portfolio in actual:
                if (portfolio['name'] == expected['name'] and
                    portfolio['instrument_type'] == expected['instrument_type'] and
                    portfolio['signal_type'] == expected['signal_type']):
                    found = True
                    break

            assert found, \
                f"Expected portfolio not found: {expected}"


class TestPortfolioCapital:
    """Verify all portfolios start with $100,000."""

    def test_starting_capital_is_100k(self, seeded_db):
        """All portfolios must have starting_capital = 100000."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT name, starting_capital FROM portfolios")
        portfolios = cursor.fetchall()

        for name, starting_capital in portfolios:
            assert starting_capital == 100000, \
                f"Portfolio {name} has starting_capital {starting_capital}, expected 100000"

    def test_current_value_is_100k(self, seeded_db):
        """All portfolios must have current_value = 100000."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT name, current_value FROM portfolios")
        portfolios = cursor.fetchall()

        for name, current_value in portfolios:
            assert current_value == 100000, \
                f"Portfolio {name} has current_value {current_value}, expected 100000"

    def test_cash_available_is_100k(self, seeded_db):
        """All portfolios must have cash_available = 100000."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT name, cash_available FROM portfolios")
        portfolios = cursor.fetchall()

        for name, cash_available in portfolios:
            assert cash_available == 100000, \
                f"Portfolio {name} has cash_available {cash_available}, expected 100000"


class TestSeedIdempotence:
    """Verify seed script can be run multiple times safely."""

    def test_seed_portfolios_is_idempotent(self, temp_db_path):
        """Running seed.sql multiple times should not duplicate portfolio entries."""
        import sqlite3
        from pathlib import Path

        db_dir = Path(__file__).parent.parent / "src" / "backend" / "db"
        schema_path = db_dir / "schema.sql"
        seed_path = db_dir / "seed.sql"

        if not schema_path.exists() or not seed_path.exists():
            pytest.skip("SQL files not available yet")

        conn = sqlite3.connect(temp_db_path)
        conn.executescript(schema_path.read_text())
        conn.executescript(seed_path.read_text())
        # Seed again
        conn.executescript(seed_path.read_text())

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM portfolios")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 4, \
            f"After running seed twice, expected 4 portfolios, got {count}"

    def test_seeded_values_unchanged_after_reseed(self, temp_db_path):
        """Re-seeding should not change existing portfolio values."""
        import sqlite3
        from pathlib import Path

        db_dir = Path(__file__).parent.parent / "src" / "backend" / "db"
        schema_path = db_dir / "schema.sql"
        seed_path = db_dir / "seed.sql"

        if not schema_path.exists() or not seed_path.exists():
            pytest.skip("SQL files not available yet")

        conn = sqlite3.connect(temp_db_path)
        conn.executescript(schema_path.read_text())
        conn.executescript(seed_path.read_text())

        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, starting_capital, current_value, cash_available
            FROM portfolios ORDER BY name
        """)
        initial_values = cursor.fetchall()

        # Seed again
        conn.executescript(seed_path.read_text())

        cursor.execute("""
            SELECT name, starting_capital, current_value, cash_available
            FROM portfolios ORDER BY name
        """)
        after_values = cursor.fetchall()
        conn.close()

        assert initial_values == after_values, \
            "Portfolio values changed after re-seeding"
