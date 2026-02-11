"""
Database schema validation script.

Verifies that the database is correctly initialized with:
- All 16 required tables
- All 34 system_config keys
- All 4 portfolio records with correct configurations
- Proper PRAGMA settings (foreign_keys=ON, journal_mode=WAL)

Usage:
    python -m src.backend.scripts.validate_schema
    python src/backend/scripts/validate_schema.py
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.backend.db.connection import get_connection


# Expected schema components
EXPECTED_TABLES = [
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
    'prediction_exits',
]

EXPECTED_CONFIG_KEYS = [
    # System state (2 entries)
    'system_start_date',
    'phase',
    # Signal thresholds: Quality (2 entries)
    'quality_min_users',
    'quality_min_confidence',
    # Signal thresholds: Consensus (3 entries)
    'consensus_min_comments',
    'consensus_min_users',
    'consensus_min_alignment',
    # Confidence calculation weights (4 entries)
    'confidence_weight_volume',
    'confidence_weight_alignment',
    'confidence_weight_ai_confidence',
    'confidence_weight_author_trust',
    # Author trust calculation (6 entries)
    'trust_weight_quality',
    'trust_weight_accuracy',
    'trust_weight_tenure',
    'trust_default_accuracy',
    'trust_tenure_saturation_days',
    'accuracy_ema_weight',
    # Stock exit strategy thresholds (10 entries)
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
    # Options exit strategy thresholds (6 entries)
    'option_stop_loss_pct',
    'option_take_profit_pct',
    'option_trailing_stop_pct',
    'option_time_stop_days',
    'option_expiration_protection_dte',
    'option_take_profit_exit_pct',
    # Position management (1 entry)
    'signal_min_confidence',
]

EXPECTED_PORTFOLIOS = [
    {'name': 'stocks_quality', 'instrument_type': 'stock', 'signal_type': 'quality'},
    {'name': 'stocks_consensus', 'instrument_type': 'stock', 'signal_type': 'consensus'},
    {'name': 'options_quality', 'instrument_type': 'option', 'signal_type': 'quality'},
    {'name': 'options_consensus', 'instrument_type': 'option', 'signal_type': 'consensus'},
]

# Key columns to verify for each table (table_name -> list of column names)
TABLE_KEY_COLUMNS = {
    'system_config': ['key', 'value', 'updated_at'],
    'authors': ['id', 'username', 'first_seen'],
    'reddit_posts': ['id', 'reddit_id', 'title', 'fetched_at'],
    'signals': ['id', 'ticker', 'signal_type', 'signal_date', 'confidence'],
    'portfolios': ['id', 'name', 'instrument_type', 'signal_type', 'starting_capital', 'current_value', 'cash_available'],
    'positions': ['id', 'portfolio_id', 'signal_id', 'ticker', 'instrument_type', 'entry_price', 'status'],
    'price_history': ['id', 'ticker', 'date', 'open', 'high', 'low', 'close'],
    'evaluation_periods': ['id', 'portfolio_id', 'period_start', 'period_end', 'status'],
    'comments': ['id', 'analysis_run_id', 'post_id', 'reddit_id', 'author', 'body'],
    'analysis_runs': ['id', 'status', 'current_phase', 'started_at'],
    'signal_comments': ['id', 'signal_id', 'comment_id'],
    'comment_tickers': ['id', 'comment_id', 'ticker', 'sentiment'],
    'position_exits': ['id', 'position_id', 'exit_date', 'exit_reason'],
    'predictions': ['id', 'comment_id', 'ticker', 'sentiment', 'status'],
    'prediction_outcomes': ['id', 'prediction_id', 'day_offset', 'premium'],
    'prediction_exits': ['id', 'prediction_id', 'exit_date', 'exit_reason'],
}


class ValidationResult:
    """Tracks validation results."""

    def __init__(self):
        self.passed = []
        self.failed = []

    def add_pass(self, check_name: str):
        """Record a passing check."""
        self.passed.append(check_name)
        print(f"✓ PASS: {check_name}")

    def add_fail(self, check_name: str, details: str = None):
        """Record a failing check."""
        msg = f"✗ FAIL: {check_name}"
        if details:
            msg += f"\n  Details: {details}"
        self.failed.append(check_name)
        print(msg)

    def summary(self) -> bool:
        """Print summary and return True if all passed."""
        print("\n" + "=" * 70)
        print(f"VALIDATION SUMMARY: {len(self.passed)} passed, {len(self.failed)} failed")
        print("=" * 70)

        if self.failed:
            print("\nFailed checks:")
            for check in self.failed:
                print(f"  - {check}")
            return False
        else:
            print("\nAll checks passed!")
            return True


def validate_tables(conn, result: ValidationResult):
    """Verify all 16 tables exist with correct structures."""
    cursor = conn.cursor()

    # Get list of actual tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    actual_tables = {row['name'] for row in cursor.fetchall()}

    # Check for missing tables
    expected_set = set(EXPECTED_TABLES)
    missing = expected_set - actual_tables

    if missing:
        result.add_fail(
            "Table existence check",
            f"Missing tables: {', '.join(sorted(missing))}"
        )
    else:
        result.add_pass(f"All {len(EXPECTED_TABLES)} tables exist")

    # Verify key columns for each table
    for table in EXPECTED_TABLES:
        if table not in actual_tables:
            continue  # Already reported as missing

        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row['name'] for row in cursor.fetchall()]

        expected_cols = TABLE_KEY_COLUMNS.get(table, [])
        missing_cols = [col for col in expected_cols if col not in columns]

        if missing_cols:
            result.add_fail(
                f"Table '{table}' column check",
                f"Missing columns: {', '.join(missing_cols)}"
            )
        else:
            result.add_pass(f"Table '{table}' has {len(columns)} columns including key columns")


def validate_system_config(conn, result: ValidationResult):
    """Verify all 34 system_config keys are present."""
    cursor = conn.cursor()

    # Get actual config keys
    cursor.execute("SELECT key FROM system_config ORDER BY key")
    actual_keys = {row['key'] for row in cursor.fetchall()}

    # Check for missing keys
    expected_set = set(EXPECTED_CONFIG_KEYS)
    missing = expected_set - actual_keys

    if missing:
        result.add_fail(
            "system_config keys check",
            f"Missing {len(missing)} keys: {', '.join(sorted(missing))}"
        )
    else:
        result.add_pass(f"All {len(EXPECTED_CONFIG_KEYS)} system_config keys present")


def validate_portfolios(conn, result: ValidationResult):
    """Verify 4 portfolio rows with correct configurations."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, instrument_type, signal_type
        FROM portfolios
        ORDER BY name
    """)
    actual_portfolios = [
        {
            'name': row['name'],
            'instrument_type': row['instrument_type'],
            'signal_type': row['signal_type']
        }
        for row in cursor.fetchall()
    ]

    # Check count
    if len(actual_portfolios) != 4:
        result.add_fail(
            "Portfolio count",
            f"Expected 4 portfolios, found {len(actual_portfolios)}"
        )
        return

    # Check each expected portfolio exists with correct config
    all_match = True
    for expected in EXPECTED_PORTFOLIOS:
        found = any(
            p['name'] == expected['name']
            and p['instrument_type'] == expected['instrument_type']
            and p['signal_type'] == expected['signal_type']
            for p in actual_portfolios
        )
        if not found:
            all_match = False
            result.add_fail(
                f"Portfolio '{expected['name']}'",
                f"Not found or incorrect configuration"
            )

    if all_match:
        result.add_pass("All 4 portfolios present with correct configurations")


def validate_pragma_settings(conn, result: ValidationResult):
    """Verify PRAGMA foreign_keys and journal_mode settings."""
    cursor = conn.cursor()

    # Check foreign_keys
    cursor.execute("PRAGMA foreign_keys")
    fk_value = cursor.fetchone()[0]

    if fk_value == 1:
        result.add_pass("PRAGMA foreign_keys = 1")
    else:
        result.add_fail("PRAGMA foreign_keys", f"Expected 1, got {fk_value}")

    # Check journal_mode
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0].lower()

    if journal_mode == 'wal':
        result.add_pass("PRAGMA journal_mode = 'wal'")
    else:
        result.add_fail("PRAGMA journal_mode", f"Expected 'wal', got '{journal_mode}'")


def main(db_path=None):
    """Run all validation checks."""
    print("=" * 70)
    print("WSB Analysis Tool - Database Schema Validation")
    print("=" * 70)
    print()

    result = ValidationResult()

    try:
        with get_connection(db_path) as conn:
            validate_pragma_settings(conn, result)
            validate_tables(conn, result)
            validate_system_config(conn, result)
            validate_portfolios(conn, result)
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        return 1

    # Print summary and return appropriate exit code
    if result.summary():
        return 0
    else:
        return 1


if __name__ == '__main__':
    sys.exit(main())
