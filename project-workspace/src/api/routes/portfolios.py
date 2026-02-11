"""Portfolio and evaluation period API endpoints.

This module provides GET endpoints for portfolio and evaluation period data:
- GET /portfolios: List all portfolios with computed summary statistics
- GET /portfolios/{id}: Get single portfolio with allocation breakdown
- GET /evaluation-periods: Get evaluation periods (requires portfolio_id filter)
"""

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, Query, Depends

from src.api.responses import wrap_response, raise_api_error, NOT_FOUND, VALIDATION_ERROR
from src.backend.utils.logging_config import get_logger

router = APIRouter(prefix="/portfolios", tags=["portfolios"])
logger = get_logger(__name__)


def _dict_from_row(row) -> Dict[str, Any]:
    """Convert sqlite3.Row to dict."""
    return dict(row) if row else None


def _compute_portfolio_summary(db, portfolio_id: int, portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Compute summary statistics for a portfolio.

    Computes the following fields from the positions table:
    - value: sum of (entry_price * shares_remaining) for open stock positions +
             sum of (premium_paid * contracts_remaining * 100) for open option positions
    - open_position_count: count of open positions
    - total_pnl: sum of realized_pnl from all position_exits
    - total_pnl_pct: (total_pnl / starting_capital) * 100

    Args:
        db: Database connection
        portfolio_id: Portfolio ID
        portfolio: Portfolio dict with starting_capital and cash_available

    Returns:
        Dict with computed summary fields
    """
    cursor = db.cursor()

    # Compute value from open positions
    # For stocks: sum of (entry_price * shares_remaining)
    cursor.execute(
        """
        SELECT COALESCE(SUM(entry_price * shares_remaining), 0) as stock_value
        FROM positions
        WHERE portfolio_id = ? AND status = 'open' AND instrument_type = 'stock'
        """,
        (portfolio_id,)
    )
    stock_value = cursor.fetchone()['stock_value']

    # For options: sum of (premium_paid * contracts_remaining * 100)
    cursor.execute(
        """
        SELECT COALESCE(SUM(premium_paid * contracts_remaining * 100), 0) as option_value
        FROM positions
        WHERE portfolio_id = ? AND status = 'open' AND instrument_type = 'option'
        """,
        (portfolio_id,)
    )
    option_value = cursor.fetchone()['option_value']

    value = stock_value + option_value

    # Count open positions
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM positions
        WHERE portfolio_id = ? AND status = 'open'
        """,
        (portfolio_id,)
    )
    open_position_count = cursor.fetchone()['count']

    # Sum total realized PnL from position_exits
    cursor.execute(
        """
        SELECT COALESCE(SUM(pe.realized_pnl), 0) as total_pnl
        FROM position_exits pe
        JOIN positions p ON pe.position_id = p.id
        WHERE p.portfolio_id = ?
        """,
        (portfolio_id,)
    )
    total_pnl = cursor.fetchone()['total_pnl']

    # Compute total_pnl_pct
    starting_capital = portfolio.get('starting_capital', 0)
    if starting_capital and starting_capital > 0:
        total_pnl_pct = (total_pnl / starting_capital) * 100
    else:
        total_pnl_pct = 0.0

    return {
        'value': value,
        'cash': portfolio.get('cash_available', 0.0),
        'open_position_count': open_position_count,
        'total_pnl': total_pnl,
        'total_pnl_pct': total_pnl_pct
    }


def _compute_allocation_breakdown(db, portfolio_id: int) -> List[Dict[str, Any]]:
    """Compute allocation breakdown by ticker for a portfolio.

    Groups open positions by ticker and returns aggregate statistics.

    Args:
        db: Database connection
        portfolio_id: Portfolio ID

    Returns:
        List of dicts with ticker, total_value, position_count, avg_unrealized_return_pct
    """
    cursor = db.cursor()

    # Group open positions by ticker
    # For stocks: value = entry_price * shares_remaining
    # For options: value = premium_paid * contracts_remaining * 100
    cursor.execute(
        """
        SELECT
            ticker,
            COUNT(*) as position_count,
            SUM(
                CASE
                    WHEN instrument_type = 'stock' THEN entry_price * shares_remaining
                    WHEN instrument_type = 'option' THEN premium_paid * contracts_remaining * 100
                    ELSE 0
                END
            ) as total_value
        FROM positions
        WHERE portfolio_id = ? AND status = 'open'
        GROUP BY ticker
        ORDER BY total_value DESC
        """,
        (portfolio_id,)
    )

    rows = cursor.fetchall()
    breakdown = []

    for row in rows:
        ticker_data = _dict_from_row(row)
        breakdown.append(ticker_data)

    return breakdown


