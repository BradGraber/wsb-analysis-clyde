"""Position-related API endpoints.

This module provides GET endpoints for position data:
- GET /positions: List positions with filters and computed convenience fields
- GET /positions/{id}: Get single position with exit strategy state and exit history
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, Query, Depends

from src.api.models import PaginationParams
from src.api.responses import wrap_response, raise_api_error, NOT_FOUND
from src.backend.utils.logging_config import get_logger

router = APIRouter(prefix="/positions", tags=["positions"])
logger = get_logger(__name__)


def _dict_from_row(row) -> Dict[str, Any]:
    """Convert sqlite3.Row to dict."""
    return dict(row) if row else None


def _get_current_price(db, ticker: str, instrument_type: str) -> Optional[float]:
    """Get the most recent price from price_history.

    Args:
        db: Database connection
        ticker: Ticker symbol
        instrument_type: 'stock' or 'option'

    Returns:
        Most recent close price or None if not available
    """
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT close
        FROM price_history
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT 1
        """,
        (ticker,)
    )

    row = cursor.fetchone()
    return row['close'] if row else None


def _compute_convenience_fields(db, position: Dict[str, Any]) -> Dict[str, Any]:
    """Compute on-demand convenience fields for a position.

    Computes the following fields based on position type and status:
    - current_price: Latest price from price_history
    - unrealized_return_pct: Percentage return for open positions
    - nearest_exit_distance_pct: Distance to closest exit target
    - hold_days: Days since entry
    - dte: Days to expiration (options only)
    - premium_change_pct: Premium change percentage (options only)

    Args:
        db: Database connection
        position: Position dict from database

    Returns:
        Dictionary with computed fields (may include None values)
    """
    result = {}

    # Get current price
    current_price = _get_current_price(db, position['ticker'], position['instrument_type'])
    result['current_price'] = current_price

    # Only compute return/distance fields for open positions
    if position['status'] == 'open' and current_price is not None:
        entry_price = position['entry_price']

        # Unrealized return percentage
        if entry_price and entry_price > 0:
            result['unrealized_return_pct'] = ((current_price - entry_price) / entry_price) * 100
        else:
            result['unrealized_return_pct'] = None

        # Nearest exit distance percentage
        distances = []

        # Distance to stop loss
        if position['stop_loss_price'] is not None and position['stop_loss_price'] > 0:
            stop_distance = abs((current_price - position['stop_loss_price']) / current_price) * 100
            distances.append(stop_distance)

        # Distance to take profit
        if position['take_profit_price'] is not None and position['take_profit_price'] > 0:
            tp_distance = abs((position['take_profit_price'] - current_price) / current_price) * 100
            distances.append(tp_distance)

        result['nearest_exit_distance_pct'] = min(distances) if distances else None
    else:
        # Closed positions don't have unrealized returns or exit distances
        result['unrealized_return_pct'] = None
        result['nearest_exit_distance_pct'] = None

    # Hold days (applicable to all positions)
    if position['entry_date']:
        try:
            entry = datetime.strptime(position['entry_date'], '%Y-%m-%d').date()
            today = date.today()
            result['hold_days'] = (today - entry).days
        except (ValueError, TypeError):
            result['hold_days'] = None
    else:
        result['hold_days'] = None

    # Options-specific fields
    if position['instrument_type'] == 'option':
        # Days to expiration
        if position['expiration_date']:
            try:
                expiration = datetime.strptime(position['expiration_date'], '%Y-%m-%d').date()
                today = date.today()
                result['dte'] = (expiration - today).days
            except (ValueError, TypeError):
                result['dte'] = None
        else:
            result['dte'] = None

        # Premium change percentage (for open positions with current price)
        if position['status'] == 'open' and current_price is not None:
            if position['premium_paid'] and position['premium_paid'] > 0:
                result['premium_change_pct'] = ((current_price - position['premium_paid']) / position['premium_paid']) * 100
            else:
                result['premium_change_pct'] = None
        else:
            result['premium_change_pct'] = None
    else:
        # Stock positions don't have these fields
        result['dte'] = None
        result['premium_change_pct'] = None

    return result


