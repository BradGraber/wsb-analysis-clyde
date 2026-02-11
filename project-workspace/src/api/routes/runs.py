"""Analysis run-related API endpoints.

This module provides GET endpoints for analysis run data:
- GET /runs: List analysis runs with timestamps and status
- GET /runs/{id}/status: Polling-optimized run status endpoint
"""

import json
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, Depends

from src.api.models import PaginationParams
from src.api.responses import wrap_response, raise_api_error, NOT_FOUND
from src.backend.utils.logging_config import get_logger

router = APIRouter(prefix="/runs", tags=["analysis"])
logger = get_logger(__name__)


def _dict_from_row(row) -> Dict[str, Any]:
    """Convert sqlite3.Row to dict."""
    return dict(row) if row else None


def _get_phase_label(phase: Optional[int]) -> str:
    """Get human-readable label for current_phase.

    Args:
        phase: Phase number (1-7) or None

    Returns:
        Human-readable phase label
    """
    phase_labels = {
        1: "Acquisition",
        2: "Prioritization",
        3: "Analysis",
        4: "Signal Detection",
        5: "Position Management",
        6: "Price Monitoring",
        7: "Post-Analysis"
    }

    return phase_labels.get(phase, "Unknown") if phase is not None else "Not started"


def _get_run_warnings(db, run_id: int) -> List[str]:
    """Get warnings array from analysis_runs.warnings field.

    The warnings field is a JSON array stored as TEXT. Parse it and return
    as a Python list.

    Args:
        db: Database connection
        run_id: Analysis run ID

    Returns:
        List of warning strings (empty list if none)
    """
    cursor = db.cursor()

    cursor.execute(
        "SELECT warnings FROM analysis_runs WHERE id = ?",
        (run_id,)
    )

    row = cursor.fetchone()

    if not row or not row['warnings']:
        return []

    try:
        # Parse JSON array from TEXT field
        warnings = json.loads(row['warnings'])
        return warnings if isinstance(warnings, list) else []
    except (json.JSONDecodeError, TypeError):
        logger.warning("failed_to_parse_warnings", run_id=run_id, warnings=row['warnings'])
        return []


@router.get("")
async def list_runs(
    request: Request,
    pagination: PaginationParams = Depends()
):
    """List analysis runs with pagination.

    Returns paginated analysis runs ordered by most recent first.
    Each run includes timestamps (started_at, completed_at) and status.

    Query Parameters:
        limit: Maximum results to return (default 50, max 100)
        offset: Number of results to skip (default 0)

    Returns:
        Response envelope with list of analysis runs and pagination metadata
    """
    db = request.app.state.db
    cursor = db.cursor()

    logger.info(
        "list_runs_request",
        limit=pagination.limit,
        offset=pagination.offset
    )

    # Count total runs
    cursor.execute("SELECT COUNT(*) as total FROM analysis_runs")
    total = cursor.fetchone()['total']

    # Fetch paginated runs
    cursor.execute(
        """
        SELECT
            id, status, current_phase, current_phase_label,
            started_at, completed_at, error_message,
            signals_created, positions_opened, exits_triggered
        FROM analysis_runs
        ORDER BY started_at DESC
        LIMIT ? OFFSET ?
        """,
        (pagination.limit, pagination.offset)
    )

    rows = cursor.fetchall()
    runs = [_dict_from_row(row) for row in rows]

    logger.info("list_runs_response", total=total, returned=len(runs))

    return wrap_response(runs, total=total)


@router.get("/{run_id}/status")
async def get_run_status(
    request: Request,
    run_id: int
):
    """Get polling-optimized run status for frontend.

    This endpoint is optimized for frontend polling (10-second intervals).
    Returns current status, phase information, progress, results summary,
    and warnings array.

    Path Parameters:
        run_id: Analysis run ID

    Returns:
        Response envelope with run status data:
        - status: Current run status (running/completed/failed)
        - current_phase: Current phase number (1-7)
        - phase_label: Human-readable phase label
        - progress_current: Current progress within phase
        - progress_total: Total items in current phase
        - results: Summary of results (signals_created, positions_opened, exits_triggered)
        - warnings: Array of warning strings

    Raises:
        404 NOT_FOUND: If run ID does not exist
    """
    db = request.app.state.db
    cursor = db.cursor()

    logger.info("get_run_status_request", run_id=run_id)

    # Fetch run data
    cursor.execute(
        """
        SELECT
            id, status, current_phase, current_phase_label,
            progress_current, progress_total,
            started_at, completed_at, error_message,
            signals_created, positions_opened, exits_triggered
        FROM analysis_runs
        WHERE id = ?
        """,
        (run_id,)
    )

    row = cursor.fetchone()

    if not row:
        logger.warning("run_not_found", run_id=run_id)
        raise_api_error(NOT_FOUND, f"Analysis run with ID {run_id} not found")

    run = _dict_from_row(row)

    # Get warnings array
    warnings = _get_run_warnings(db, run_id)

    # Construct polling-optimized response
    response = {
        "status": run['status'],
        "current_phase": run['current_phase'],
        "phase_label": _get_phase_label(run['current_phase']),
        "progress_current": run['progress_current'],
        "progress_total": run['progress_total'],
        "results": {
            "signals_created": run['signals_created'] or 0,
            "positions_opened": run['positions_opened'] or 0,
            "exits_triggered": run['exits_triggered'] or 0
        },
        "warnings": warnings
    }

    logger.info(
        "get_run_status_response",
        run_id=run_id,
        status=run['status'],
        current_phase=run['current_phase'],
        warnings_count=len(warnings)
    )

    return wrap_response(response)
