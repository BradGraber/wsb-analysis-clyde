"""
Tests for story-001-001: Create Database Schema with 16 Tables and Constraints

These tests verify that the schema creation logic:
- Creates all 16 required tables
- Defines correct column names, types, and constraints
- Establishes all foreign key relationships
- Sets up UNIQUE constraints on junction tables
- Configures proper ON DELETE behavior
- Enables foreign key enforcement and WAL mode
"""

import pytest
import sqlite3


class TestSchemaCreation:
    """Verify schema creates all 16 tables with correct structure."""

    def test_all_16_tables_exist(self, schema_initialized_db, expected_tables):
        """All 16 tables must be created."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        actual_tables = [row[0] for row in cursor.fetchall()]

        for table in expected_tables:
            assert table in actual_tables, f"Table {table} not found in schema"

        assert len(actual_tables) >= len(expected_tables), \
            f"Expected at least {len(expected_tables)} tables, found {len(actual_tables)}"

    def test_system_config_columns(self, schema_initialized_db):
        """system_config table has correct structure."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA table_info(system_config)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert 'key' in columns, "system_config missing 'key' column"
        assert 'value' in columns, "system_config missing 'value' column"
        assert 'VARCHAR' in columns['key'].upper() or columns['key'].upper() == 'TEXT', \
            "key should be TEXT or VARCHAR"

    def test_authors_columns(self, schema_initialized_db):
        """authors table has correct structure."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA table_info(authors)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        required = ['id', 'username', 'total_comments', 'high_quality_comments',
                    'total_upvotes', 'avg_conviction_score', 'avg_sentiment_accuracy']
        for col in required:
            assert col in columns, f"authors missing required column: {col}"

    def test_signals_columns(self, schema_initialized_db):
        """signals table has correct structure."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA table_info(signals)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        required = ['id', 'ticker', 'signal_type', 'signal_date', 'prediction',
                    'confidence', 'position_opened']
        for col in required:
            assert col in columns, f"signals missing required column: {col}"

    def test_portfolios_columns(self, schema_initialized_db):
        """portfolios table has correct structure."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA table_info(portfolios)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        required = ['id', 'name', 'instrument_type', 'signal_type',
                    'starting_capital', 'current_value', 'cash_available']
        for col in required:
            assert col in columns, f"portfolios missing required column: {col}"

    def test_positions_columns(self, schema_initialized_db):
        """positions table has correct structure."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA table_info(positions)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        required = ['id', 'portfolio_id', 'signal_id', 'ticker', 'instrument_type',
                    'entry_date', 'entry_price', 'shares', 'contracts']
        for col in required:
            assert col in columns, f"positions missing required column: {col}"

    def test_comments_columns(self, schema_initialized_db):
        """comments table has correct structure including self-referential FK."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA table_info(comments)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        required = ['id', 'reddit_id', 'post_id', 'author', 'parent_comment_id',
                    'body', 'sentiment', 'sarcasm_detected', 'has_reasoning',
                    'ai_confidence']
        for col in required:
            assert col in columns, f"comments missing required column: {col}"


class TestUniqueConstraints:
    """Verify UNIQUE constraints on junction tables and key tables."""

    def test_signal_comments_unique_constraint(self, schema_initialized_db):
        """signal_comments has UNIQUE(signal_id, comment_id)."""
        cursor = schema_initialized_db.cursor()

        # Get index information for signal_comments
        cursor.execute("PRAGMA index_list(signal_comments)")
        indexes = cursor.fetchall()

        # Check if there's a unique index on signal_id, comment_id
        found_unique = False
        for idx in indexes:
            idx_name = idx[1]
            is_unique = idx[2] == 1

            if is_unique:
                cursor.execute(f"PRAGMA index_info({idx_name})")
                idx_cols = [row[2] for row in cursor.fetchall()]
                if set(idx_cols) == {'signal_id', 'comment_id'}:
                    found_unique = True
                    break

        assert found_unique, "signal_comments missing UNIQUE(signal_id, comment_id)"

    def test_comment_tickers_unique_constraint(self, schema_initialized_db):
        """comment_tickers has UNIQUE(comment_id, ticker)."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA index_list(comment_tickers)")
        indexes = cursor.fetchall()

        found_unique = False
        for idx in indexes:
            idx_name = idx[1]
            is_unique = idx[2] == 1

            if is_unique:
                cursor.execute(f"PRAGMA index_info({idx_name})")
                idx_cols = [row[2] for row in cursor.fetchall()]
                if set(idx_cols) == {'comment_id', 'ticker'}:
                    found_unique = True
                    break

        assert found_unique, "comment_tickers missing UNIQUE(comment_id, ticker)"

    def test_signals_unique_constraint(self, schema_initialized_db):
        """signals has UNIQUE(ticker, signal_type, signal_date)."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA index_list(signals)")
        indexes = cursor.fetchall()

        found_unique = False
        for idx in indexes:
            idx_name = idx[1]
            is_unique = idx[2] == 1

            if is_unique:
                cursor.execute(f"PRAGMA index_info({idx_name})")
                idx_cols = [row[2] for row in cursor.fetchall()]
                if set(idx_cols) == {'ticker', 'signal_type', 'signal_date'}:
                    found_unique = True
                    break

        assert found_unique, "signals missing UNIQUE(ticker, signal_type, signal_date)"

    def test_price_history_unique_constraint(self, schema_initialized_db):
        """price_history has UNIQUE(ticker, date)."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA index_list(price_history)")
        indexes = cursor.fetchall()

        found_unique = False
        for idx in indexes:
            idx_name = idx[1]
            is_unique = idx[2] == 1

            if is_unique:
                cursor.execute(f"PRAGMA index_info({idx_name})")
                idx_cols = [row[2] for row in cursor.fetchall()]
                if set(idx_cols) == {'ticker', 'date'}:
                    found_unique = True
                    break

        assert found_unique, "price_history missing UNIQUE(ticker, date)"

    def test_predictions_unique_constraint(self, schema_initialized_db):
        """predictions has UNIQUE(comment_id, ticker)."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA index_list(predictions)")
        indexes = cursor.fetchall()

        found_unique = False
        for idx in indexes:
            idx_name = idx[1]
            is_unique = idx[2] == 1

            if is_unique:
                cursor.execute(f"PRAGMA index_info({idx_name})")
                idx_cols = [row[2] for row in cursor.fetchall()]
                if set(idx_cols) == {'comment_id', 'ticker'}:
                    found_unique = True
                    break

        assert found_unique, "predictions missing UNIQUE(comment_id, ticker)"


class TestForeignKeyRelationships:
    """Verify foreign key relationships and ON DELETE behavior."""

    def test_foreign_keys_enabled(self, schema_initialized_db):
        """PRAGMA foreign_keys must be ON."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()

        assert result is not None, "PRAGMA foreign_keys returned no result"
        assert result[0] == 1, "Foreign keys not enabled (PRAGMA foreign_keys != 1)"

    def test_position_exits_cascade_on_position_delete(self, schema_initialized_db):
        """position_exits.position_id has ON DELETE CASCADE."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA foreign_key_list(position_exits)")
        fks = cursor.fetchall()

        found_cascade = False
        for fk in fks:
            # fk format: (id, seq, table, from, to, on_update, on_delete, match)
            if fk[2] == 'positions' and fk[3] == 'position_id':
                assert fk[6] == 'CASCADE', \
                    "position_exits.position_id should have ON DELETE CASCADE"
                found_cascade = True
                break

        assert found_cascade, "position_exits.position_id foreign key not found"

    def test_comments_restrict_on_post_delete(self, schema_initialized_db):
        """comments.post_id has ON DELETE RESTRICT."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA foreign_key_list(comments)")
        fks = cursor.fetchall()

        found_restrict = False
        for fk in fks:
            if fk[2] == 'reddit_posts' and fk[3] == 'post_id':
                # RESTRICT is the default, but could also be 'NO ACTION'
                assert fk[6] in ['RESTRICT', 'NO ACTION'], \
                    "comments.post_id should have ON DELETE RESTRICT"
                found_restrict = True
                break

        assert found_restrict, "comments.post_id foreign key not found"

    def test_comments_self_referential_fk_nullable(self, schema_initialized_db):
        """comments.parent_comment_id can be NULL and references comments.id."""
        cursor = schema_initialized_db.cursor()

        # Check column is nullable
        cursor.execute("PRAGMA table_info(comments)")
        columns = {row[1]: {'notnull': row[3], 'type': row[2]} for row in cursor.fetchall()}

        assert 'parent_comment_id' in columns, "parent_comment_id column not found"
        assert columns['parent_comment_id']['notnull'] == 0, \
            "parent_comment_id should allow NULL"

        # Check foreign key points to comments table
        cursor.execute("PRAGMA foreign_key_list(comments)")
        fks = cursor.fetchall()

        found_self_ref = False
        for fk in fks:
            if fk[3] == 'parent_comment_id' and fk[2] == 'comments':
                found_self_ref = True
                break

        assert found_self_ref, "comments.parent_comment_id self-referential FK not found"


class TestDatabaseConfiguration:
    """Verify database-level configuration settings."""

    def test_wal_mode_enabled(self, schema_initialized_db):
        """PRAGMA journal_mode must return 'wal'."""
        cursor = schema_initialized_db.cursor()
        cursor.execute("PRAGMA journal_mode")
        result = cursor.fetchone()

        assert result is not None, "PRAGMA journal_mode returned no result"
        assert result[0].lower() == 'wal', \
            f"Expected WAL mode, got {result[0]}"

    def test_schema_executes_without_errors(self, temp_db_path):
        """Schema file can be executed on fresh database without errors."""
        import sqlite3
        from pathlib import Path

        schema_path = Path(__file__).parent.parent / "src" / "backend" / "db" / "schema.sql"
        assert schema_path.exists(), f"schema.sql not found at {schema_path}"

        conn = sqlite3.connect(temp_db_path)
        try:
            sql = schema_path.read_text()
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            lines = [line for line in sql.splitlines()
                     if not line.strip().upper().startswith("PRAGMA")]
            conn.executescript("\n".join(lines))
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]
            assert table_count >= 16, f"Expected at least 16 tables, got {table_count}"
        finally:
            conn.close()
