"""
Tests for story-001-002: Seed Configuration Data with 34 System Config Entries

These tests verify that the configuration seeding logic:
- Creates all 34 system_config entries with correct keys
- Sets appropriate default values for each config type
- Ensures confidence weights sum to exactly 1.0
- Sets system_start_date to current date
- Sets phase to 'paper_trading'
- Is idempotent (can be run multiple times safely)
"""

import pytest
import sqlite3
from pathlib import Path
from datetime import date


class TestConfigSeeding:
    """Verify all 34 config entries are created with correct defaults."""

    def test_all_34_config_keys_exist(self, seeded_db, expected_config_keys):
        """All 34 system_config entries must be created."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT key FROM system_config ORDER BY key")
        actual_keys = [row[0] for row in cursor.fetchall()]

        for key in expected_config_keys:
            assert key in actual_keys, f"Config key {key} not found"

        assert len(actual_keys) >= len(expected_config_keys), \
            f"Expected at least {len(expected_config_keys)} config keys, found {len(actual_keys)}"

    def test_system_start_date_is_current_date(self, seeded_db):
        """system_start_date should be set to current date."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT value FROM system_config WHERE key = 'system_start_date'")
        result = cursor.fetchone()

        assert result is not None, "system_start_date not found"

        stored_date = date.fromisoformat(result[0])
        today = date.today()
        days_diff = abs((today - stored_date).days)

        assert days_diff <= 7, \
            f"system_start_date {stored_date} is more than 7 days from today {today}"

    def test_phase_is_paper_trading(self, seeded_db):
        """phase should be set to 'paper_trading'."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT value FROM system_config WHERE key = 'phase'")
        result = cursor.fetchone()

        assert result is not None, "phase config not found"
        assert result[0] == 'paper_trading', \
            f"Expected phase='paper_trading', got '{result[0]}'"


class TestConfidenceWeights:
    """Verify confidence weights sum to exactly 1.0."""

    def test_confidence_weights_sum_to_one(self, seeded_db):
        """The four confidence weights must sum to exactly 1.0."""
        cursor = seeded_db.cursor()
        cursor.execute("""
            SELECT value FROM system_config
            WHERE key IN (
                'confidence_weight_volume',
                'confidence_weight_alignment',
                'confidence_weight_ai_confidence',
                'confidence_weight_author_trust'
            )
        """)
        weights = [float(row[0]) for row in cursor.fetchall()]

        assert len(weights) == 4, "Expected 4 confidence weights"

        weight_sum = sum(weights)
        assert abs(weight_sum - 1.0) < 0.0001, \
            f"Confidence weights sum to {weight_sum}, expected 1.0"


class TestSignalThresholdDefaults:
    """Verify signal detection threshold defaults."""

    def test_quality_signal_thresholds(self, seeded_db):
        """Quality signal thresholds have correct defaults."""
        cursor = seeded_db.cursor()

        cursor.execute("SELECT value FROM system_config WHERE key = 'quality_min_users'")
        result = cursor.fetchone()
        assert result is not None
        assert int(result[0]) == 2, "quality_min_users should default to 2"

        cursor.execute("SELECT value FROM system_config WHERE key = 'quality_min_confidence'")
        result = cursor.fetchone()
        assert result is not None
        assert float(result[0]) == 0.6, "quality_min_confidence should default to 0.6"

    def test_consensus_signal_thresholds(self, seeded_db):
        """Consensus signal thresholds have correct defaults."""
        cursor = seeded_db.cursor()

        cursor.execute("SELECT value FROM system_config WHERE key = 'consensus_min_comments'")
        result = cursor.fetchone()
        assert result is not None
        assert int(result[0]) == 30, "consensus_min_comments should default to 30"

        cursor.execute("SELECT value FROM system_config WHERE key = 'consensus_min_users'")
        result = cursor.fetchone()
        assert result is not None
        assert int(result[0]) == 8, "consensus_min_users should default to 8"

        cursor.execute("SELECT value FROM system_config WHERE key = 'consensus_min_alignment'")
        result = cursor.fetchone()
        assert result is not None
        assert float(result[0]) == 0.7, "consensus_min_alignment should default to 0.7"


class TestStockExitDefaults:
    """Verify stock exit strategy defaults match PRD specifications."""

    def test_stock_exit_percentages(self, seeded_db):
        """Stock exit percentage thresholds have correct defaults."""
        cursor = seeded_db.cursor()

        expected = {
            'stock_stop_loss_pct': -0.10,
            'stock_take_profit_pct': 0.15,
            'stock_trailing_stop_pct': 0.07,
            'stock_breakeven_trigger_pct': 0.05,
            'stock_time_stop_base_min_gain': 0.05,
            'stock_take_profit_exit_pct': 0.50
        }

        for key, expected_value in expected.items():
            cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
            result = cursor.fetchone()
            assert result is not None, f"{key} not found"
            assert float(result[0]) == expected_value, \
                f"{key} should be {expected_value}, got {result[0]}"

    def test_stock_exit_day_thresholds(self, seeded_db):
        """Stock exit day thresholds have correct defaults."""
        cursor = seeded_db.cursor()

        expected = {
            'stock_breakeven_min_days': 5,
            'stock_time_stop_base_days': 5,
            'stock_time_stop_extended_days': 7,
            'stock_time_stop_max_days': 10
        }

        for key, expected_value in expected.items():
            cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
            result = cursor.fetchone()
            assert result is not None, f"{key} not found"
            assert int(result[0]) == expected_value, \
                f"{key} should be {expected_value}, got {result[0]}"


class TestOptionsExitDefaults:
    """Verify options exit strategy defaults match PRD specifications."""

    def test_options_exit_percentages(self, seeded_db):
        """Options exit percentage thresholds have correct defaults."""
        cursor = seeded_db.cursor()

        expected = {
            'option_stop_loss_pct': -0.50,
            'option_take_profit_pct': 1.00,
            'option_trailing_stop_pct': 0.30,
            'option_take_profit_exit_pct': 0.50
        }

        for key, expected_value in expected.items():
            cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
            result = cursor.fetchone()
            assert result is not None, f"{key} not found"
            assert float(result[0]) == expected_value, \
                f"{key} should be {expected_value}, got {result[0]}"

    def test_options_exit_day_and_dte_thresholds(self, seeded_db):
        """Options exit day and DTE thresholds have correct defaults."""
        cursor = seeded_db.cursor()

        expected = {
            'option_time_stop_days': 10,
            'option_expiration_protection_dte': 2
        }

        for key, expected_value in expected.items():
            cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
            result = cursor.fetchone()
            assert result is not None, f"{key} not found"
            assert int(result[0]) == expected_value, \
                f"{key} should be {expected_value}, got {result[0]}"


class TestPositionManagement:
    """Verify position management defaults."""

    def test_signal_min_confidence(self, seeded_db):
        """signal_min_confidence should default to 0.50."""
        cursor = seeded_db.cursor()
        cursor.execute("SELECT value FROM system_config WHERE key = 'signal_min_confidence'")
        result = cursor.fetchone()

        assert result is not None, "signal_min_confidence not found"
        assert float(result[0]) == 0.50, \
            f"signal_min_confidence should be 0.50, got {result[0]}"


class TestSeedIdempotence:
    """Verify seed script can be run multiple times safely."""

    def test_seed_config_is_idempotent(self, temp_db_path):
        """Running seed.sql multiple times should not duplicate entries."""
        db_dir = Path(__file__).parent.parent / "src" / "backend" / "db"
        schema_path = db_dir / "schema.sql"
        seed_path = db_dir / "seed.sql"

        if not schema_path.exists() or not seed_path.exists():
            pytest.skip("SQL files not available yet")

        conn = sqlite3.connect(temp_db_path)
        conn.executescript(schema_path.read_text())
        conn.executescript(seed_path.read_text())
        # Run seed again
        conn.executescript(seed_path.read_text())

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM system_config")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 34, \
            f"After running seed twice, expected 34 entries, got {count}"
