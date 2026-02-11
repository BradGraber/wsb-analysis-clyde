"""
Tests for story-007-002: Standard Response Envelope

These tests verify:
- Success responses: {data, meta: {timestamp, version}}
- Error responses: {error: {code, message}}
- 7 error codes defined
- Pydantic models for envelope, error, pagination
- Pagination: limit (default 50, max 100), offset (default 0)
- Paginated responses include meta.total
- Exception handlers return error envelope for 404, 422, 500
"""

import pytest
from pydantic import ValidationError


class TestResponseEnvelopeModels:
    """Verify Pydantic models for response envelope exist."""

    def test_success_envelope_model_exists(self):
        """ResponseEnvelope model should exist."""
        try:
            from src.api.models import ResponseEnvelope
            assert ResponseEnvelope is not None
        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_error_envelope_model_exists(self):
        """ErrorEnvelope model should exist."""
        try:
            from src.api.models import ErrorEnvelope
            assert ErrorEnvelope is not None
        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_pagination_model_exists(self):
        """PaginationParams model should exist."""
        try:
            from src.api.models import PaginationParams
            assert PaginationParams is not None
        except ImportError:
            pytest.skip("Implementation not available yet")


class TestSuccessEnvelope:
    """Verify success response envelope structure."""

    def test_success_envelope_has_data_field(self):
        """Success envelope should have 'data' field."""
        try:
            from src.api.models import ResponseEnvelope, MetaModel

            response = ResponseEnvelope(
                data={"test": "value"},
                meta=MetaModel(timestamp="2026-01-01T00:00:00Z", version="1.0")
            )

            assert hasattr(response, 'data'), "Should have 'data' field"
            assert response.data == {"test": "value"}

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_success_envelope_has_meta_field(self):
        """Success envelope should have 'meta' field with timestamp and version."""
        try:
            from src.api.models import ResponseEnvelope, MetaModel

            response = ResponseEnvelope(
                data=[],
                meta=MetaModel(timestamp="2026-01-01T00:00:00Z", version="1.0")
            )

            assert hasattr(response, 'meta'), "Should have 'meta' field"
            assert response.meta.timestamp == "2026-01-01T00:00:00Z"
            assert response.meta.version == "1.0"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_wrap_response_utility(self):
        """wrap_response should return proper envelope structure."""
        try:
            from src.api.responses import wrap_response

            result = wrap_response({"items": [1, 2, 3]}, total=42)

            assert "data" in result
            assert "meta" in result
            assert result["data"] == {"items": [1, 2, 3]}
            assert result["meta"]["version"] == "1.0"
            assert result["meta"]["total"] == 42
            assert "timestamp" in result["meta"]

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_wrap_response_without_total(self):
        """wrap_response without total should not include total in meta."""
        try:
            from src.api.responses import wrap_response

            result = wrap_response({"key": "val"})

            assert "data" in result
            assert "meta" in result
            assert "total" not in result["meta"]

        except ImportError:
            pytest.skip("Implementation not available yet")


class TestErrorEnvelope:
    """Verify error response envelope structure."""

    def test_error_envelope_has_error_field(self):
        """Error envelope should have 'error' field with code and message."""
        try:
            from src.api.models import ErrorEnvelope, ErrorDetail

            envelope = ErrorEnvelope(
                error=ErrorDetail(code="NOT_FOUND", message="Resource not found")
            )

            assert hasattr(envelope, 'error')
            assert envelope.error.code == "NOT_FOUND"
            assert envelope.error.message == "Resource not found"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_seven_error_codes_defined(self):
        """All 7 error codes should be defined."""
        try:
            from src.api import responses

            expected_codes = [
                'VALIDATION_ERROR',
                'NOT_FOUND',
                'ANALYSIS_ALREADY_RUNNING',
                'REDDIT_API_ERROR',
                'OPENAI_API_ERROR',
                'SCHWAB_AUTH_ERROR',
                'DATABASE_ERROR'
            ]

            for code in expected_codes:
                assert hasattr(responses, code), f"Error code {code} not defined"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_error_codes_map_to_status_codes(self):
        """Error codes should map to correct HTTP status codes."""
        try:
            from src.api.responses import ERROR_STATUS_CODES

            assert ERROR_STATUS_CODES["VALIDATION_ERROR"] == 422
            assert ERROR_STATUS_CODES["NOT_FOUND"] == 404
            assert ERROR_STATUS_CODES["ANALYSIS_ALREADY_RUNNING"] == 409
            assert ERROR_STATUS_CODES["DATABASE_ERROR"] == 500

        except ImportError:
            pytest.skip("Implementation not available yet")


class TestPagination:
    """Verify pagination parameters and behavior."""

    def test_pagination_params_model(self):
        """PaginationParams should have limit and offset with defaults."""
        try:
            from src.api.models import PaginationParams

            pagination = PaginationParams()

            assert pagination.limit == 50, "Default limit should be 50"
            assert pagination.offset == 0, "Default offset should be 0"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_pagination_max_limit(self):
        """Limit should be capped at 100."""
        try:
            from src.api.models import PaginationParams

            with pytest.raises(ValidationError):
                PaginationParams(limit=150, offset=0)

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_pagination_min_offset(self):
        """Offset should not be negative."""
        try:
            from src.api.models import PaginationParams

            with pytest.raises(ValidationError):
                PaginationParams(limit=50, offset=-1)

        except ImportError:
            pytest.skip("Implementation not available yet")


class TestExceptionHandlers:
    """Verify exception handlers return error envelopes."""

    def test_404_returns_error_envelope(self):
        """404 errors should return error envelope with NOT_FOUND code."""
        try:
            from src.api.app import app
            from fastapi.testclient import TestClient

            client = TestClient(app)
            response = client.get("/nonexistent/endpoint/12345")

            assert response.status_code == 404
            data = response.json()
            assert 'error' in data, "404 should return error envelope"
            assert data['error']['code'] == 'NOT_FOUND'
            assert 'message' in data['error']

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_raise_api_error_helper(self):
        """raise_api_error should raise HTTPException with proper structure."""
        try:
            from src.api.responses import raise_api_error, NOT_FOUND
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                raise_api_error(NOT_FOUND, "Item not found")

            assert exc_info.value.status_code == 404
            assert exc_info.value.detail["code"] == "NOT_FOUND"
            assert exc_info.value.detail["message"] == "Item not found"

        except ImportError:
            pytest.skip("Implementation not available yet")

    def test_version_is_1_0(self):
        """Version string should be hardcoded as '1.0'."""
        try:
            from src.api.responses import wrap_response

            result = wrap_response({})
            assert result["meta"]["version"] == "1.0"

        except ImportError:
            pytest.skip("Implementation not available yet")
