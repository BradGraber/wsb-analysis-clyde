"""Pydantic models for API request/response structures.

This module defines the standard response and error envelopes used across all API endpoints,
as well as pagination parameters for list endpoints.

Response Structure:
    All successful responses use ResponseEnvelope with:
    - data: The actual response payload (any type)
    - meta: Metadata including timestamp, version, and optional total count

Error Structure:
    All error responses use ErrorEnvelope with:
    - error: ErrorDetail containing code and message

Pagination:
    List endpoints accept PaginationParams as a dependency for limit/offset query parameters.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class MetaModel(BaseModel):
    """Metadata included in all successful responses.

    Attributes:
        timestamp: ISO 8601 formatted UTC timestamp of the response
        version: API version string (currently hardcoded as "1.0")
        total: Optional total count of items (used with pagination)
    """
    timestamp: str
    version: str
    total: Optional[int] = None


class ResponseEnvelope(BaseModel):
    """Standard response envelope for all successful API responses.

    Attributes:
        data: The actual response payload (type varies by endpoint)
        meta: Metadata about the response (timestamp, version, total)
    """
    data: Any
    meta: MetaModel


class ErrorDetail(BaseModel):
    """Error details included in error responses.

    Attributes:
        code: Machine-readable error code (see responses.py for constants)
        message: Human-readable error message
    """
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    """Standard error envelope for all error responses.

    Attributes:
        error: Error details including code and message
    """
    error: ErrorDetail


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints.

    This class is used as a FastAPI dependency to accept limit and offset
    query parameters with validation and defaults.

    Attributes:
        limit: Maximum number of items to return (default 50, max 100)
        offset: Number of items to skip (default 0, min 0)

    Example:
        from fastapi import Depends

        @app.get("/items")
        async def list_items(pagination: PaginationParams = Depends()):
            # pagination.limit and pagination.offset are validated
            ...
    """
    limit: int = Field(default=50, ge=1, le=100, description="Maximum number of items to return")
    offset: int = Field(default=0, ge=0, description="Number of items to skip")
