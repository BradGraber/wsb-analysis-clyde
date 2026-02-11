"""FastAPI application entry point with lifespan, CORS, and structured logging.

This module initializes the FastAPI application with:
- Lifespan context manager for database connection lifecycle
- CORS middleware for Vue.js dev server
- Structured logging (JSON) to logs/backend.log
- Exception handlers for consistent error responses
- Basic health check endpoint

The database connection is managed via the lifespan context manager and stored
in app.state.db for access by route handlers throughout the application lifecycle.

All API responses follow the standard envelope format defined in src.api.models.

Usage:
    uvicorn src.api.app:app --reload
    or
    python -m uvicorn src.api.app:app --reload
"""

import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Dict

import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.models import ErrorEnvelope, ErrorDetail
from src.api.responses import (
    VALIDATION_ERROR, DATABASE_ERROR, NOT_FOUND,
    ERROR_STATUS_CODES,
)
from src.api.routes import signals, positions, portfolios, runs, system, auth
from src.backend.db.connection import get_connection
from src.backend.utils.logging_config import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for database connection lifecycle.

    Acquires a database connection on startup and stores it in app.state.db
    for access by route handlers. Closes the connection on shutdown.

    Args:
        app: FastAPI application instance

    Yields:
        None (context manager for startup/shutdown)
    """
    logger = get_logger(__name__)

    # Startup: acquire database connection
    db_path = os.environ.get('DB_PATH', './data/wsb.db')

    try:
        # Manually open connection (not using context manager since we need it to persist)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")

        # Store in app state
        app.state.db = conn

        logger.info("database_connection_acquired", db_path=db_path)

        yield

    finally:
        # Shutdown: close database connection
        if hasattr(app.state, 'db') and app.state.db is not None:
            app.state.db.close()
            logger.info("database_connection_closed")


# Initialize logging before creating the app
setup_logging(log_dir="logs", log_filename="backend.log")

# Create FastAPI application with lifespan
app = FastAPI(
    title="WSB Analysis Tool API",
    description="Backend API for Reddit WSB analysis, signal detection, and portfolio management",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for Vue.js dev server
# Read allowed origins from environment or use default
cors_origins = os.environ.get(
    'CORS_ORIGINS',
    'http://localhost:5173'
).split(',')

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = get_logger(__name__)
logger.info("fastapi_app_initialized", cors_origins=cors_origins)

# Include routers
app.include_router(signals.router)
app.include_router(positions.router)
app.include_router(portfolios.router)
app.include_router(portfolios.evaluation_router)
app.include_router(runs.router)
app.include_router(system.router)
app.include_router(auth.router)

# Exception Handlers
# These handlers convert exceptions to the standard ErrorEnvelope format


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI request validation errors (422).

    Converts Pydantic validation errors into the standard ErrorEnvelope format.

    Args:
        request: The incoming request
        exc: The validation error exception

    Returns:
        JSONResponse with ErrorEnvelope structure and 422 status code
    """
    logger = get_logger(__name__)
    logger.warning("validation_error", path=request.url.path, errors=exc.errors())

    error_envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=VALIDATION_ERROR,
            message=f"Request validation failed: {exc.errors()[0]['msg']}"
        )
    )

    return JSONResponse(
        status_code=422,
        content=error_envelope.model_dump(),
        headers={"Content-Type": "application/json"}
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTPException with error envelope format.

    Routes exceptions raised via raise_api_error() or raw HTTPException
    into the standard ErrorEnvelope structure.
    """
    logger = get_logger(__name__)
    logger.warning("http_exception", path=request.url.path, status=exc.status_code)

    # If detail is a dict with code/message (from raise_api_error), use it
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        code = exc.detail["code"]
        message = exc.detail["message"]
    else:
        # Map status code to error code for generic HTTPExceptions
        code_map = {404: NOT_FOUND, 422: VALIDATION_ERROR, 409: "ANALYSIS_ALREADY_RUNNING"}
        code = code_map.get(exc.status_code, DATABASE_ERROR)
        message = str(exc.detail) if exc.detail else "An error occurred"

    error_envelope = ErrorEnvelope(
        error=ErrorDetail(code=code, message=message)
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope.model_dump(),
        headers={"Content-Type": "application/json"}
    )


@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle 404 Not Found errors.

    Converts generic 404 errors into the standard ErrorEnvelope format.

    Args:
        request: The incoming request
        exc: The exception

    Returns:
        JSONResponse with ErrorEnvelope structure and 404 status code
    """
    logger = get_logger(__name__)
    logger.warning("not_found", path=request.url.path)

    error_envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=NOT_FOUND,
            message=f"Resource not found: {request.url.path}"
        )
    )

    return JSONResponse(
        status_code=404,
        content=error_envelope.model_dump(),
        headers={"Content-Type": "application/json"}
    )


@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle 500 Internal Server Error.

    Converts uncaught server errors into the standard ErrorEnvelope format.

    Args:
        request: The incoming request
        exc: The exception

    Returns:
        JSONResponse with ErrorEnvelope structure and 500 status code
    """
    logger = get_logger(__name__)
    logger.error(
        "internal_server_error",
        path=request.url.path,
        error=str(exc),
        traceback=traceback.format_exc(),
    )

    error_envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=DATABASE_ERROR,
            message="An internal server error occurred"
        )
    )

    return JSONResponse(
        status_code=500,
        content=error_envelope.model_dump(),
        headers={"Content-Type": "application/json"}
    )


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint for basic health check.

    Returns:
        Dict with status and message

    Example:
        GET / -> {"status": "ok", "message": "WSB Analysis Tool API"}
    """
    return {
        "status": "ok",
        "message": "WSB Analysis Tool API"
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint.

    Returns:
        Dict with status indicator

    Example:
        GET /health -> {"status": "healthy"}
    """
    return {"status": "healthy"}
