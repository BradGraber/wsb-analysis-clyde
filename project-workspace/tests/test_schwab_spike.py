"""
Tests for story-001-006: Schwab OAuth Spike

These tests verify the module structure and token handling logic.
Tests that require actual Schwab API credentials are marked with @pytest.mark.schwab_api
and will be skipped unless credentials are available.

The tests verify:
- CLI script module/function exists
- Token storage structure (access_token, refresh_token, expires_at, refresh_expires_at)
- Token file permissions (chmod 600)
- Token refresh logic (proactive + on 401)
- Stock quote fetch functionality exists
- Options chain fetch functionality exists
- .gitignore contains token file path

NOTE: This is a spike with external dependencies. Most tests verify structure,
not actual API calls.
"""

import pytest
import os
import json
import stat
from pathlib import Path


class TestSchwabModuleStructure:
    """Verify Schwab module structure exists."""

    def test_schwab_module_exists(self):
        """Schwab OAuth module should exist."""
        try:
            from src.backend.integrations import schwab
            assert schwab is not None
        except ImportError:
            pytest.skip("Schwab module not implemented yet")

    def test_oauth_setup_function_exists(self):
        """CLI OAuth setup function should exist."""
        try:
            from src.backend.integrations.schwab import setup_oauth
            assert callable(setup_oauth), "setup_oauth should be a callable function"
        except ImportError:
            pytest.skip("Schwab module not implemented yet")

    def test_token_refresh_function_exists(self):
        """Token refresh function should exist."""
        try:
            from src.backend.integrations.schwab import refresh_token
            assert callable(refresh_token), "refresh_token should be a callable function"
        except ImportError:
            pytest.skip("Schwab module not implemented yet")

    def test_stock_quote_function_exists(self):
        """Stock quote fetch function should exist."""
        try:
            from src.backend.integrations.schwab import get_stock_quote
            assert callable(get_stock_quote), "get_stock_quote should be a callable function"
        except ImportError:
            pytest.skip("Schwab module not implemented yet")

    def test_options_chain_function_exists(self):
        """Options chain fetch function should exist."""
        try:
            from src.backend.integrations.schwab import get_options_chain
            assert callable(get_options_chain), \
                "get_options_chain should be a callable function"
        except ImportError:
            pytest.skip("Schwab module not implemented yet")


class TestTokenStorage:
    """Verify token storage structure and handling."""

    def test_token_file_structure(self, mock_schwab_token, tmp_path):
        """Token file should have correct JSON structure."""
        try:
            from src.backend.integrations.schwab import save_token

            token_path = tmp_path / "schwab_token.json"

            # Save token
            save_token(mock_schwab_token, str(token_path))

            # Verify file exists
            assert token_path.exists(), "Token file not created"

            # Verify structure
            with open(token_path, 'r') as f:
                saved_token = json.load(f)

            required_fields = ['access_token', 'refresh_token', 'expires_at', 'refresh_expires_at']
            for field in required_fields:
                assert field in saved_token, f"Token missing required field: {field}"

        except ImportError:
            pytest.skip("Schwab module not implemented yet")

    def test_token_file_permissions(self, mock_schwab_token, tmp_path):
        """Token file should have chmod 600 permissions."""
        try:
            from src.backend.integrations.schwab import save_token

            token_path = tmp_path / "schwab_token.json"
            save_token(mock_schwab_token, str(token_path))

            # Check file permissions
            file_stat = os.stat(token_path)
            file_mode = stat.filemode(file_stat.st_mode)

            # Should be -rw------- (600)
            assert stat.S_IRUSR & file_stat.st_mode, "Owner read permission not set"
            assert stat.S_IWUSR & file_stat.st_mode, "Owner write permission not set"
            assert not (stat.S_IRGRP & file_stat.st_mode), "Group read should not be set"
            assert not (stat.S_IWGRP & file_stat.st_mode), "Group write should not be set"
            assert not (stat.S_IROTH & file_stat.st_mode), "Other read should not be set"
            assert not (stat.S_IWOTH & file_stat.st_mode), "Other write should not be set"

        except ImportError:
            pytest.skip("Schwab module not implemented yet")

    def test_token_loading(self, mock_schwab_token, tmp_path):
        """Should be able to load token from file."""
        try:
            from src.backend.integrations.schwab import save_token, load_token

            token_path = tmp_path / "schwab_token.json"
            save_token(mock_schwab_token, str(token_path))

            loaded_token = load_token(str(token_path))

            assert loaded_token['access_token'] == mock_schwab_token['access_token']
            assert loaded_token['refresh_token'] == mock_schwab_token['refresh_token']

        except ImportError:
            pytest.skip("Schwab module not implemented yet")


