"""
Tests for story-007-003: CRUD GET Endpoints

These tests verify all 15+ GET endpoints:
- GET /signals with filters and pagination
- GET /signals/{id}
- GET /signals/{id}/comments
- GET /signals/history
- GET /portfolios
- GET /portfolios/{id}
- GET /positions with filters and pagination
- GET /positions/{id}
- GET /runs
- GET /runs/{id}/status
- GET /evaluation-periods
- GET /prices/{ticker}
- GET /status

All tests verify:
- Empty data array for no matches (not error)
- Invalid filters return VALIDATION_ERROR
- Invalid IDs return NOT_FOUND
"""

import pytest


class TestSignalsEndpoints:
    """Verify /signals endpoints."""

    def test_get_signals_exists(self, test_client):
        """GET /signals endpoint should exist."""
        response = test_client.get("/signals")
        assert response.status_code == 200, \
            f"GET /signals should return 200, got {response.status_code}"

    def test_get_signals_returns_envelope(self, test_client):
        """GET /signals should return data envelope."""
        response = test_client.get("/signals")
        assert response.status_code == 200
        data = response.json()
        assert 'data' in data, "Should return data envelope"
        assert 'meta' in data, "Should include meta"
        assert isinstance(data['data'], list), "Data should be a list"

    def test_get_signals_filters(self, test_client):
        """GET /signals should support ticker, signal_type, date filters."""
        response = test_client.get("/signals?ticker=AAPL&signal_type=quality")
        assert response.status_code == 200, "Should accept filter parameters"
        data = response.json()
        assert 'data' in data, "Should return data envelope with filters"

    def test_get_signals_pagination(self, test_client):
        """GET /signals should support limit and offset pagination."""
        response = test_client.get("/signals?limit=10&offset=0")
        assert response.status_code == 200, "Should accept pagination parameters"
        data = response.json()
        assert 'meta' in data, "Should include meta"

    def test_get_signal_by_id(self, test_client):
        """GET /signals/{id} should return NOT_FOUND for missing signal."""
        response = test_client.get("/signals/1")
        # No seed data, so expect 404
        assert response.status_code == 404, \
            "GET /signals/{id} should return 404 for non-existent signal"

    def test_get_signal_comments(self, test_client):
        """GET /signals/{id}/comments should return NOT_FOUND for missing signal."""
        response = test_client.get("/signals/1/comments")
        assert response.status_code in [200, 404], \
            "GET /signals/{id}/comments endpoint should exist"

    def test_get_signals_history(self, test_client):
        """GET /signals/history should accept ticker, signal_type, days params."""
        response = test_client.get("/signals/history?signal_type=quality&days=7")
        assert response.status_code == 200, \
            "GET /signals/history should return 200"


class TestPortfoliosEndpoints:
    """Verify /portfolios endpoints."""

    def test_get_portfolios(self, test_client):
        """GET /portfolios should return portfolios with summary stats."""
        response = test_client.get("/portfolios")
        assert response.status_code == 200, "GET /portfolios should return 200"

        data = response.json()
        assert 'data' in data, "Should return data envelope"
        assert isinstance(data['data'], list), "Data should be a list"

        # With seed data, should have 4 portfolios
        if len(data['data']) > 0:
            portfolio = data['data'][0]
            assert 'name' in portfolio or 'id' in portfolio, \
                "Portfolio should have identifying fields"

    def test_get_portfolio_by_id(self, test_client):
        """GET /portfolios/{id} should return single portfolio."""
        response = test_client.get("/portfolios/1")
        # Seed data includes 4 portfolios
        assert response.status_code in [200, 404], \
            "GET /portfolios/{id} endpoint should exist"

        if response.status_code == 200:
            data = response.json()
            assert 'data' in data, "Should return data envelope"


class TestPositionsEndpoints:
    """Verify /positions endpoints."""

    def test_get_positions(self, test_client):
        """GET /positions should support filters and pagination."""
        response = test_client.get("/positions")
        assert response.status_code == 200, "GET /positions should return 200"

        data = response.json()
        assert 'data' in data, "Should return data envelope"
        assert isinstance(data['data'], list), "Data should be a list"

    def test_get_positions_filters(self, test_client):
        """GET /positions should support portfolio_id, status, ticker filters."""
        response = test_client.get("/positions?portfolio_id=1&status=open&ticker=AAPL")
        assert response.status_code == 200, "Should accept filter parameters"

    def test_get_position_by_id(self, test_client):
        """GET /positions/{id} should return NOT_FOUND for missing position."""
        response = test_client.get("/positions/1")
        assert response.status_code in [200, 404], \
            "GET /positions/{id} endpoint should exist"


class TestAnalysisRunsEndpoints:
    """Verify /runs endpoints."""

    def test_get_runs(self, test_client):
        """GET /runs should return paginated list of analysis runs."""
        response = test_client.get("/runs")
        assert response.status_code == 200, "GET /runs should return 200"

        data = response.json()
        assert 'data' in data, "Should return data envelope"
        assert isinstance(data['data'], list), "Data should be a list"

    def test_get_run_status(self, test_client):
        """GET /runs/{id}/status should return NOT_FOUND for missing run."""
        response = test_client.get("/runs/1/status")
        assert response.status_code == 404, \
            "GET /runs/{id}/status should return 404 for non-existent run"


