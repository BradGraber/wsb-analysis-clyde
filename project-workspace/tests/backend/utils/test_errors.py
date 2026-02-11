"""Unit Tests for Error Handling Utilities

Tests cover retry_with_backoff and WarningsCollector:

retry_with_backoff:
1. Successful call returns result without retry
2. Call succeeds on 2nd attempt after 1 retry
3. Call fails after max_retries and raises final exception
4. Non-retryable exception propagates immediately without retry
5. Exponential backoff with proper delay calculations
6. Delay capping at max_delay

WarningsCollector:
1. Initializes with empty warnings list
2. append() adds warning with all 4 fields (type, message, timestamp, context)
3. to_json() returns None when empty
4. Single warning serializes correctly with all 4 fields
5. Multiple warnings from multiple threads produce correct JSON
6. Supports all 7 warning types
7. append() is thread-safe
"""

import json
import time
import pytest
import threading
from datetime import datetime
from unittest.mock import Mock, patch

from src.backend.utils.errors import (
    retry_with_backoff,
    WarningsCollector,
    WARNING_TYPE_SCHWAB_STOCK_UNAVAILABLE,
    WARNING_TYPE_SCHWAB_OPTIONS_UNAVAILABLE,
    WARNING_TYPE_IMAGE_ANALYSIS_FAILED,
    WARNING_TYPE_MARKET_HOURS_SKIPPED,
    WARNING_TYPE_INSUFFICIENT_CASH,
    WARNING_TYPE_SCHWAB_PREDICTION_UNAVAILABLE,
    WARNING_TYPE_PREDICTION_STRIKE_UNAVAILABLE,
)


class RetryableError(Exception):
    """Mock retryable exception for testing"""
    pass


class NonRetryableError(Exception):
    """Mock non-retryable exception for testing"""
    pass


