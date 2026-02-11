"""Error Handling Utilities

This module provides retry logic with exponential backoff for handling transient failures,
and warning collection for non-fatal events during analysis runs.
Part of the 4-tier error handling strategy (Tier 2: Retry with backoff, Tier 3: Degradation).
"""

import json
import time
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple, Type, TypeVar, Any


T = TypeVar('T')


def retry_with_backoff(
    fn: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> T:
    """Execute a callable with exponential backoff retry logic.

    Implements Tier 2 error handling: retry transient API failures with
    exponential backoff. Used for external integrations (Reddit, OpenAI, Schwab, yfinance).

    Args:
        fn: Callable to execute (should take no arguments)
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 30.0)
        retryable_exceptions: Tuple of exception types to retry on (default: all exceptions)

    Returns:
        The result of fn() on successful execution

    Raises:
        The final exception if all retries are exhausted, or immediately if the exception
        type is not in retryable_exceptions

    Example:
        >>> def fetch_data():
        ...     return api.get("/endpoint")
        >>> result = retry_with_backoff(
        ...     fetch_data,
        ...     max_retries=3,
        ...     base_delay=1.0,
        ...     max_delay=30.0,
        ...     retryable_exceptions=(requests.RequestException,)
        ... )

    Backoff schedule (base_delay=1.0, max_delay=30.0):
        - Attempt 1: immediate
        - Attempt 2: wait 1.0s (base_delay * 2^0)
        - Attempt 3: wait 2.0s (base_delay * 2^1)
        - Attempt 4: wait 4.0s (base_delay * 2^2)
        - etc., capped at max_delay
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            # Check if this exception type should be retried
            if not isinstance(e, retryable_exceptions):
                # Non-retryable exception: propagate immediately
                raise

            last_exception = e

            # If we've exhausted all retries, raise the final exception
            if attempt >= max_retries:
                raise

            # Calculate exponential backoff delay: base_delay * 2^attempt
            delay = base_delay * (2 ** attempt)
            # Cap at max_delay
            delay = min(delay, max_delay)

            # Wait before next retry
            time.sleep(delay)

    # This should never be reached due to the raise in the loop,
    # but Python's type checker needs this
    if last_exception:
        raise last_exception
    raise RuntimeError("Unreachable code")


# Supported warning types (Tier 3: Degradation)
WARNING_TYPE_SCHWAB_STOCK_UNAVAILABLE = "schwab_stock_unavailable"
WARNING_TYPE_SCHWAB_OPTIONS_UNAVAILABLE = "schwab_options_unavailable"
WARNING_TYPE_IMAGE_ANALYSIS_FAILED = "image_analysis_failed"
WARNING_TYPE_MARKET_HOURS_SKIPPED = "market_hours_skipped"
WARNING_TYPE_INSUFFICIENT_CASH = "insufficient_cash"
WARNING_TYPE_SCHWAB_PREDICTION_UNAVAILABLE = "schwab_prediction_unavailable"
WARNING_TYPE_PREDICTION_STRIKE_UNAVAILABLE = "prediction_strike_unavailable"

VALID_WARNING_TYPES = {
    WARNING_TYPE_SCHWAB_STOCK_UNAVAILABLE,
    WARNING_TYPE_SCHWAB_OPTIONS_UNAVAILABLE,
    WARNING_TYPE_IMAGE_ANALYSIS_FAILED,
    WARNING_TYPE_MARKET_HOURS_SKIPPED,
    WARNING_TYPE_INSUFFICIENT_CASH,
    WARNING_TYPE_SCHWAB_PREDICTION_UNAVAILABLE,
    WARNING_TYPE_PREDICTION_STRIKE_UNAVAILABLE,
}


class WarningsCollector:
    """Thread-safe collector for non-fatal warnings during analysis runs.

    Accumulates warning events with type, message, timestamp, and context.
    Supports serialization to JSON for storage in analysis_runs.warnings column.
    Part of Tier 3 (Degradation) error handling.

    Example:
        >>> collector = WarningsCollector()
        >>> collector.append(
        ...     "schwab_stock_unavailable",
        ...     "Failed to fetch quote for AAPL",
        ...     {"ticker": "AAPL", "attempts": 3}
        ... )
        >>> json_string = collector.to_json()
        >>> print(json_string)
        '[{"type": "schwab_stock_unavailable", "message": "...", "timestamp": "...", "context": {...}}]'
    """

    def __init__(self):
        """Initialize an empty warnings collector."""
        self._warnings: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def append(self, warning_type: str, message: str, context: Dict[str, Any]) -> None:
        """Add a warning with type, message, timestamp, and context.

        Thread-safe via internal lock. Timestamp is auto-generated in ISO 8601 format (UTC).

        Args:
            warning_type: One of the 7 supported warning types (see VALID_WARNING_TYPES)
            message: Human-readable description of the warning
            context: Additional structured data (e.g., ticker, attempts, reason)

        Raises:
            ValueError: If warning_type is not in VALID_WARNING_TYPES
        """
        if warning_type not in VALID_WARNING_TYPES:
            raise ValueError(
                f"Invalid warning_type '{warning_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_WARNING_TYPES))}"
            )

        warning = {
            "type": warning_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context
        }

        with self._lock:
            self._warnings.append(warning)

    def to_json(self) -> Optional[str]:
        """Serialize warnings to JSON array string.

        Returns:
            JSON array string of all warnings if any exist, None if no warnings collected.

        Example:
            >>> collector.to_json()
            '[{"type": "schwab_stock_unavailable", "message": "...", "timestamp": "...", "context": {...}}]'
            >>> empty_collector.to_json()
            None
        """
        with self._lock:
            if not self._warnings:
                return None
            return json.dumps(self._warnings)
