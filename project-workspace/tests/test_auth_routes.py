"""Tests for Schwab OAuth authentication endpoints.

Tests the /auth/schwab/login and /auth/schwab/callback routes using
mocked Schwab dependencies (no real API calls or credentials needed).
"""

import pytest
from unittest.mock import patch, MagicMock


class TestSchwabLogin:
    """Tests for GET /auth/schwab/login."""

    def test_login_redirects_to_schwab(self, test_client):
        """Login endpoint redirects to Schwab authorization URL with correct params."""
        mock_creds = {
            "client_id": "test_client_id",
            "client_secret": "test_secret",
            "redirect_uri": "https://127.0.0.1:8000/auth/schwab/callback",
        }
        with patch("src.api.routes.auth.load_env_vars", return_value=mock_creds):
            response = test_client.get(
                "/auth/schwab/login", follow_redirects=False
            )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "api.schwabapi.com" in location
        assert "client_id=test_client_id" in location
        assert "response_type=code" in location
        assert "redirect_uri=" in location

    def test_login_returns_error_html_when_creds_missing(self, test_client):
        """Login returns HTML error page when Schwab credentials are not configured."""
        from src.backend.integrations.schwab import SchwabAuthError

        with patch(
            "src.api.routes.auth.load_env_vars",
            side_effect=SchwabAuthError("SCHWAB_CLIENT_ID not found"),
        ):
            response = test_client.get("/auth/schwab/login")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Configuration Error" in response.text
        assert "SCHWAB_CLIENT_ID" in response.text


class TestSchwabCallback:
    """Tests for GET /auth/schwab/callback."""

    def test_callback_exchanges_code_and_saves_token(self, test_client):
        """Callback exchanges auth code for tokens and returns success HTML."""
        mock_creds = {
            "client_id": "test_client_id",
            "client_secret": "test_secret",
            "redirect_uri": "https://127.0.0.1:8000/auth/schwab/callback",
        }
        mock_token_response = MagicMock()
        mock_token_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 1800,
            "refresh_token_expires_in": 604800,
        }
        mock_token_response.raise_for_status = MagicMock()

        with (
            patch("src.api.routes.auth.load_env_vars", return_value=mock_creds),
            patch("src.api.routes.auth.requests.post", return_value=mock_token_response) as mock_post,
            patch("src.api.routes.auth.save_token") as mock_save,
        ):
            response = test_client.get(
                "/auth/schwab/callback?code=test_auth_code_123"
            )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Authentication Successful" in response.text

        # Verify token exchange was called with correct data
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        post_data = call_kwargs.kwargs.get("data") or call_kwargs[1].get("data")
        assert post_data["grant_type"] == "authorization_code"
        assert post_data["code"] == "test_auth_code_123"

        # Verify token was saved
        mock_save.assert_called_once()
        saved_token = mock_save.call_args[0][0]
        assert saved_token["access_token"] == "new_access_token"
        assert saved_token["refresh_token"] == "new_refresh_token"
        assert "expires_at" in saved_token
        assert "refresh_expires_at" in saved_token

    def test_callback_returns_error_html_on_schwab_error_param(self, test_client):
        """Callback returns error HTML when Schwab sends an error parameter."""
        response = test_client.get(
            "/auth/schwab/callback?error=access_denied"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Authorization Failed" in response.text
        assert "access_denied" in response.text

    def test_callback_returns_error_html_when_no_code(self, test_client):
        """Callback returns error HTML when no code parameter is provided."""
        response = test_client.get("/auth/schwab/callback")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Missing Authorization Code" in response.text

    def test_callback_returns_error_html_on_token_exchange_failure(self, test_client):
        """Callback returns error HTML when token exchange HTTP request fails."""
        import requests as req_lib

        mock_creds = {
            "client_id": "test_client_id",
            "client_secret": "test_secret",
            "redirect_uri": "https://127.0.0.1:8000/auth/schwab/callback",
        }

        with (
            patch("src.api.routes.auth.load_env_vars", return_value=mock_creds),
            patch(
                "src.api.routes.auth.requests.post",
                side_effect=req_lib.RequestException("Connection refused"),
            ),
        ):
            response = test_client.get(
                "/auth/schwab/callback?code=test_code"
            )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Token Exchange Failed" in response.text