class TestRetryWithBackoff:
    """Test suite for retry_with_backoff function"""

    def test_successful_call_returns_result_without_retry(self):
        """Test that a successful call returns the result immediately without any retries"""
        mock_fn = Mock(return_value="success")

        result = retry_with_backoff(mock_fn)

        assert result == "success"
        assert mock_fn.call_count == 1

    def test_call_succeeds_on_second_attempt_after_one_retry(self):
        """Test that a call that fails once then succeeds returns the result after 1 retry"""
        mock_fn = Mock(side_effect=[RetryableError("transient"), "success"])

        with patch('time.sleep') as mock_sleep:
            result = retry_with_backoff(
                mock_fn,
                max_retries=3,
                base_delay=1.0,
                retryable_exceptions=(RetryableError,)
            )

        assert result == "success"
        assert mock_fn.call_count == 2
        # First retry delay: base_delay * 2^0 = 1.0
        mock_sleep.assert_called_once_with(1.0)

    def test_call_fails_after_max_retries_and_raises_final_exception(self):
        """Test that exhausting all retries raises the final exception"""
        mock_fn = Mock(side_effect=RetryableError("persistent failure"))

        with patch('time.sleep') as mock_sleep:
            with pytest.raises(RetryableError, match="persistent failure"):
                retry_with_backoff(
                    mock_fn,
                    max_retries=3,
                    base_delay=1.0,
                    retryable_exceptions=(RetryableError,)
                )

        # Should call fn 4 times (initial + 3 retries)
        assert mock_fn.call_count == 4
        # Should sleep 3 times (between retries)
        assert mock_sleep.call_count == 3

    def test_non_retryable_exception_propagates_immediately(self):
        """Test that non-retryable exceptions are raised immediately without any retries"""
        mock_fn = Mock(side_effect=NonRetryableError("immediate failure"))

        with patch('time.sleep') as mock_sleep:
            with pytest.raises(NonRetryableError, match="immediate failure"):
                retry_with_backoff(
                    mock_fn,
                    max_retries=3,
                    base_delay=1.0,
                    retryable_exceptions=(RetryableError,)  # NonRetryableError not in tuple
                )

        # Should only call fn once
        assert mock_fn.call_count == 1
        # Should never sleep
        mock_sleep.assert_not_called()

    def test_exponential_backoff_delays(self):
        """Test that delays follow exponential backoff: base_delay * 2^attempt"""
        mock_fn = Mock(side_effect=RetryableError("fail"))

        with patch('time.sleep') as mock_sleep:
            with pytest.raises(RetryableError):
                retry_with_backoff(
                    mock_fn,
                    max_retries=3,
                    base_delay=1.0,
                    max_delay=30.0,
                    retryable_exceptions=(RetryableError,)
                )

        # Verify exponential backoff delays: 1.0, 2.0, 4.0
        expected_delays = [1.0, 2.0, 4.0]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    def test_delay_capped_at_max_delay(self):
        """Test that delays are capped at max_delay when exponential backoff exceeds it"""
        mock_fn = Mock(side_effect=RetryableError("fail"))

        with patch('time.sleep') as mock_sleep:
            with pytest.raises(RetryableError):
                retry_with_backoff(
                    mock_fn,
                    max_retries=10,
                    base_delay=1.0,
                    max_delay=5.0,  # Cap at 5 seconds
                    retryable_exceptions=(RetryableError,)
                )

        # Verify that no delay exceeds max_delay
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        # Expected: 1.0, 2.0, 4.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0
        # (after 4.0, next would be 8.0 but capped at 5.0)
        assert all(delay <= 5.0 for delay in actual_delays)
        # Verify specific sequence
        expected_delays = [1.0, 2.0, 4.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
        assert actual_delays == expected_delays

    def test_default_parameters(self):
        """Test that default parameters work as expected"""
        mock_fn = Mock(side_effect=Exception("fail"))

        with patch('time.sleep') as mock_sleep:
            with pytest.raises(Exception):
                retry_with_backoff(mock_fn)  # Use all defaults

        # Default max_retries=3, so 4 calls total
        assert mock_fn.call_count == 4
        # Default base_delay=1.0, so delays: 1.0, 2.0, 4.0
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == [1.0, 2.0, 4.0]

    def test_returns_various_types(self):
        """Test that retry_with_backoff correctly returns various result types"""
        # Test with integer
        mock_fn = Mock(return_value=42)
        assert retry_with_backoff(mock_fn) == 42

        # Test with dict
        mock_fn = Mock(return_value={"key": "value"})
        assert retry_with_backoff(mock_fn) == {"key": "value"}

        # Test with None
        mock_fn = Mock(return_value=None)
        assert retry_with_backoff(mock_fn) is None

        # Test with list
        mock_fn = Mock(return_value=[1, 2, 3])
        assert retry_with_backoff(mock_fn) == [1, 2, 3]

    def test_multiple_retryable_exception_types(self):
        """Test that multiple exception types can be specified as retryable"""
        class AnotherRetryableError(Exception):
            pass

        # Test with first exception type
        mock_fn = Mock(side_effect=[RetryableError("fail"), "success"])
        with patch('time.sleep'):
            result = retry_with_backoff(
                mock_fn,
                retryable_exceptions=(RetryableError, AnotherRetryableError)
            )
        assert result == "success"

        # Test with second exception type
        mock_fn = Mock(side_effect=[AnotherRetryableError("fail"), "success"])
        with patch('time.sleep'):
            result = retry_with_backoff(
                mock_fn,
                retryable_exceptions=(RetryableError, AnotherRetryableError)
            )
        assert result == "success"

    def test_zero_retries(self):
        """Test that max_retries=0 means no retries, only initial attempt"""
        mock_fn = Mock(side_effect=RetryableError("fail"))

        with patch('time.sleep') as mock_sleep:
            with pytest.raises(RetryableError):
                retry_with_backoff(
                    mock_fn,
                    max_retries=0,
                    retryable_exceptions=(RetryableError,)
                )

        # Should only call once (no retries)
        assert mock_fn.call_count == 1
        # Should never sleep
        mock_sleep.assert_not_called()

    def test_different_base_delays(self):
        """Test that different base_delay values affect the backoff schedule"""
        mock_fn = Mock(side_effect=RetryableError("fail"))

        with patch('time.sleep') as mock_sleep:
            with pytest.raises(RetryableError):
                retry_with_backoff(
                    mock_fn,
                    max_retries=3,
                    base_delay=2.0,  # Different base delay
                    max_delay=100.0,
                    retryable_exceptions=(RetryableError,)
                )

        # Expected delays with base_delay=2.0: 2.0, 4.0, 8.0
        expected_delays = [2.0, 4.0, 8.0]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays


class TestWarningsCollector:
    """Test suite for WarningsCollector class"""

    def test_initializes_with_empty_warnings_list(self):
        """Test that WarningsCollector() initializes with an empty warnings list"""
        collector = WarningsCollector()

        # to_json() should return None for empty collector
        assert collector.to_json() is None

    def test_to_json_returns_none_when_empty(self):
        """Test that to_json() returns None (not empty string, not '[]') when no warnings"""
        collector = WarningsCollector()

        result = collector.to_json()

        assert result is None
        assert result != "[]"
        assert result != ""

    def test_single_warning_serializes_with_all_fields(self):
        """Test that a single warning serializes correctly with type, message, timestamp, and context"""
        collector = WarningsCollector()

        collector.append(
            WARNING_TYPE_SCHWAB_STOCK_UNAVAILABLE,
            "Failed to fetch quote for AAPL",
            {"ticker": "AAPL", "attempts": 3}
        )

        json_string = collector.to_json()
        assert json_string is not None

        # Parse and verify structure
        warnings = json.loads(json_string)
        assert isinstance(warnings, list)
        assert len(warnings) == 1

        warning = warnings[0]
        assert warning["type"] == WARNING_TYPE_SCHWAB_STOCK_UNAVAILABLE
        assert warning["message"] == "Failed to fetch quote for AAPL"
        assert "timestamp" in warning
        assert warning["context"] == {"ticker": "AAPL", "attempts": 3}

        # Verify timestamp is valid ISO format
        timestamp = datetime.fromisoformat(warning["timestamp"])
        assert timestamp is not None

    def test_append_adds_warning_with_all_required_fields(self):
        """Test that append() adds a warning with type, message, timestamp (ISO format), and context"""
        collector = WarningsCollector()

        collector.append(
            WARNING_TYPE_IMAGE_ANALYSIS_FAILED,
            "GPT-4 vision API returned error",
            {"post_id": "abc123", "error": "rate_limit"}
        )

        json_string = collector.to_json()
        warnings = json.loads(json_string)
        warning = warnings[0]

        # Verify all 4 required fields
        assert "type" in warning
        assert "message" in warning
        assert "timestamp" in warning
        assert "context" in warning

        # Verify values
        assert warning["type"] == WARNING_TYPE_IMAGE_ANALYSIS_FAILED
        assert warning["message"] == "GPT-4 vision API returned error"
        assert warning["context"]["post_id"] == "abc123"
        assert warning["context"]["error"] == "rate_limit"

        # Verify timestamp is ISO 8601 format with timezone
        timestamp_str = warning["timestamp"]
        assert "T" in timestamp_str  # ISO format separator
        # Should parse without error
        dt = datetime.fromisoformat(timestamp_str)
        assert dt.tzinfo is not None  # Must include timezone (UTC)

    def test_supports_all_seven_warning_types(self):
        """Test that all 7 warning types defined in PRD PIPE-055 are supported"""
        collector = WarningsCollector()

        all_warning_types = [
            WARNING_TYPE_SCHWAB_STOCK_UNAVAILABLE,
            WARNING_TYPE_SCHWAB_OPTIONS_UNAVAILABLE,
            WARNING_TYPE_IMAGE_ANALYSIS_FAILED,
            WARNING_TYPE_MARKET_HOURS_SKIPPED,
            WARNING_TYPE_INSUFFICIENT_CASH,
            WARNING_TYPE_SCHWAB_PREDICTION_UNAVAILABLE,
            WARNING_TYPE_PREDICTION_STRIKE_UNAVAILABLE,
        ]

        # Verify we have exactly 7 types
        assert len(all_warning_types) == 7

        # Append one warning of each type
        for i, warning_type in enumerate(all_warning_types):
            collector.append(
                warning_type,
                f"Test message {i}",
                {"index": i}
            )

        json_string = collector.to_json()
        warnings = json.loads(json_string)

        # Verify all 7 warnings were added
        assert len(warnings) == 7

        # Verify each type is present
        warning_types = [w["type"] for w in warnings]
        assert set(warning_types) == set(all_warning_types)

    def test_invalid_warning_type_raises_value_error(self):
        """Test that append() raises ValueError for invalid warning types"""
        collector = WarningsCollector()

        with pytest.raises(ValueError, match="Invalid warning_type"):
            collector.append(
                "invalid_type",
                "This should fail",
                {}
            )

    def test_multiple_warnings_serialize_correctly(self):
        """Test that multiple warnings accumulate and serialize as a JSON array"""
        collector = WarningsCollector()

        collector.append(
            WARNING_TYPE_MARKET_HOURS_SKIPPED,
            "Market closed, skipping position opens",
            {"time": "18:00 ET"}
        )
        collector.append(
            WARNING_TYPE_INSUFFICIENT_CASH,
            "Not enough cash for TSLA position",
            {"ticker": "TSLA", "required": 5000, "available": 3000}
        )

        json_string = collector.to_json()
        warnings = json.loads(json_string)

        assert len(warnings) == 2
        assert warnings[0]["type"] == WARNING_TYPE_MARKET_HOURS_SKIPPED
        assert warnings[1]["type"] == WARNING_TYPE_INSUFFICIENT_CASH
        assert warnings[1]["context"]["ticker"] == "TSLA"

    def test_thread_safety_multiple_threads(self):
        """Test that append() is thread-safe when called from multiple threads"""
        collector = WarningsCollector()
        num_threads = 10
        warnings_per_thread = 10

        def add_warnings(thread_id):
            for i in range(warnings_per_thread):
                collector.append(
                    WARNING_TYPE_SCHWAB_STOCK_UNAVAILABLE,
                    f"Thread {thread_id} warning {i}",
                    {"thread_id": thread_id, "warning_num": i}
                )

        threads = []
        for t in range(num_threads):
            thread = threading.Thread(target=add_warnings, args=(t,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        json_string = collector.to_json()
        warnings = json.loads(json_string)

        # Verify all warnings were added (no lost updates due to race conditions)
        expected_count = num_threads * warnings_per_thread
        assert len(warnings) == expected_count

        # Verify all warnings have the required fields
        for warning in warnings:
            assert "type" in warning
            assert "message" in warning
            assert "timestamp" in warning
            assert "context" in warning
            assert warning["type"] == WARNING_TYPE_SCHWAB_STOCK_UNAVAILABLE

    def test_context_can_be_empty_dict(self):
        """Test that context can be an empty dictionary"""
        collector = WarningsCollector()

        collector.append(
            WARNING_TYPE_MARKET_HOURS_SKIPPED,
            "Market closed",
            {}
        )

        json_string = collector.to_json()
        warnings = json.loads(json_string)

        assert warnings[0]["context"] == {}

    def test_context_can_contain_nested_structures(self):
        """Test that context can contain nested dictionaries and lists"""
        collector = WarningsCollector()

        complex_context = {
            "ticker": "AAPL",
            "attempts": [1, 2, 3],
            "errors": {
                "first": "timeout",
                "second": "rate_limit"
            },
            "metadata": {
                "source": "schwab",
                "nested": {
                    "level": 2
                }
            }
        }

        collector.append(
            WARNING_TYPE_SCHWAB_OPTIONS_UNAVAILABLE,
            "Complex context test",
            complex_context
        )

        json_string = collector.to_json()
        warnings = json.loads(json_string)

        # Verify complex context round-trips correctly
        assert warnings[0]["context"] == complex_context