@router.get("")
async def list_portfolios(request: Request):
    """List all portfolios with computed summary statistics.

    Returns all 4 portfolios with the following computed fields:
    - value: Total value of open positions
    - cash: Cash available in the portfolio
    - open_position_count: Number of open positions
    - total_pnl: Total realized profit/loss from all exits
    - total_pnl_pct: Total PnL as percentage of starting capital

    This endpoint does not paginate (fixed 4 portfolios) but uses the response envelope.

    Returns:
        Response envelope with list of portfolios
    """
    db = request.app.state.db
    cursor = db.cursor()

    logger.info("list_portfolios_request")

    # Fetch all portfolios
    cursor.execute(
        """
        SELECT
            id, name, instrument_type, signal_type, starting_capital,
            current_value, cash_available, created_at
        FROM portfolios
        ORDER BY id ASC
        """
    )
    rows = cursor.fetchall()

    # Convert to dicts and add computed summary
    portfolios = []
    for row in rows:
        portfolio = _dict_from_row(row)

        # Add computed summary statistics
        summary = _compute_portfolio_summary(db, portfolio['id'], portfolio)
        portfolio.update(summary)

        portfolios.append(portfolio)

    logger.info("list_portfolios_response", count=len(portfolios))

    return wrap_response(portfolios)


@router.get("/{portfolio_id}")
async def get_portfolio(request: Request, portfolio_id: int):
    """Get single portfolio by ID with allocation breakdown.

    Returns complete portfolio data including:
    - All database fields
    - Computed summary statistics (value, cash, open_position_count, total_pnl, total_pnl_pct)
    - Allocation breakdown: grouped open positions by ticker with total value and position count

    Path Parameters:
        portfolio_id: Portfolio ID

    Returns:
        Response envelope with portfolio data

    Raises:
        404 NOT_FOUND: If portfolio ID does not exist
    """
    db = request.app.state.db
    cursor = db.cursor()

    logger.info("get_portfolio_request", portfolio_id=portfolio_id)

    # Fetch portfolio
    cursor.execute(
        """
        SELECT
            id, name, instrument_type, signal_type, starting_capital,
            current_value, cash_available, created_at
        FROM portfolios
        WHERE id = ?
        """,
        (portfolio_id,)
    )

    row = cursor.fetchone()

    if not row:
        logger.warning("portfolio_not_found", portfolio_id=portfolio_id)
        raise_api_error(NOT_FOUND, f"Portfolio with ID {portfolio_id} not found")

    portfolio = _dict_from_row(row)

    # Add computed summary statistics
    summary = _compute_portfolio_summary(db, portfolio['id'], portfolio)
    portfolio.update(summary)

    # Add allocation breakdown
    portfolio['allocation_breakdown'] = _compute_allocation_breakdown(db, portfolio_id)

    logger.info(
        "get_portfolio_response",
        portfolio_id=portfolio_id,
        name=portfolio['name'],
        open_positions=portfolio['open_position_count'],
        allocation_tickers=len(portfolio['allocation_breakdown'])
    )

    return wrap_response(portfolio)


# Evaluation periods endpoint (separate router prefix)
evaluation_router = APIRouter(prefix="/evaluation-periods", tags=["evaluation"])


@evaluation_router.get("")
async def list_evaluation_periods(
    request: Request,
    portfolio_id: Optional[int] = Query(None, description="Filter by portfolio ID (required)")
):
    """Get evaluation periods filtered by portfolio_id.

    Returns both active and completed evaluation periods with performance metrics
    for the specified portfolio.

    Query Parameters:
        portfolio_id: Portfolio ID (required)

    Returns:
        Response envelope with list of evaluation periods

    Raises:
        422 VALIDATION_ERROR: If portfolio_id parameter is missing
    """
    db = request.app.state.db
    cursor = db.cursor()

    logger.info("list_evaluation_periods_request", portfolio_id=portfolio_id)

    # Validate required parameter
    if portfolio_id is None:
        logger.warning("evaluation_periods_missing_portfolio_id")
        raise_api_error(
            VALIDATION_ERROR,
            "Query parameter 'portfolio_id' is required for evaluation periods endpoint"
        )

    # Fetch evaluation periods for the portfolio
    cursor.execute(
        """
        SELECT
            id, portfolio_id, period_start, period_end, instrument_type,
            signal_type, status, portfolio_return_pct, sp500_return_pct,
            relative_performance, beat_benchmark, total_positions_closed,
            winning_positions, losing_positions, avg_return_pct,
            signal_accuracy_pct, value_at_period_start, created_at
        FROM evaluation_periods
        WHERE portfolio_id = ?
        ORDER BY period_start DESC
        """,
        (portfolio_id,)
    )

    rows = cursor.fetchall()

    # Convert to dicts
    periods = [_dict_from_row(row) for row in rows]

    logger.info("list_evaluation_periods_response", portfolio_id=portfolio_id, count=len(periods))

    return wrap_response(periods, total=len(periods))
