"""
Tests for story-001-008: Shared Error Handling Module

These tests verify:
- retry_with_backoff(fn, max_retries, base_delay, max_delay) retries with exponential backoff
- Configurable parameters (max_retries default 3-5, base_delay 1s, max_delay 30s)
- WarningsCollector.append(warning_type, message, context) adds warnings
- WarningsCollector.to_json() serializes as JSON array string, returns None if empty
- 7 warning types supported
- Each warning has: type, message, timestamp (ISO), context
- structlog configured for JSON output to logs/backend.log
- Backoff capped at max_delay
- WarningsCollector thread-safe
"""

import pytest
import time
import json
import threading
from datetime import datetime


class TestRetryWithBackoff:
    """Verify retry_with_backoff function behavior."""

    def test_retry_function_exists(self):
        """retry_with_backoff function should exist."""
        try:
            from src.backend.utils.errors import retry_with_backoff
            assert callable(retry_with_backoff), \
                "retry_with_backoff should be a callable function"
        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_retry_succeeds_on_first_attempt(self):
        """Function that succeeds immediately should return without retry."""
        try:
            from src.backend.utils.errors import retry_with_backoff

            call_count = [0]

            def succeeds_immediately():
                call_count[0] += 1
                return "success"

            result = retry_with_backoff(succeeds_immediately)

            assert result == "success", "Should return function result"
            assert call_count[0] == 1, "Should only call once when successful"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_retry_retries_on_failure(self):
        """Function that fails should be retried up to max_retries."""
        try:
            from src.backend.utils.errors import retry_with_backoff

            call_count = [0]

            def fails_twice():
                call_count[0] += 1
                if call_count[0] < 3:
                    raise ValueError("Temporary error")
                return "success"

            result = retry_with_backoff(fails_twice, max_retries=3)

            assert result == "success", "Should eventually succeed"
            assert call_count[0] == 3, "Should retry until success"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_retry_exhausts_max_retries(self):
        """Function that always fails should exhaust retries and raise."""
        try:
            from src.backend.utils.errors import retry_with_backoff

            call_count = [0]

            def always_fails():
                call_count[0] += 1
                raise ValueError("Permanent error")

            with pytest.raises(ValueError):
                retry_with_backoff(always_fails, max_retries=3)

            # Should try initial + 3 retries = 4 total
            assert call_count[0] == 4, f"Expected 4 attempts, got {call_count[0]}"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_exponential_backoff_timing(self):
        """Retry delays should follow exponential backoff pattern."""
        try:
            from src.backend.utils.errors import retry_with_backoff

            call_times = []

            def fails_three_times():
                call_times.append(time.time())
                if len(call_times) < 4:
                    raise ValueError("Temporary error")
                return "success"

            retry_with_backoff(fails_three_times, max_retries=3,
                               base_delay=0.1, max_delay=10)

            # Calculate delays between calls
            delays = [call_times[i+1] - call_times[i] for i in range(len(call_times)-1)]

            # First delay ~0.1s, second ~0.2s, third ~0.4s (exponential)
            assert delays[0] >= 0.09, f"First delay too short: {delays[0]}"
            assert delays[1] >= 0.18, f"Second delay too short: {delays[1]}"
            # Allow for timing variance
            assert delays[1] > delays[0], "Delays should increase exponentially"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_backoff_capped_at_max_delay(self):
        """Backoff delay should not exceed max_delay."""
        try:
            from src.backend.utils.errors import retry_with_backoff

            call_times = []

            def fails_many_times():
                call_times.append(time.time())
                if len(call_times) < 6:
                    raise ValueError("Temporary error")
                return "success"

            retry_with_backoff(fails_many_times, max_retries=5,
                               base_delay=1, max_delay=2)

            delays = [call_times[i+1] - call_times[i] for i in range(len(call_times)-1)]

            # All delays should be <= max_delay (2s) plus some tolerance
            for delay in delays:
                assert delay <= 2.5, \
                    f"Delay {delay} exceeds max_delay cap of 2s (with tolerance)"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_configurable_parameters(self):
        """retry_with_backoff should accept configurable parameters."""
        try:
            from src.backend.utils.errors import retry_with_backoff
            import inspect

            sig = inspect.signature(retry_with_backoff)
            params = sig.parameters

            assert 'fn' in params or list(params.keys())[0], \
                "Should accept function parameter"
            assert 'max_retries' in params, "Should accept max_retries parameter"
            assert 'base_delay' in params, "Should accept base_delay parameter"
            assert 'max_delay' in params, "Should accept max_delay parameter"

            # Check defaults
            if params['max_retries'].default != inspect.Parameter.empty:
                default = params['max_retries'].default
                assert 3 <= default <= 5, \
                    f"max_retries default should be 3-5, got {default}"

        except ImportError:
            pytest.skip("Implementation not available yet")


