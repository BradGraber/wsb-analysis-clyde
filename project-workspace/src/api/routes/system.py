"""System health and price data API endpoints.

This module provides GET endpoints for system-level data:
- GET /prices/{ticker}: Daily close prices from price_history table
- GET /status: System health dashboard data
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, Query

from src.api.responses import wrap_response
from src.backend.utils.logging_config import get_logger

router = APIRouter(tags=["system"])
logger = get_logger(__name__)


def _dict_from_row(row) -> Dict[str, Any]:
    """Convert sqlite3.Row to dict."""
    return dict(row) if row else None


def _get_system_config_value(db, key: str) -> Optional[Any]:
    """Get a value from system_config table.

    Args:
        db: Database connection
        key: Configuration key

    Returns:
        Configuration value or None if not found
    """
    cursor = db.cursor()

    cursor.execute(
        "SELECT value FROM system_config WHERE key = ?",
        (key,)
    )

    row = cursor.fetchone()
    return row['value'] if row else None


def _get_system_config_bool(db, key: str, default: bool = False) -> bool:
    """Get a boolean value from system_config table.

    Args:
        db: Database connection
        key: Configuration key
        default: Default value if key not found

    Returns:
        Boolean value
    """
    value = _get_system_config_value(db, key)

    if value is None:
        return default

    # Handle various truthiness representations
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    elif isinstance(value, (int, bool)):
        return bool(value)

    return default


def _get_system_config_int(db, key: str, default: int = 0) -> int:
    """Get an integer value from system_config table.

    Args:
        db: Database connection
        key: Configuration key
        default: Default value if key not found

    Returns:
        Integer value
    """
    value = _get_system_config_value(db, key)

    if value is None:
        return default

    try:
        return int(value)
    except (ValueError, TypeError):
        return default


@router.get("/prices/{ticker}")
async def get_price_history(
    request: Request,
    ticker: str,
    days: int = Query(14, ge=1, le=90, description="Number of days to retrieve (default 14)")
):
    """Get daily close prices for a ticker from price_history table.

    This endpoint returns historical price data for sparklines and charts.
    Data is sourced from the price_history table (not live yfinance).

    Path Parameters:
        ticker: Ticker symbol

    Query Parameters:
        days: Number of days to retrieve (default 14, max 90)

    Returns:
        Response envelope with list of price data points:
        - date: Price date (YYYY-MM-DD)
        - close: Closing price

        Returns empty array for unknown tickers (not an error).
    """
    db = request.app.state.db
    cursor = db.cursor()

    logger.info("get_price_history_request", ticker=ticker, days=days)

    # Query price_history for the ticker, ordered by date descending, limited by days
    cursor.execute(
        """
        SELECT date, close
        FROM price_history
        WHERE UPPER(ticker) = UPPER(?)
        ORDER BY date DESC
        LIMIT ?
        """,
        (ticker, days)
    )

    rows = cursor.fetchall()

    # Convert to list of dicts and reverse to chronological order
    prices = [_dict_from_row(row) for row in reversed(rows)]

    logger.info(
        "get_price_history_response",
        ticker=ticker,
        days_requested=days,
        data_points=len(prices)
    )

    return wrap_response(prices)


@router.get("/status")
async def get_system_status(request: Request):
    """Get system health status for dashboard.

    Returns system health overview including:
    - current_pipeline_phase: Current phase label if analysis is running (null if not)
    - emergence_active: Boolean flag for emergence detection status
    - emergence_days_remaining: Days remaining in emergence window
    - open_position_count: Total count of open positions across all portfolios
    - last_run_completed_at: Timestamp of most recent completed analysis run
    - active_run_id: ID of currently running analysis (null if none)

    Returns:
        Response envelope with system status data
    """
    db = request.app.state.db
    cursor = db.cursor()

    logger.info("get_system_status_request")

    # Get active run (status = 'running')
    cursor.execute(
        """
        SELECT id, current_phase, current_phase_label
        FROM analysis_runs
        WHERE status = 'running'
        ORDER BY started_at DESC
        LIMIT 1
        """
    )

    active_run = cursor.fetchone()

    if active_run:
        active_run_id = active_run['id']
        current_pipeline_phase = active_run['current_phase_label']
    else:
        active_run_id = None
        current_pipeline_phase = None

    # Get emergence configuration
    emergence_active = _get_system_config_bool(db, 'emergence_active', default=False)
    emergence_days_remaining = _get_system_config_int(db, 'emergence_days_remaining', default=0)

    # Count open positions across all portfolios
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM positions
        WHERE status = 'open'
        """
    )

    open_position_count = cursor.fetchone()['count']

    # Get most recent completed run
    cursor.execute(
        """
        SELECT completed_at
        FROM analysis_runs
        WHERE status = 'completed'
        ORDER BY completed_at DESC
        LIMIT 1
        """
    )

    last_run_row = cursor.fetchone()
    last_run_completed_at = last_run_row['completed_at'] if last_run_row else None

    # Construct response
    status = {
        "current_pipeline_phase": current_pipeline_phase,
        "emergence_active": emergence_active,
        "emergence_days_remaining": emergence_days_remaining,
        "open_position_count": open_position_count,
        "last_run_completed_at": last_run_completed_at,
        "active_run_id": active_run_id
    }

    logger.info(
        "get_system_status_response",
        active_run_id=active_run_id,
        current_pipeline_phase=current_pipeline_phase,
        open_position_count=open_position_count
    )

    return wrap_response(status)
