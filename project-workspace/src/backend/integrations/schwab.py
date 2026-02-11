"""
Schwab API Integration Module

Provides OAuth 2.0 authentication and API client for Schwab market data:
- OAuth setup (authorization code grant flow)
- Token management (proactive refresh, reactive 401 handling)
- Stock quotes (real-time)
- Options chains (with greeks)
- 5-minute candles

Token lifecycle:
- Access token TTL: ~30 minutes
- Refresh token TTL: ~7 days (renews if active weekly)
- Proactive refresh: when remaining TTL < 5 minutes
- Reactive refresh: on 401 response, immediate refresh + retry once
- If refresh token expired: user must re-run setup

Token storage: ./data/schwab_token.json (chmod 600)
Environment variables: SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET, SCHWAB_REDIRECT_URI
"""

import json
import logging
import os
import stat
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlencode, urlparse, parse_qs

import requests

# Configure logger
logger = logging.getLogger(__name__)

# Default token storage path
DEFAULT_TOKEN_PATH = str(Path(__file__).parent.parent.parent.parent / "data" / "schwab_token.json")

# Schwab API endpoints
SCHWAB_AUTH_BASE = "https://api.schwabapi.com/v1/oauth"
SCHWAB_AUTHORIZE_URL = f"{SCHWAB_AUTH_BASE}/authorize"
SCHWAB_TOKEN_URL = f"{SCHWAB_AUTH_BASE}/token"

# Token refresh threshold (5 minutes before expiry)
PROACTIVE_REFRESH_BUFFER = timedelta(minutes=5)


class SchwabAPIError(Exception):
    """Base exception for Schwab API errors."""
    pass


class SchwabAuthError(SchwabAPIError):
    """Exception for OAuth authentication errors."""
    pass


class SchwabTokenExpiredError(SchwabAPIError):
    """Exception when refresh token is expired and re-auth is required."""
    pass


def load_env_vars() -> Dict[str, str]:
    """Load Schwab credentials from environment or .env file.

    Reads SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET, SCHWAB_REDIRECT_URI.
    First checks environment variables, then falls back to .env file if present.

    Returns:
        Dictionary with client_id, client_secret, redirect_uri keys

    Raises:
        SchwabAuthError: If required environment variables are missing
    """
    # Try environment first
    client_id = os.getenv('SCHWAB_CLIENT_ID')
    client_secret = os.getenv('SCHWAB_CLIENT_SECRET')
    redirect_uri = os.getenv('SCHWAB_REDIRECT_URI')

    # Try .env file if environment vars not set
    if not all([client_id, client_secret, redirect_uri]):
        env_path = Path.cwd() / '.env'
        if env_path.exists():
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            if key == 'SCHWAB_CLIENT_ID':
                                client_id = value
                            elif key == 'SCHWAB_CLIENT_SECRET':
                                client_secret = value
                            elif key == 'SCHWAB_REDIRECT_URI':
                                redirect_uri = value

    # Validate all required vars are present
    if not client_id:
        raise SchwabAuthError("SCHWAB_CLIENT_ID not found in environment or .env file")
    if not client_secret:
        raise SchwabAuthError("SCHWAB_CLIENT_SECRET not found in environment or .env file")
    if not redirect_uri:
        raise SchwabAuthError("SCHWAB_REDIRECT_URI not found in environment or .env file")

    return {
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri
    }


