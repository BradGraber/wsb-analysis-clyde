"""Signal-related API endpoints.

This module provides four GET endpoints for signal data:
- GET /signals: List signals with filters and computed fields
- GET /signals/{id}: Get single signal details
- GET /signals/{id}/comments: Get paginated comments for a signal
- GET /signals/history: Get confidence history grouped by ticker
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, Query, Depends

from src.api.models import PaginationParams
from src.api.responses import wrap_response, raise_api_error, NOT_FOUND

router = APIRouter(prefix="/signals", tags=["signals"])


def _dict_from_row(row) -> Dict[str, Any]:
    """Convert sqlite3.Row to dict."""
    return dict(row) if row else None


def _compute_position_summary(db, signal_id: int) -> Dict[str, Any]:
    """Compute position summary for a signal.

    Returns count of positions across portfolios with status breakdown.

    Args:
        db: Database connection
        signal_id: Signal ID

    Returns:
        Dict with total_positions and status_breakdown
    """
    cursor = db.cursor()

    # Count total positions
    cursor.execute(
        "SELECT COUNT(*) as count FROM positions WHERE signal_id = ?",
        (signal_id,)
    )
    total = cursor.fetchone()['count']

    # Get status breakdown
    cursor.execute(
        """
        SELECT status, COUNT(*) as count
        FROM positions
        WHERE signal_id = ?
        GROUP BY status
        """,
        (signal_id,)
    )
    status_rows = cursor.fetchall()
    status_breakdown = {row['status']: row['count'] for row in status_rows}

    return {
        "total_positions": total,
        "status_breakdown": status_breakdown
    }


def _compute_skip_reason(db, signal_id: int, portfolio_id: Optional[int]) -> Optional[str]:
    """Compute skip_reason for a signal.

    Returns "bearish_long_only" when applicable, otherwise generic "not eligible".

    Args:
        db: Database connection
        signal_id: Signal ID
        portfolio_id: Optional portfolio ID filter

    Returns:
        Skip reason string or None if position was opened
    """
    cursor = db.cursor()

    # Get signal details
    cursor.execute(
        "SELECT prediction, position_opened FROM signals WHERE id = ?",
        (signal_id,)
    )
    signal_row = cursor.fetchone()

    if not signal_row:
        return None

    # If position was opened, no skip reason
    if signal_row['position_opened']:
        return None

    # Check if bearish prediction and portfolio is stock-based
    if signal_row['prediction'] == 'bearish' and portfolio_id:
        cursor.execute(
            "SELECT instrument_type FROM portfolios WHERE id = ?",
            (portfolio_id,)
        )
        portfolio = cursor.fetchone()
        if portfolio and portfolio['instrument_type'] == 'stock':
            return "bearish_long_only"

    # Generic skip reason
    return "not eligible"


@router.get("")
async def list_signals(
    request: Request,
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    signal_type: Optional[str] = Query(None, description="Filter by signal type (quality/consensus)"),
    date_from: Optional[str] = Query(None, description="Filter by signal date from (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter by signal date to (YYYY-MM-DD)"),
    portfolio_id: Optional[int] = Query(None, description="Filter by portfolio ID"),
    pagination: PaginationParams = Depends()
):
    """List signals with filters and pagination.

    Returns paginated signals with computed position_summary and skip_reason fields.
    All filter parameters work individually and can be combined.

    Query Parameters:
        ticker: Filter by ticker symbol (exact match, case-insensitive)
        signal_type: Filter by signal type (quality/consensus)
        date_from: Filter signals from this date (inclusive)
        date_to: Filter signals to this date (inclusive)
        portfolio_id: Filter by portfolio ID (affects skip_reason computation)
        limit: Maximum results to return (default 50, max 100)
        offset: Number of results to skip (default 0)

    Returns:
        Response envelope with list of signals and pagination metadata
    """
    db = request.app.state.db
    cursor = db.cursor()

    # Build WHERE clause dynamically
    where_clauses = []
    params = []

    if ticker:
        where_clauses.append("UPPER(ticker) = UPPER(?)")
        params.append(ticker)

    if signal_type:
        where_clauses.append("signal_type = ?")
        params.append(signal_type)

    if date_from:
        where_clauses.append("signal_date >= ?")
        params.append(date_from)

    if date_to:
        where_clauses.append("signal_date <= ?")
        params.append(date_to)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Count total matching signals
    count_query = f"SELECT COUNT(*) as total FROM signals {where_sql}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()['total']

    # Fetch paginated signals
    query = f"""
        SELECT
            id, signal_date, created_at, updated_at, ticker, signal_type,
            sentiment_score, prediction, confidence, comment_count,
            has_reasoning, is_emergence, prior_7d_mentions, distinct_users,
            position_opened
        FROM signals
        {where_sql}
        ORDER BY signal_date DESC, created_at DESC
        LIMIT ? OFFSET ?
    """

    cursor.execute(query, params + [pagination.limit, pagination.offset])
    rows = cursor.fetchall()

    # Convert to dicts and add computed fields
    signals = []
    for row in rows:
        signal = _dict_from_row(row)

        # Add position_summary
        signal['position_summary'] = _compute_position_summary(db, signal['id'])

        # Add skip_reason
        signal['skip_reason'] = _compute_skip_reason(db, signal['id'], portfolio_id)

        signals.append(signal)

    return wrap_response(signals, total=total)


@router.get("/history")
async def get_signal_history(
    request: Request,
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    signal_type: Optional[str] = Query(None, description="Filter by signal type"),
    days: int = Query(14, ge=1, le=90, description="Number of days to look back (default 14)")
):
    """Get signal confidence history grouped by ticker.

    Returns confidence values over time for signals, optionally filtered by ticker
    and signal type. Default lookback period is 14 days.

    Query Parameters:
        ticker: Optional ticker symbol filter
        signal_type: Optional signal type filter (quality/consensus)
        days: Number of days to look back (default 14, max 90)

    Returns:
        Response envelope with list of ticker histories containing:
        - ticker: Ticker symbol
        - signal_type: Signal type
        - data_points: List of {signal_date, confidence} objects
    """
    db = request.app.state.db
    cursor = db.cursor()

    # Calculate date threshold
    date_threshold = (datetime.now() - timedelta(days=days)).date()

    # Build WHERE clause
    where_clauses = ["signal_date >= ?"]
    params = [date_threshold.isoformat()]

    if ticker:
        where_clauses.append("UPPER(ticker) = UPPER(?)")
        params.append(ticker)

    if signal_type:
        where_clauses.append("signal_type = ?")
        params.append(signal_type)

    where_sql = "WHERE " + " AND ".join(where_clauses)

    # Fetch signals grouped by ticker and signal_type
    query = f"""
        SELECT
            ticker, signal_type, signal_date, confidence
        FROM signals
        {where_sql}
        ORDER BY ticker, signal_type, signal_date ASC
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # Group by ticker and signal_type
    grouped = {}
    for row in rows:
        key = (row['ticker'], row['signal_type'])
        if key not in grouped:
            grouped[key] = {
                'ticker': row['ticker'],
                'signal_type': row['signal_type'],
                'data_points': []
            }
        grouped[key]['data_points'].append({
            'signal_date': row['signal_date'],
            'confidence': row['confidence']
        })

    # Convert to list
    history = list(grouped.values())

    return wrap_response(history, total=len(history))


