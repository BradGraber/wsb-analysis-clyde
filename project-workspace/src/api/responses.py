"""Response utilities and error handling for the API.

This module provides:
- Error code constants for consistent error handling across endpoints
- wrap_response() utility for creating standard response envelopes
- raise_api_error() helper for raising HTTP exceptions with error envelopes
- Error code to HTTP status code mappings

All API endpoints should use wrap_response() to return data and raise_api_error()
to signal errors. Exception handlers in app.py convert these to ErrorEnvelope format.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

from src.api.models import MetaModel


# Error Code Constants
# These codes are returned in the ErrorEnvelope.error.code field
VALIDATION_ERROR = "VALIDATION_ERROR"  # Invalid request parameters (422)
NOT_FOUND = "NOT_FOUND"  # Requested resource not found (404)
ANALYSIS_ALREADY_RUNNING = "ANALYSIS_ALREADY_RUNNING"  # Duplicate analysis attempt (409)
REDDIT_API_ERROR = "REDDIT_API_ERROR"  # Reddit API communication failure (502)
OPENAI_API_ERROR = "OPENAI_API_ERROR"  # OpenAI API communication failure (502)
SCHWAB_AUTH_ERROR = "SCHWAB_AUTH_ERROR"  # Schwab authentication/authorization failure (502)
DATABASE_ERROR = "DATABASE_ERROR"  # Database operation failure (500)


# Error Code to HTTP Status Code Mapping
ERROR_STATUS_CODES: Dict[str, int] = {
    VALIDATION_ERROR: 422,
    NOT_FOUND: 404,
    ANALYSIS_ALREADY_RUNNING: 409,
    REDDIT_API_ERROR: 502,
    OPENAI_API_ERROR: 502,
    SCHWAB_AUTH_ERROR: 502,
    DATABASE_ERROR: 500,
}


def wrap_response(data: Any, total: Optional[int] = None) -> Dict[str, Any]:
    """Wrap data in the standard response envelope.

    All API endpoints should return their data through this function to ensure
    consistent response structure across the API.

    Args:
        data: The response payload (any JSON-serializable type)
        total: Optional total count of items (used with pagination)

    Returns:
        Dict with response envelope structure:
        {
            "data": <data>,
            "meta": {
                "timestamp": "<ISO 8601 UTC timestamp>",
                "version": "1.0",
                "total": <total if provided>
            }
        }

    Example:
        @app.get("/items")
        async def list_items():
            items = [...fetch items...]
            return wrap_response(items, total=100)
    """
    meta = MetaModel(
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0",
        total=total
    )

    return {
        "data": data,
        "meta": meta.model_dump(exclude_none=True)
    }


def raise_api_error(code: str, message: str, status_code: Optional[int] = None) -> None:
    """Raise an HTTPException with consistent error envelope structure.

    This function provides a convenient way to raise API errors that will be
    formatted into ErrorEnvelope structure by the exception handlers in app.py.

    Args:
        code: Error code constant (e.g., VALIDATION_ERROR, NOT_FOUND)
        message: Human-readable error message
        status_code: Optional HTTP status code (defaults to mapped code for known errors)

    Raises:
        HTTPException with the specified status code and detail dict containing
        the error code and message.

    Example:
        if not item_exists:
            raise_api_error(NOT_FOUND, "Item with ID 123 not found")

        # With explicit status code
        raise_api_error("CUSTOM_ERROR", "Something went wrong", status_code=418)
    """
    # Use mapped status code if not explicitly provided
    if status_code is None:
        status_code = ERROR_STATUS_CODES.get(code, 500)

    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message}
    )