def _get_position_exits(db, position_id: int) -> List[Dict[str, Any]]:
    """Get all position_exits records for a position.

    Args:
        db: Database connection
        position_id: Position ID

    Returns:
        List of position exit dicts
    """
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT
            id, position_id, exit_date, exit_price, exit_reason,
            quantity_pct, shares_exited, contracts_exited, realized_pnl,
            created_at
        FROM position_exits
        WHERE position_id = ?
        ORDER BY exit_date DESC, created_at DESC
        """,
        (position_id,)
    )

    rows = cursor.fetchall()
    return [_dict_from_row(row) for row in rows]


@router.get("")
async def list_positions(
    request: Request,
    portfolio_id: Optional[int] = Query(None, description="Filter by portfolio ID"),
    status: Optional[str] = Query(None, description="Filter by status (open/closed)"),
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    instrument_type: Optional[str] = Query(None, description="Filter by instrument type (stock/option)"),
    signal_type: Optional[str] = Query(None, description="Filter by signal type (quality/consensus)"),
    pagination: PaginationParams = Depends()
):
    """List positions with filters, pagination, and computed convenience fields.

    Returns paginated positions with on-demand computed fields:
    - current_price: Latest price from price_history
    - unrealized_return_pct: Percentage return (open positions only)
    - nearest_exit_distance_pct: Distance to closest exit target (open positions only)
    - hold_days: Days since entry
    - dte: Days to expiration (options only)
    - premium_change_pct: Premium change percentage (options only)

    Also includes nested position_exits array for each position.

    Query Parameters:
        portfolio_id: Filter by portfolio ID
        status: Filter by status (open/closed)
        ticker: Filter by ticker symbol (exact match, case-insensitive)
        instrument_type: Filter by instrument type (stock/option)
        signal_type: Filter by signal type (quality/consensus)
        limit: Maximum results to return (default 50, max 100)
        offset: Number of results to skip (default 0)

    Returns:
        Response envelope with list of positions and pagination metadata
    """
    db = request.app.state.db
    cursor = db.cursor()

    logger.info(
        "list_positions_request",
        portfolio_id=portfolio_id,
        status=status,
        ticker=ticker,
        instrument_type=instrument_type,
        signal_type=signal_type,
        limit=pagination.limit,
        offset=pagination.offset
    )

    # Build WHERE clause dynamically
    where_clauses = []
    params = []

    if portfolio_id is not None:
        where_clauses.append("portfolio_id = ?")
        params.append(portfolio_id)

    if status:
        where_clauses.append("status = ?")
        params.append(status)

    if ticker:
        where_clauses.append("UPPER(ticker) = UPPER(?)")
        params.append(ticker)

    if instrument_type:
        where_clauses.append("instrument_type = ?")
        params.append(instrument_type)

    if signal_type:
        where_clauses.append("signal_type = ?")
        params.append(signal_type)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Count total matching positions
    count_query = f"SELECT COUNT(*) as total FROM positions {where_sql}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()['total']

    # Fetch paginated positions
    query = f"""
        SELECT
            id, portfolio_id, signal_id, ticker, instrument_type, signal_type,
            direction, confidence, position_size, entry_date, entry_price, status,
            shares, shares_remaining,
            stop_loss_price, take_profit_price, peak_price, trailing_stop_active,
            time_extension,
            option_type, strike_price, expiration_date, contracts, contracts_remaining,
            premium_paid, peak_premium, underlying_price_at_entry,
            exit_date, exit_reason, hold_days, realized_return_pct
        FROM positions
        {where_sql}
        ORDER BY entry_date DESC, id DESC
        LIMIT ? OFFSET ?
    """

    cursor.execute(query, params + [pagination.limit, pagination.offset])
    rows = cursor.fetchall()

    # Convert to dicts and add computed fields
    positions = []
    for row in rows:
        position = _dict_from_row(row)

        # Add computed convenience fields
        convenience_fields = _compute_convenience_fields(db, position)
        position.update(convenience_fields)

        # Add position exits as nested array
        position['position_exits'] = _get_position_exits(db, position['id'])

        positions.append(position)

    logger.info("list_positions_response", total=total, returned=len(positions))

    return wrap_response(positions, total=total)


@router.get("/{position_id}")
async def get_position(
    request: Request,
    position_id: int
):
    """Get single position by ID with exit strategy state and full exit history.

    Returns complete position data including:
    - All database fields (including exit strategy state like stop_loss_price, trailing_stop_active)
    - Computed convenience fields (current_price, unrealized_return_pct, etc.)
    - Complete position_exits history as nested array

    Path Parameters:
        position_id: Position ID

    Returns:
        Response envelope with position data

    Raises:
        404 NOT_FOUND: If position ID does not exist
    """
    db = request.app.state.db
    cursor = db.cursor()

    logger.info("get_position_request", position_id=position_id)

    cursor.execute(
        """
        SELECT
            id, portfolio_id, signal_id, ticker, instrument_type, signal_type,
            direction, confidence, position_size, entry_date, entry_price, status,
            shares, shares_remaining,
            stop_loss_price, take_profit_price, peak_price, trailing_stop_active,
            time_extension,
            option_type, strike_price, expiration_date, contracts, contracts_remaining,
            premium_paid, peak_premium, underlying_price_at_entry,
            exit_date, exit_reason, hold_days, realized_return_pct
        FROM positions
        WHERE id = ?
        """,
        (position_id,)
    )

    row = cursor.fetchone()

    if not row:
        logger.warning("position_not_found", position_id=position_id)
        raise_api_error(NOT_FOUND, f"Position with ID {position_id} not found")

    position = _dict_from_row(row)

    # Add computed convenience fields
    convenience_fields = _compute_convenience_fields(db, position)
    position.update(convenience_fields)

    # Add complete position exits history
    position['position_exits'] = _get_position_exits(db, position_id)

    logger.info(
        "get_position_response",
        position_id=position_id,
        ticker=position['ticker'],
        status=position['status'],
        exits_count=len(position['position_exits'])
    )

    return wrap_response(position)