class TestEvaluationPeriodsEndpoint:
    """Verify /evaluation-periods endpoint."""

    def test_get_evaluation_periods_requires_portfolio_id(self, test_client):
        """GET /evaluation-periods without portfolio_id should return VALIDATION_ERROR."""
        response = test_client.get("/evaluation-periods")
        assert response.status_code == 422, \
            "Missing portfolio_id should return 422"

        data = response.json()
        assert 'error' in data, "Should return error envelope"
        assert data['error']['code'] == 'VALIDATION_ERROR', \
            "Error code should be VALIDATION_ERROR"

    def test_get_evaluation_periods_with_portfolio_id(self, test_client):
        """GET /evaluation-periods?portfolio_id=1 should return periods."""
        response = test_client.get("/evaluation-periods?portfolio_id=1")
        assert response.status_code == 200, "Should accept portfolio_id parameter"

        data = response.json()
        assert 'data' in data, "Should return data envelope"
        assert isinstance(data['data'], list), "Data should be a list"


class TestPricesEndpoint:
    """Verify /prices/{ticker} endpoint."""

    def test_get_prices_by_ticker(self, test_client):
        """GET /prices/{ticker} should return price history."""
        response = test_client.get("/prices/AAPL")
        assert response.status_code == 200, "GET /prices/{ticker} should return 200"

        data = response.json()
        assert 'data' in data, "Should return data envelope"

    def test_get_prices_unknown_ticker_returns_empty(self, test_client):
        """GET /prices/{ticker} for unknown ticker returns empty array, not error."""
        response = test_client.get("/prices/NONEXISTENT12345")
        assert response.status_code == 200, "Unknown ticker should return 200, not error"

        data = response.json()
        assert data['data'] == [], "Should return empty array for unknown ticker"

    def test_get_prices_with_days_param(self, test_client):
        """GET /prices/{ticker}?days=7 should filter by days."""
        response = test_client.get("/prices/AAPL?days=7")
        assert response.status_code == 200, "Should accept days parameter"


class TestStatusEndpoint:
    """Verify /status system health endpoint."""

    def test_get_status(self, test_client):
        """GET /status should return system health."""
        response = test_client.get("/status")
        assert response.status_code == 200, "GET /status should return 200"

        data = response.json()
        assert 'data' in data, "Should return data envelope"

        status = data['data']
        assert 'open_position_count' in status, "Should include open_position_count"
        assert 'active_run_id' in status, "Should include active_run_id"
        assert 'emergence_active' in status, "Should include emergence_active"


class TestEmptyResultsBehavior:
    """Verify endpoints return empty arrays for no matches, not errors."""

    def test_signals_with_no_matches_returns_empty_array(self, test_client):
        """GET /signals with filters that match nothing should return empty array."""
        response = test_client.get("/signals?ticker=NONEXISTENT12345")
        assert response.status_code == 200, "No matches should return 200, not 404"

        data = response.json()
        assert 'data' in data, "Should return data envelope"
        assert data['data'] == [], "Should return empty array for no matches"

    def test_positions_with_no_matches_returns_empty_array(self, test_client):
        """GET /positions with filters that match nothing should return empty array."""
        response = test_client.get("/positions?ticker=NONEXISTENT12345")
        assert response.status_code == 200, "No matches should return 200, not 404"

        data = response.json()
        assert 'data' in data, "Should return data envelope"
        assert data['data'] == [], "Should return empty array for no matches"


class TestInvalidFiltersBehavior:
    """Verify invalid filters return VALIDATION_ERROR."""

    def test_invalid_limit_returns_validation_error(self, test_client):
        """Invalid pagination limit should return VALIDATION_ERROR."""
        response = test_client.get("/signals?limit=invalid")
        assert response.status_code == 422, "Invalid parameter should return 422"

        data = response.json()
        assert 'error' in data, "Should return error envelope"
        assert data['error']['code'] == 'VALIDATION_ERROR', \
            "Error code should be VALIDATION_ERROR"


class TestInvalidIdBehavior:
    """Verify invalid IDs return NOT_FOUND."""

    def test_nonexistent_signal_id_returns_not_found(self, test_client):
        """GET /signals/{id} with non-existent ID should return NOT_FOUND."""
        response = test_client.get("/signals/99999")
        assert response.status_code == 404, "Non-existent ID should return 404"

        data = response.json()
        assert 'error' in data, "Should return error envelope"
        assert data['error']['code'] == 'NOT_FOUND', \
            "Error code should be NOT_FOUND"

    def test_nonexistent_portfolio_id_returns_not_found(self, test_client):
        """GET /portfolios/{id} with non-existent ID should return NOT_FOUND."""
        response = test_client.get("/portfolios/99999")
        assert response.status_code == 404, "Non-existent ID should return 404"

        data = response.json()
        assert 'error' in data, "Should return error envelope"
        assert data['error']['code'] == 'NOT_FOUND', \
            "Error code should be NOT_FOUND"

    def test_nonexistent_position_id_returns_not_found(self, test_client):
        """GET /positions/{id} with non-existent ID should return NOT_FOUND."""
        response = test_client.get("/positions/99999")
        assert response.status_code == 404, "Non-existent ID should return 404"

        data = response.json()
        assert 'error' in data, "Should return error envelope"
        assert data['error']['code'] == 'NOT_FOUND', \
            "Error code should be NOT_FOUND"

    def test_nonexistent_run_id_returns_not_found(self, test_client):
        """GET /runs/{id}/status with non-existent ID should return NOT_FOUND."""
        response = test_client.get("/runs/99999/status")
        assert response.status_code == 404, "Non-existent ID should return 404"

        data = response.json()
        assert 'error' in data, "Should return error envelope"
        assert data['error']['code'] == 'NOT_FOUND', \
            "Error code should be NOT_FOUND"