def setup_oauth(token_path: str = DEFAULT_TOKEN_PATH) -> None:
    """Run OAuth 2.0 Authorization Code Grant flow for Schwab API.

    1. Opens browser to Schwab authorization URL
    2. User grants consent
    3. User pastes callback URL with authorization code
    4. Exchanges code for access and refresh tokens
    5. Saves tokens to token_path with chmod 600

    Args:
        token_path: Path to save token file (default: ./data/schwab_token.json)

    Raises:
        SchwabAuthError: If OAuth flow fails or credentials are invalid
    """
    print("Schwab OAuth Setup")
    print("=" * 50)

    # Load credentials
    try:
        creds = load_env_vars()
    except SchwabAuthError as e:
        print(f"\nError: {e}")
        print("\nPlease set the following environment variables or create a .env file:")
        print("  SCHWAB_CLIENT_ID")
        print("  SCHWAB_CLIENT_SECRET")
        print("  SCHWAB_REDIRECT_URI")
        raise

    # Build authorization URL
    auth_params = {
        'client_id': creds['client_id'],
        'redirect_uri': creds['redirect_uri'],
        'response_type': 'code'
    }
    auth_url = f"{SCHWAB_AUTHORIZE_URL}?{urlencode(auth_params)}"

    # Open browser
    print(f"\nOpening browser to Schwab authorization page...")
    print(f"URL: {auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for user to paste callback URL
    print("After granting consent, you will be redirected to your callback URL.")
    print("Copy the entire URL from your browser's address bar and paste it below.\n")
    callback_url = input("Paste callback URL: ").strip()

    # Extract authorization code
    try:
        parsed = urlparse(callback_url)
        query_params = parse_qs(parsed.query)

        if 'code' not in query_params:
            raise SchwabAuthError("No authorization code found in callback URL")

        auth_code = query_params['code'][0]
    except Exception as e:
        raise SchwabAuthError(f"Failed to parse callback URL: {e}")

    # Exchange code for tokens
    print("\nExchanging authorization code for tokens...")
    token_data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': creds['redirect_uri'],
        'client_id': creds['client_id'],
        'client_secret': creds['client_secret']
    }

    try:
        response = requests.post(
            SCHWAB_TOKEN_URL,
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        response.raise_for_status()
        token_response = response.json()
    except requests.RequestException as e:
        raise SchwabAuthError(f"Token exchange failed: {e}")

    # Build token structure with expiration timestamps
    now = datetime.now(timezone.utc)

    # Access token expires in ~30 minutes (use expires_in from response, or default to 1800s)
    access_ttl = token_response.get('expires_in', 1800)
    expires_at = now + timedelta(seconds=access_ttl)

    # Refresh token expires in ~7 days (use refresh_token_expires_in from response, or default to 7 days)
    refresh_ttl = token_response.get('refresh_token_expires_in', 7 * 24 * 60 * 60)
    refresh_expires_at = now + timedelta(seconds=refresh_ttl)

    token = {
        'access_token': token_response['access_token'],
        'refresh_token': token_response['refresh_token'],
        'expires_at': expires_at.isoformat(),
        'refresh_expires_at': refresh_expires_at.isoformat()
    }

    # Save token
    save_token(token, token_path)

    print(f"\nSuccess! Token saved to: {token_path}")
    print(f"Access token expires: {expires_at.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Refresh token expires: {refresh_expires_at.strftime('%Y-%m-%d %H:%M:%S %Z')}")


def save_token(token: Dict[str, str], token_path: str) -> None:
    """Save token to file with chmod 600 permissions.

    Creates parent directory if it doesn't exist.

    Args:
        token: Token dictionary with access_token, refresh_token, expires_at, refresh_expires_at
        token_path: Path to save token file
    """
    # Create parent directory if needed
    token_file = Path(token_path)
    token_file.parent.mkdir(parents=True, exist_ok=True)

    # Write token
    with open(token_path, 'w') as f:
        json.dump(token, f, indent=2)

    # Set chmod 600 (owner read/write only)
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)


def load_token(token_path: str) -> Dict[str, str]:
    """Load token from file.

    Args:
        token_path: Path to token file

    Returns:
        Token dictionary with access_token, refresh_token, expires_at, refresh_expires_at

    Raises:
        FileNotFoundError: If token file doesn't exist
        SchwabAuthError: If token file is invalid
    """
    if not Path(token_path).exists():
        raise FileNotFoundError(
            f"Token file not found: {token_path}\n"
            "Run schwab_setup.py to authenticate"
        )

    try:
        with open(token_path, 'r') as f:
            token = json.load(f)

        # Validate required fields
        required_fields = ['access_token', 'refresh_token', 'expires_at', 'refresh_expires_at']
        for field in required_fields:
            if field not in token:
                raise SchwabAuthError(f"Token file missing required field: {field}")

        return token
    except json.JSONDecodeError as e:
        raise SchwabAuthError(f"Invalid token file: {e}")


def needs_refresh(token: Dict[str, str]) -> bool:
    """Check if access token needs proactive refresh.

    Triggers refresh when remaining TTL < 5 minutes.

    Args:
        token: Token dictionary with expires_at field

    Returns:
        True if token should be refreshed proactively
    """
    try:
        expires_at = datetime.fromisoformat(token['expires_at'])

        # Compare using same timezone awareness
        if expires_at.tzinfo is None:
            # Naive datetime - compare with naive now
            now = datetime.now()
        else:
            # Timezone-aware - compare with aware now
            now = datetime.now(timezone.utc)

        remaining = expires_at - now

        return remaining < PROACTIVE_REFRESH_BUFFER
    except (KeyError, ValueError):
        # If we can't parse expiry, assume refresh is needed
        return True