class TestWarningsCollector:
    """Verify WarningsCollector class behavior."""

    def test_warnings_collector_exists(self):
        """WarningsCollector class should exist."""
        try:
            from src.backend.utils.errors import WarningsCollector
            assert WarningsCollector is not None
        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_append_warning(self):
        """append() should add warnings with type, message, timestamp, context."""
        try:
            from src.backend.utils.errors import WarningsCollector

            collector = WarningsCollector()
            collector.append(
                warning_type='schwab_stock_unavailable',
                message='Failed to fetch AAPL quote',
                context={'ticker': 'AAPL'}
            )

            warnings = collector._warnings
            assert len(warnings) == 1, "Should have 1 warning"

            warning = warnings[0]
            assert warning['type'] == 'schwab_stock_unavailable'
            assert warning['message'] == 'Failed to fetch AAPL quote'
            assert 'timestamp' in warning, "Warning should have timestamp"
            assert warning['context'] == {'ticker': 'AAPL'}

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_seven_warning_types_supported(self):
        """All 7 warning types should be supported."""
        try:
            from src.backend.utils.errors import WarningsCollector

            expected_types = [
                'schwab_stock_unavailable',
                'schwab_options_unavailable',
                'image_analysis_failed',
                'market_hours_skipped',
                'insufficient_cash',
                'schwab_prediction_unavailable',
                'prediction_strike_unavailable'
            ]

            collector = WarningsCollector()

            # Add each warning type
            for wtype in expected_types:
                collector.append(warning_type=wtype, message=f"Test {wtype}", context={})

            assert len(collector._warnings) == 7, \
                f"Should support 7 warning types, got {len(collector._warnings)}"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_to_json_serialization(self):
        """to_json() should serialize warnings as JSON array string."""
        try:
            from src.backend.utils.errors import WarningsCollector

            collector = WarningsCollector()
            collector.append('schwab_stock_unavailable', 'Test warning', {'ticker': 'TSLA'})
            collector.append('market_hours_skipped', 'Market closed', {})

            json_str = collector.to_json()

            # Should be valid JSON
            warnings_array = json.loads(json_str)
            assert isinstance(warnings_array, list), "Should deserialize to list"
            assert len(warnings_array) == 2, "Should have 2 warnings"

            # Verify structure
            assert warnings_array[0]['type'] == 'schwab_stock_unavailable'
            assert warnings_array[1]['type'] == 'market_hours_skipped'

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_to_json_returns_none_when_empty(self):
        """to_json() should return None if no warnings."""
        try:
            from src.backend.utils.errors import WarningsCollector

            collector = WarningsCollector()
            result = collector.to_json()

            assert result is None, \
                f"to_json() should return None when empty, got {result}"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_timestamp_is_iso_format(self):
        """Warning timestamps should be in ISO format."""
        try:
            from src.backend.utils.errors import WarningsCollector

            collector = WarningsCollector()
            collector.append('schwab_stock_unavailable', 'Test', {})

            warning = collector._warnings[0]
            timestamp = warning['timestamp']

            # Should be able to parse as ISO datetime
            parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            assert isinstance(parsed, datetime), \
                "Timestamp should be valid ISO format datetime"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_warnings_collector_thread_safe(self):
        """WarningsCollector should be thread-safe."""
        try:
            from src.backend.utils.errors import WarningsCollector

            collector = WarningsCollector()
            errors = []

            def add_warnings():
                try:
                    for i in range(10):
                        collector.append(
                            'schwab_stock_unavailable',
                            f'Warning {i}',
                            {'count': i}
                        )
                except Exception as e:
                    errors.append(str(e))

            # Run in multiple threads
            threads = [threading.Thread(target=add_warnings) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0, f"Thread safety errors: {errors}"
            assert len(collector._warnings) == 30, \
                f"Expected 30 warnings from 3 threads, got {len(collector._warnings)}"

        except ImportError:
            pytest.skip("Implementation not available yet")


class TestStructlogConfiguration:
    """Verify structlog is configured for JSON output."""

    def test_structlog_configured(self):
        """structlog should be configured and importable."""
        try:
            import structlog
            from src.backend.utils.logging_config import setup_logging as configure_logging

            # Should be able to call configuration
            configure_logging()

            # Get a logger
            logger = structlog.get_logger()
            assert logger is not None, "Should be able to get logger"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_structlog_json_output(self, tmp_path):
        """structlog should output JSON format logs."""
        try:
            from src.backend.utils.logging_config import setup_logging as configure_logging
            import structlog

            # Configure with temp log directory
            configure_logging(log_dir=str(tmp_path), log_filename="test_backend.log")

            logger = structlog.get_logger()
            logger.info("test_message", key="value", count=42)

            # Read log file
            log_file = tmp_path / "test_backend.log"
            if log_file.exists():
                with open(log_file, 'r') as f:
                    log_line = f.readline()

                # Should be valid JSON
                log_entry = json.loads(log_line)
                assert 'event' in log_entry or 'message' in log_entry, \
                    "Log entry should have event/message field"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_default_log_path_is_logs_backend(self):
        """Default log file should be logs/backend.log."""
        try:
            from src.backend.utils.logging_config import setup_logging as configure_logging
            import inspect

            sig = inspect.signature(configure_logging)
            params = sig.parameters

            if 'log_file' in params:
                default = params['log_file'].default
                if default != inspect.Parameter.empty:
                    assert 'backend.log' in default, \
                        f"Default log file should be backend.log, got {default}"

        except ImportError:
            pytest.skip("Implementation not available yet")
