#!/usr/bin/env python3
"""
Schwab OAuth Setup CLI Script

One-time setup script for Schwab API OAuth 2.0 authentication.
Opens browser for user consent, exchanges authorization code for tokens,
and stores them securely in ./data/schwab_token.json with chmod 600.

Usage:
    python3 scripts/schwab_setup.py

Prerequisites:
    Set environment variables or create .env file:
        SCHWAB_CLIENT_ID
        SCHWAB_CLIENT_SECRET
        SCHWAB_REDIRECT_URI

Output:
    ./data/schwab_token.json (chmod 600)
    - access_token: Bearer token for API calls (~30 min TTL)
    - refresh_token: Token for refreshing access token (~7 day TTL)
    - expires_at: ISO timestamp when access token expires
    - refresh_expires_at: ISO timestamp when refresh token expires
"""

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from integrations.schwab import setup_oauth, SchwabAuthError


def main():
    """Run OAuth setup flow."""
    try:
        setup_oauth()
        print("\nSetup complete!")
        print("\nYour Schwab API credentials are now configured.")
        print("The access token will be automatically refreshed when needed.")
        print("If the refresh token expires (after 7 days of inactivity), re-run this script.")

    except SchwabAuthError as e:
        print(f"\nSetup failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
