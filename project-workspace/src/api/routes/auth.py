"""Schwab OAuth authentication endpoints.

Provides a web-based OAuth flow as an alternative to the CLI schwab_setup.py script:
- GET /auth/schwab/login — redirects browser to Schwab's authorization page
- GET /auth/schwab/callback — receives auth code, exchanges for tokens, saves them
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from src.backend.integrations.schwab import (
    SCHWAB_AUTHORIZE_URL,
    SCHWAB_TOKEN_URL,
    DEFAULT_TOKEN_PATH,
    SchwabAuthError,
    load_env_vars,
    save_token,
)
from src.backend.utils.logging_config import get_logger

router = APIRouter(prefix="/auth/schwab", tags=["auth"])
logger = get_logger(__name__)


def _html_page(title: str, body: str) -> HTMLResponse:
    """Render a minimal HTML page."""
    html = f"""<!DOCTYPE html>
<html>
<head><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 80px auto; padding: 0 20px; }}
h1 {{ color: #1a1a1a; }}
.success {{ color: #16a34a; }}
.error {{ color: #dc2626; }}
code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }}
</style>
</head>
<body>{body}</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/login")
async def schwab_login():
    """Redirect browser to Schwab's OAuth authorization page.

    Reads SCHWAB_CLIENT_ID and SCHWAB_REDIRECT_URI from environment/.env,
    builds the authorization URL, and returns a 302 redirect.
    """
    try:
        creds = load_env_vars()
    except SchwabAuthError as e:
        logger.warning("schwab_login_failed", error=str(e))
        return _html_page(
            "Schwab Login Error",
            '<h1 class="error">Configuration Error</h1>'
            f"<p>{e}</p>"
            "<p>Set <code>SCHWAB_CLIENT_ID</code>, <code>SCHWAB_CLIENT_SECRET</code>, "
            "and <code>SCHWAB_REDIRECT_URI</code> in your <code>.env</code> file.</p>",
        )

    auth_params = {
        "client_id": creds["client_id"],
        "redirect_uri": creds["redirect_uri"],
        "response_type": "code",
    }
    auth_url = f"{SCHWAB_AUTHORIZE_URL}?{urlencode(auth_params)}"
    logger.info("schwab_login_redirect", auth_url=auth_url)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def schwab_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """Handle Schwab OAuth callback.

    Receives the authorization code (or error) from Schwab's redirect,
    exchanges the code for access/refresh tokens, and saves them.
    """
    # Schwab denied or user cancelled
    if error:
        logger.warning("schwab_callback_error", error=error)
        return _html_page(
            "Schwab Auth Error",
            '<h1 class="error">Authorization Failed</h1>'
            f"<p>Schwab returned an error: <code>{error}</code></p>"
            '<p><a href="/auth/schwab/login">Try again</a></p>',
        )

    if not code:
        return _html_page(
            "Schwab Auth Error",
            '<h1 class="error">Missing Authorization Code</h1>'
            "<p>No authorization code was received from Schwab.</p>"
            '<p><a href="/auth/schwab/login">Try again</a></p>',
        )

    # Exchange code for tokens
    try:
        creds = load_env_vars()
    except SchwabAuthError as e:
        logger.error("schwab_callback_creds_error", error=str(e))
        return _html_page(
            "Schwab Auth Error",
            '<h1 class="error">Configuration Error</h1>'
            f"<p>{e}</p>",
        )

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": creds["redirect_uri"],
    }

    try:
        response = requests.post(
            SCHWAB_TOKEN_URL,
            data=token_data,
            auth=(creds["client_id"], creds["client_secret"]),
        )
        response.raise_for_status()
        token_response = response.json()
    except requests.RequestException as e:
        logger.error("schwab_token_exchange_failed", error=str(e))
        return _html_page(
            "Schwab Auth Error",
            '<h1 class="error">Token Exchange Failed</h1>'
            f"<p>Could not exchange authorization code for tokens: {e}</p>"
            '<p><a href="/auth/schwab/login">Try again</a></p>',
        )

    # Build token with expiration timestamps
    now = datetime.now(timezone.utc)

    access_ttl = token_response.get("expires_in", 1800)
    expires_at = now + timedelta(seconds=access_ttl)

    refresh_ttl = token_response.get("refresh_token_expires_in", 7 * 24 * 60 * 60)
    refresh_expires_at = now + timedelta(seconds=refresh_ttl)

    token = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response["refresh_token"],
        "expires_at": expires_at.isoformat(),
        "refresh_expires_at": refresh_expires_at.isoformat(),
    }

    save_token(token, DEFAULT_TOKEN_PATH)
    logger.info(
        "schwab_token_saved",
        expires_at=expires_at.isoformat(),
        refresh_expires_at=refresh_expires_at.isoformat(),
    )

    return _html_page(
        "Schwab Auth Success",
        '<h1 class="success">Authentication Successful</h1>'
        "<p>Schwab OAuth tokens have been saved.</p>"
        f"<p><strong>Access token expires:</strong> {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>"
        f"<p><strong>Refresh token expires:</strong> {refresh_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>"
        "<p>You can close this page.</p>",
    )
