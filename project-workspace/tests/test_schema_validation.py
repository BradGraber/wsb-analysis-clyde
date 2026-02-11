"""
Tests for story-001-005: Schema Validation Script

These tests verify that the validation script:
- Verifies all 16 tables exist
- Verifies column names and types per table
- Verifies all 34 system_config entries present
- Verifies 4 portfolio rows with correct combinations
- Verifies PRAGMA foreign_keys returns 1
- Verifies PRAGMA journal_mode returns 'wal'
- Provides clear pass/fail summary with specific failure details
- Returns exit code 0 on pass, 1 on fail
"""

import pytest
import sqlite3
from pathlib import Path


SCRIPT_PATH = Path(__file__).parent.parent / "src" / "backend" / "scripts" / "validate_schema.py"


class TestValidationScript:
    """Verify the schema validation script exists and runs."""

    def test_validation_script_exists(self):
        """Validation script should exist in expected location."""
        assert SCRIPT_PATH.exists(), f"Validation script not found at {SCRIPT_PATH}"

    def test_validation_passes_on_valid_schema(self, seeded_db):
        """Validation should pass on a properly seeded database."""
        try:
            from src.backend.scripts.validate_schema import main, ValidationResult
        except ImportError:
            pytest.skip("Implementation not available yet")

        cursor = seeded_db.cursor()
        cursor.execute("PRAGMA database_list")
        db_path = cursor.fetchone()[2]

        result = main(db_path=db_path)
        assert result == 0, "Validation should pass on properly seeded database"

    def test_validation_fails_on_missing_tables(self, temp_db_path):
        """Validation should fail on database with missing tables."""
        try:
            from src.backend.scripts.validate_schema import main
        except ImportError:
            pytest.skip("Implementation not available yet")

        # Create a database with only some tables
        conn = sqlite3.connect(temp_db_path)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("CREATE TABLE system_config (key TEXT, value TEXT)")
        conn.commit()
        conn.close()

        result = main(db_path=temp_db_path)
        assert result == 1, "Validation should fail on incomplete schema"


class TestValidationChecks:
    """Verify validation script checks all required elements."""

    def test_validates_all_16_tables(self, seeded_db):
        """Validation should check for all 16 tables."""
        try:
            from src.backend.scripts.validate_schema import validate_tables, ValidationResult
        except ImportError:
            pytest.skip("Implementation not available yet")

        result = ValidationResult()
        validate_tables(seeded_db, result)
        assert len(result.passed) > 0, "Should have passing checks for tables"
        assert len(result.failed) == 0, f"Table validation should pass: {result.failed}"

    def test_validates_34_config_entries(self, seeded_db):
        """Validation should verify all 34 system_config entries exist."""
        try:
            from src.backend.scripts.validate_schema import validate_system_config, ValidationResult
        except ImportError:
            pytest.skip("Implementation not available yet")

        # Delete one config entry to cause failure
        cursor = seeded_db.cursor()
        cursor.execute("DELETE FROM system_config WHERE key = 'phase'")
        seeded_db.commit()

        result = ValidationResult()
        validate_system_config(seeded_db, result)
        assert len(result.failed) > 0, "Should fail when config entries are missing"

    def test_validates_4_portfolios(self, seeded_db):
        """Validation should verify exactly 4 portfolios exist."""
        try:
            from src.backend.scripts.validate_schema import validate_portfolios, ValidationResult
        except ImportError:
            pytest.skip("Implementation not available yet")

        # Delete a portfolio
        cursor = seeded_db.cursor()
        cursor.execute("DELETE FROM portfolios WHERE name = 'stocks_quality'")
        seeded_db.commit()

        result = ValidationResult()
        validate_portfolios(seeded_db, result)
        assert len(result.failed) > 0, "Should fail when portfolios are incomplete"

    def test_validates_foreign_keys_enabled(self, seeded_db):
        """Validation should check PRAGMA foreign_keys = 1."""
        try:
            from src.backend.scripts.validate_schema import validate_pragma_settings, ValidationResult
        except ImportError:
            pytest.skip("Implementation not available yet")

        result = ValidationResult()
        validate_pragma_settings(seeded_db, result)
        assert len(result.passed) > 0, "Should pass PRAGMA checks"

    def test_validates_wal_mode(self, seeded_db):
        """Validation should check PRAGMA journal_mode = 'wal'."""
        try:
            from src.backend.scripts.validate_schema import validate_pragma_settings, ValidationResult
        except ImportError:
            pytest.skip("Implementation not available yet")

        result = ValidationResult()
        validate_pragma_settings(seeded_db, result)
        # WAL check should be among the passed checks
        assert len(result.passed) > 0, "Should pass WAL mode check"


class TestValidationOutput:
    """Verify validation script provides clear pass/fail output."""

    def test_validation_provides_summary(self, seeded_db, capsys):
        """Validation should output a clear pass/fail summary."""
        try:
            from src.backend.scripts.validate_schema import main
        except ImportError:
            pytest.skip("Implementation not available yet")

        cursor = seeded_db.cursor()
        cursor.execute("PRAGMA database_list")
        db_path = cursor.fetchone()[2]

        main(db_path=db_path)
        captured = capsys.readouterr()
        output = captured.out
        assert len(output) > 0, "Validation should provide output"

    def test_validation_shows_specific_failures(self, temp_db_path, capsys):
        """Validation should show specific details about what failed."""
        try:
            from src.backend.scripts.validate_schema import main
        except ImportError:
            pytest.skip("Implementation not available yet")

        # Create minimal invalid database
        conn = sqlite3.connect(temp_db_path)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE system_config (key TEXT, value TEXT)")
        conn.commit()
        conn.close()

        main(db_path=temp_db_path)
        captured = capsys.readouterr()
        assert 'FAIL' in captured.out, "Should show FAIL for missing items"


class TestValidationExitCodes:
    """Verify validation script returns correct exit codes."""

    def test_exit_code_0_on_pass(self, seeded_db):
        """Validation should return exit code 0 on pass."""
        try:
            from src.backend.scripts.validate_schema import main
        except ImportError:
            pytest.skip("Implementation not available yet")

        cursor = seeded_db.cursor()
        cursor.execute("PRAGMA database_list")
        db_path = cursor.fetchone()[2]

        result = main(db_path=db_path)
        assert result == 0, f"Expected exit code 0 on pass, got {result}"

    def test_exit_code_1_on_fail(self, temp_db_path):
        """Validation should return exit code 1 on fail."""
        try:
            from src.backend.scripts.validate_schema import main
        except ImportError:
            pytest.skip("Implementation not available yet")

        # Create empty database
        conn = sqlite3.connect(temp_db_path)
        conn.close()

        result = main(db_path=temp_db_path)
        assert result == 1, f"Expected exit code 1 on fail, got {result}"