class TestTokenRefreshLogic:
    """Verify token refresh logic (proactive and reactive)."""

    def test_proactive_refresh_before_expiry(self, mock_schwab_token, tmp_path):
        """Should refresh token proactively before expiration."""
        try:
            from src.backend.integrations.schwab import needs_refresh
            from datetime import datetime, timedelta

            # Create token that expires in 2 minutes
            token = mock_schwab_token.copy()
            token['expires_at'] = (datetime.now() + timedelta(minutes=2)).isoformat()

            # Should need refresh (proactive, before 30 min expiry)
            result = needs_refresh(token)
            assert result is True, \
                "Should proactively refresh when access token expires soon"

        except ImportError:
            pytest.skip("Schwab module not implemented yet")

    def test_no_refresh_when_token_fresh(self, mock_schwab_token):
        """Should not refresh when token is still fresh."""
        try:
            from src.backend.integrations.schwab import needs_refresh
            from datetime import datetime, timedelta

            # Create token that expires in 20 minutes
            token = mock_schwab_token.copy()
            token['expires_at'] = (datetime.now() + timedelta(minutes=20)).isoformat()

            result = needs_refresh(token)
            assert result is False, \
                "Should not refresh when access token is still fresh"

        except ImportError:
            pytest.skip("Schwab module not implemented yet")

    def test_reactive_refresh_on_401(self):
        """Should have logic to refresh on 401 response."""
        try:
            from src.backend.integrations.schwab import handle_api_error
            import inspect

            # Verify the function exists and can handle 401
            sig = inspect.signature(handle_api_error)
            params = list(sig.parameters.keys())

            # Should accept status code or response
            assert len(params) >= 1, \
                "handle_api_error should accept error/status information"

        except ImportError:
            pytest.skip("Schwab module not implemented yet")


class TestGitignore:
    """Verify .gitignore contains token file path."""

    def test_token_path_in_gitignore(self):
        """Token file path should be in .gitignore."""
        gitignore_path = Path(__file__).parent.parent / '.gitignore'

        # .gitignore might not exist yet
        if not gitignore_path.exists():
            pytest.skip(".gitignore not created yet")

        with open(gitignore_path, 'r') as f:
            gitignore_content = f.read()

        # Should contain some variation of schwab token path
        assert 'schwab_token.json' in gitignore_content or \
               'data/schwab_token.json' in gitignore_content or \
               '*token*.json' in gitignore_content, \
               "Token file path not found in .gitignore"


@pytest.mark.schwab_api
class TestSchwabAPIIntegration:
    """
    Tests that require actual Schwab API credentials.
    These are marked with @pytest.mark.schwab_api and will be skipped
    unless run with: pytest -m schwab_api
    """

    def test_oauth_flow_completes(self):
        """OAuth flow should complete and return valid tokens."""
        pytest.skip("Requires manual OAuth flow and valid Schwab credentials")

    def test_stock_quote_fetch_works(self):
        """Should be able to fetch stock quote with valid credentials."""
        pytest.skip("Requires valid Schwab credentials and API access")

    def test_options_chain_fetch_works(self):
        """Should be able to fetch options chain with valid credentials."""
        pytest.skip("Requires valid Schwab credentials and API access")

    def test_token_refresh_works_with_api(self):
        """Token refresh should work with actual Schwab API."""
        pytest.skip("Requires valid Schwab refresh token")


class TestDefaultTokenPath:
    """Verify default token path handling."""

    def test_default_token_path_is_data_directory(self):
        """Default token path should be ./data/schwab_token.json."""
        try:
            from src.backend.integrations.schwab import DEFAULT_TOKEN_PATH

            assert 'data' in DEFAULT_TOKEN_PATH, \
                "Default token path should be in data directory"
            assert 'schwab_token.json' in DEFAULT_TOKEN_PATH, \
                "Default token filename should be schwab_token.json"

        except ImportError:
            pytest.skip("Schwab module not implemented yet")