def refresh_token(token_path: str = DEFAULT_TOKEN_PATH) -> Dict[str, str]:
    """Refresh access token using refresh token.

    Exchanges refresh token for new access token and refresh token.
    Updates token file with new values.

    Args:
        token_path: Path to token file

    Returns:
        Updated token dictionary

    Raises:
        SchwabTokenExpiredError: If refresh token is expired (user must re-auth)
        SchwabAuthError: If refresh fails for other reasons
    """
    # Load current token
    token = load_token(token_path)

    # Check if refresh token is expired
    try:
        refresh_expires_at = datetime.fromisoformat(token['refresh_expires_at'])
        if refresh_expires_at.tzinfo is None:
            refresh_expires_at = refresh_expires_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        if now >= refresh_expires_at:
            error_msg = "Refresh token has expired. Please re-run schwab_setup.py to re-authenticate."
            logger.error(error_msg)
            raise SchwabTokenExpiredError(error_msg)
    except (KeyError, ValueError) as e:
        raise SchwabAuthError(f"Invalid refresh_expires_at in token: {e}")

    # Load credentials
    creds = load_env_vars()

    # Request new tokens
    refresh_data = {
        'grant_type': 'refresh_token',
        'refresh_token': token['refresh_token'],
        'client_id': creds['client_id'],
        'client_secret': creds['client_secret']
    }

    try:
        response = requests.post(
            SCHWAB_TOKEN_URL,
            data=refresh_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        response.raise_for_status()
        token_response = response.json()
    except requests.RequestException as e:
        # Check if 401/400 indicates expired refresh token
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code in [400, 401]:
                error_msg = "Refresh token is invalid or expired. Please re-run schwab_setup.py to re-authenticate."
                logger.error(error_msg)
                raise SchwabTokenExpiredError(error_msg)
        raise SchwabAuthError(f"Token refresh failed: {e}")

    # Update token with new values
    now = datetime.now(timezone.utc)

    access_ttl = token_response.get('expires_in', 1800)
    expires_at = now + timedelta(seconds=access_ttl)

    refresh_ttl = token_response.get('refresh_token_expires_in', 7 * 24 * 60 * 60)
    refresh_expires_at = now + timedelta(seconds=refresh_ttl)

    updated_token = {
        'access_token': token_response['access_token'],
        'refresh_token': token_response['refresh_token'],
        'expires_at': expires_at.isoformat(),
        'refresh_expires_at': refresh_expires_at.isoformat()
    }

    # Save updated token
    save_token(updated_token, token_path)

    return updated_token


def handle_api_error(response: requests.Response, token_path: str = DEFAULT_TOKEN_PATH) -> bool:
    """Handle API error response and attempt recovery.

    On 401 Unauthorized: attempts immediate token refresh.
    Caller should retry the request once after successful refresh.

    Args:
        response: Failed API response
        token_path: Path to token file

    Returns:
        True if error was handled (caller should retry), False otherwise

    Raises:
        SchwabTokenExpiredError: If refresh token is expired
        SchwabAPIError: If error cannot be recovered
    """
    if response.status_code == 401:
        # Attempt immediate refresh
        try:
            refresh_token(token_path)
            return True  # Signal caller to retry
        except SchwabTokenExpiredError:
            raise
        except SchwabAuthError as e:
            raise SchwabAPIError(f"Failed to recover from 401: {e}")

    return False  # Cannot handle this error


class SchwabClient:
    """Schwab API client with automatic token management.

    Loads tokens from file on initialization. Proactively refreshes access token
    before expiration (< 5 minutes remaining). On 401 response, immediately refreshes
    and retries the request once.

    Example:
        client = SchwabClient()
        quote = client.get_stock_quote("AAPL")
        options = client.get_options_chain("AAPL", strikeCount=10)
    """

    def __init__(self, token_path: str = DEFAULT_TOKEN_PATH):
        """Initialize Schwab client and load tokens.

        Args:
            token_path: Path to token file (default: ./data/schwab_token.json)

        Raises:
            FileNotFoundError: If token file doesn't exist
            SchwabAuthError: If token file is invalid
        """
        self.token_path = token_path
        self.token = load_token(token_path)

    def _ensure_fresh_token(self) -> None:
        """Check token expiry and refresh proactively if needed.

        Refreshes if access token expires within 5 minutes.
        Updates self.token with refreshed token.

        Raises:
            SchwabTokenExpiredError: If refresh token is expired
            SchwabAuthError: If refresh fails
        """
        if needs_refresh(self.token):
            self.token = refresh_token(self.token_path)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with automatic token management.

        Proactively refreshes token before request if needed.
        On 401 response, immediately refreshes and retries once.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL for the request
            **kwargs: Additional arguments passed to requests.request()

        Returns:
            Response object

        Raises:
            SchwabAPIError: If request fails after retry
            SchwabTokenExpiredError: If refresh token is expired
        """
        # Proactive refresh
        self._ensure_fresh_token()

        # Prepare headers with auth token
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f"Bearer {self.token['access_token']}"
        headers['Accept'] = 'application/json'

        # Make initial request
        response = requests.request(method, url, headers=headers, **kwargs)

        # Handle 401 with reactive refresh + retry
        if response.status_code == 401:
            if handle_api_error(response, self.token_path):
                # Reload token after refresh and retry once
                self.token = load_token(self.token_path)
                headers['Authorization'] = f"Bearer {self.token['access_token']}"
                response = requests.request(method, url, headers=headers, **kwargs)

        return response

    def get_stock_quote(self, ticker: str) -> Dict[str, Any]:
        """Fetch real-time stock quote for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")

        Returns:
            Quote data from Schwab API

        Raises:
            SchwabAPIError: If quote fetch fails
            SchwabTokenExpiredError: If refresh token is expired
        """
        url = f"https://api.schwabapi.com/marketdata/v1/quotes/{ticker}"

        try:
            response = self._request('GET', url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise SchwabAPIError(f"Failed to fetch quote for {ticker}: {e}")

    def get_quote(self, ticker: str) -> Dict[str, Any]:
        """Fetch real-time stock quote for a ticker.

        Alias for get_stock_quote() for convenience.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")

        Returns:
            Quote data from Schwab API

        Raises:
            SchwabAPIError: If quote fetch fails
            SchwabTokenExpiredError: If refresh token is expired
        """
        return self.get_stock_quote(ticker)

    def get_options_chain(
        self,
        ticker: str,
        dte_min: Optional[int] = None,
        dte_max: Optional[int] = None,
        **params
    ) -> Dict[str, Any]:
        """Fetch options chain with greeks for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            dte_min: Minimum days to expiration (optional, calculates fromDate)
            dte_max: Maximum days to expiration (optional, calculates toDate)
            **params: Additional query parameters (e.g., strikeCount, includeQuotes, strategy)
                     Note: dte_min/dte_max override any fromDate/toDate in params

        Returns:
            Options chain data from Schwab API

        Raises:
            SchwabAPIError: If options chain fetch fails
            SchwabTokenExpiredError: If refresh token is expired

        Example:
            # Fetch options expiring in 14-21 days
            options = client.get_options_chain("AAPL", dte_min=14, dte_max=21)

            # Fetch with specific date range instead
            options = client.get_options_chain("AAPL", fromDate="2026-02-24", toDate="2026-03-03")
        """
        url = "https://api.schwabapi.com/marketdata/v1/chains"
        query_params = {'symbol': ticker, **params}

        # Convert DTE to date range if provided
        if dte_min is not None or dte_max is not None:
            from datetime import datetime, timedelta

            today = datetime.now().date()

            if dte_min is not None:
                from_date = today + timedelta(days=dte_min)
                query_params['fromDate'] = from_date.strftime('%Y-%m-%d')

            if dte_max is not None:
                to_date = today + timedelta(days=dte_max)
                query_params['toDate'] = to_date.strftime('%Y-%m-%d')

        try:
            response = self._request('GET', url, params=query_params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise SchwabAPIError(f"Failed to fetch options chain for {ticker}: {e}")


# Backwards compatibility: module-level functions that use SchwabClient
def get_stock_quote(ticker: str, token_path: str = DEFAULT_TOKEN_PATH) -> Dict[str, Any]:
    """Fetch real-time stock quote for a ticker.

    Implements proactive refresh (before request if needed) and reactive refresh (on 401).

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        token_path: Path to token file

    Returns:
        Quote data from Schwab API

    Raises:
        SchwabAPIError: If quote fetch fails
        SchwabTokenExpiredError: If refresh token is expired
    """
    client = SchwabClient(token_path)
    return client.get_stock_quote(ticker)


def get_options_chain(
    ticker: str,
    token_path: str = DEFAULT_TOKEN_PATH,
    **params
) -> Dict[str, Any]:
    """Fetch options chain with greeks for a ticker.

    Implements proactive refresh (before request if needed) and reactive refresh (on 401).

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        token_path: Path to token file
        **params: Additional query parameters (e.g., strikeCount, includeQuotes, strategy)

    Returns:
        Options chain data from Schwab API

    Raises:
        SchwabAPIError: If options chain fetch fails
        SchwabTokenExpiredError: If refresh token is expired
    """
    client = SchwabClient(token_path)
    return client.get_options_chain(ticker, **params)