@router.get("/{signal_id}")
async def get_signal(
    request: Request,
    signal_id: int
):
    """Get single signal by ID.

    Returns full signal data with all stored fields.

    Path Parameters:
        signal_id: Signal ID

    Returns:
        Response envelope with signal data

    Raises:
        404 NOT_FOUND: If signal ID does not exist
    """
    db = request.app.state.db
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT
            id, signal_date, created_at, updated_at, ticker, signal_type,
            sentiment_score, prediction, confidence, comment_count,
            has_reasoning, is_emergence, prior_7d_mentions, distinct_users,
            position_opened
        FROM signals
        WHERE id = ?
        """,
        (signal_id,)
    )

    row = cursor.fetchone()

    if not row:
        raise_api_error(NOT_FOUND, f"Signal with ID {signal_id} not found")

    signal = _dict_from_row(row)

    return wrap_response(signal)


@router.get("/{signal_id}/comments")
async def get_signal_comments(
    request: Request,
    signal_id: int,
    pagination: PaginationParams = Depends()
):
    """Get paginated comments for a signal.

    Returns comments with AI annotation fields (sentiment, sarcasm_flag,
    reasoning_indicator, confidence_score), author_trust_score, and
    ticker_sentiments from the junction table.

    Path Parameters:
        signal_id: Signal ID

    Query Parameters:
        limit: Maximum results to return (default 50, max 100)
        offset: Number of results to skip (default 0)

    Returns:
        Response envelope with list of comments and pagination metadata

    Raises:
        404 NOT_FOUND: If signal ID does not exist
    """
    db = request.app.state.db
    cursor = db.cursor()

    # Verify signal exists
    cursor.execute("SELECT id FROM signals WHERE id = ?", (signal_id,))
    if not cursor.fetchone():
        raise_api_error(NOT_FOUND, f"Signal with ID {signal_id} not found")

    # Count total comments for this signal
    cursor.execute(
        """
        SELECT COUNT(*) as total
        FROM signal_comments sc
        JOIN comments c ON sc.comment_id = c.id
        WHERE sc.signal_id = ?
        """,
        (signal_id,)
    )
    total = cursor.fetchone()['total']

    # Fetch paginated comments with author trust score
    cursor.execute(
        """
        SELECT
            c.id, c.reddit_id, c.author, c.body, c.created_utc,
            c.score, c.sentiment, c.sarcasm_detected, c.has_reasoning,
            c.reasoning_summary, c.ai_confidence, c.author_trust_score,
            a.avg_sentiment_accuracy
        FROM signal_comments sc
        JOIN comments c ON sc.comment_id = c.id
        LEFT JOIN authors a ON c.author = a.username
        WHERE sc.signal_id = ?
        ORDER BY c.created_utc DESC
        LIMIT ? OFFSET ?
        """,
        (signal_id, pagination.limit, pagination.offset)
    )
    rows = cursor.fetchall()

    # Build comment objects with ticker sentiments
    comments = []
    for row in rows:
        comment = _dict_from_row(row)

        # Fetch ticker sentiments from comment_tickers junction
        cursor.execute(
            """
            SELECT ticker, sentiment
            FROM comment_tickers
            WHERE comment_id = ?
            ORDER BY ticker
            """,
            (comment['id'],)
        )
        ticker_rows = cursor.fetchall()
        comment['ticker_sentiments'] = [
            {'ticker': t['ticker'], 'sentiment': t['sentiment']}
            for t in ticker_rows
        ]

        comments.append(comment)

    return wrap_response(comments, total=total)
