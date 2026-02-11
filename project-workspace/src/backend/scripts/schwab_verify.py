#!/usr/bin/env python3
"""
Schwab API Verification Script

Verifies SchwabClient methods by fetching:
1. Stock quote for AAPL
2. Options chain for AAPL with 14-21 DTE filter

This is a spike script to test API integration and document findings.
May fail if Schwab credentials are not configured - this is expected behavior.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from integrations.schwab import (
    SchwabClient,
    SchwabAPIError,
    SchwabAuthError,
    SchwabTokenExpiredError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def verify_stock_quote(client: SchwabClient, ticker: str = "AAPL") -> dict:
    """Fetch and verify stock quote.

    Args:
        client: Initialized SchwabClient
        ticker: Ticker symbol to fetch

    Returns:
        Quote data dictionary

    Raises:
        SchwabAPIError: If quote fetch fails
    """
    logger.info(f"Fetching stock quote for {ticker}...")

    quote_data = client.get_stock_quote(ticker)

    # Log key fields
    logger.info(f"Quote received for {ticker}:")
    logger.info(f"  Response keys: {list(quote_data.keys())}")

    # Try to extract common fields if they exist
    if ticker in quote_data:
        ticker_data = quote_data[ticker]
        logger.info(f"  Ticker data keys: {list(ticker_data.keys())}")

        # Quote fields are nested under the "quote" key per API spec
        quote = ticker_data.get('quote', {})
        if quote:
            for field in ['lastPrice', 'bidPrice', 'askPrice', 'mark', 'highPrice', 'lowPrice', 'openPrice', 'closePrice']:
                if field in quote:
                    logger.info(f"  {field}: {quote[field]}")

    return quote_data


def verify_options_chain(
    client: SchwabClient,
    ticker: str = "AAPL",
    dte_min: int = 14,
    dte_max: int = 21
) -> dict:
    """Fetch and verify options chain with DTE filter.

    Args:
        client: Initialized SchwabClient
        ticker: Ticker symbol to fetch
        dte_min: Minimum days to expiration
        dte_max: Maximum days to expiration

    Returns:
        Options chain data dictionary

    Raises:
        SchwabAPIError: If options chain fetch fails
    """
    logger.info(f"Fetching options chain for {ticker} with DTE {dte_min}-{dte_max}...")

    # Calculate expected date range for logging
    today = datetime.now().date()
    from_date = today + timedelta(days=dte_min)
    to_date = today + timedelta(days=dte_max)
    logger.info(f"  Calculated date range: {from_date} to {to_date}")

    # Fetch options chain with DTE filters and greeks
    # The client now handles DTE-to-date conversion internally
    options_data = client.get_options_chain(
        ticker,
        dte_min=dte_min,
        dte_max=dte_max,
        includeUnderlyingQuote=True,
        strategy='ANALYTICAL'  # Required for greeks
    )

    # Log response structure
    logger.info(f"Options chain received for {ticker}:")
    logger.info(f"  Response keys: {list(options_data.keys())}")

    # Log call/put map structure if present
    if 'callExpDateMap' in options_data:
        call_expirations = list(options_data['callExpDateMap'].keys())
        logger.info(f"  Call expirations: {call_expirations}")

        if call_expirations:
            # Show first expiration's strike structure
            first_exp = call_expirations[0]
            strikes = list(options_data['callExpDateMap'][first_exp].keys())
            logger.info(f"  Sample expiration ({first_exp}) strikes count: {len(strikes)}")

            # Show first strike's option data structure
            if strikes:
                first_strike_data = options_data['callExpDateMap'][first_exp][strikes[0]][0]
                logger.info(f"  Sample option fields: {list(first_strike_data.keys())}")

                # Log greeks if present
                for field in ['delta', 'gamma', 'theta', 'vega', 'rho']:
                    if field in first_strike_data:
                        logger.info(f"    {field}: {first_strike_data[field]}")

    if 'putExpDateMap' in options_data:
        put_expirations = list(options_data['putExpDateMap'].keys())
        logger.info(f"  Put expirations: {put_expirations}")

    return options_data


def main():
    """Run verification tests."""
    print("=" * 60)
    print("Schwab API Verification")
    print("=" * 60)
    print()

    try:
        # Initialize client
        logger.info("Initializing SchwabClient...")
        client = SchwabClient()
        logger.info("Client initialized successfully")
        print()

        # Test 1: Stock quote
        print("-" * 60)
        print("Test 1: Stock Quote")
        print("-" * 60)
        try:
            quote_data = verify_stock_quote(client, "AAPL")
            print("✓ Stock quote fetch SUCCESSFUL")
            print()
        except Exception as e:
            print(f"✗ Stock quote fetch FAILED: {e}")
            logger.error(f"Stock quote error: {e}", exc_info=True)
            print()

        # Test 2: Options chain
        print("-" * 60)
        print("Test 2: Options Chain (14-21 DTE)")
        print("-" * 60)
        try:
            options_data = verify_options_chain(client, "AAPL", dte_min=14, dte_max=21)
            print("✓ Options chain fetch SUCCESSFUL")
            print()
        except Exception as e:
            print(f"✗ Options chain fetch FAILED: {e}")
            logger.error(f"Options chain error: {e}", exc_info=True)
            print()

        print("=" * 60)
        print("Verification Complete")
        print("=" * 60)

    except FileNotFoundError as e:
        print(f"✗ BLOCKED: {e}")
        print()
        print("Next steps:")
        print("1. Run 'python3 scripts/schwab_setup.py' to authenticate with Schwab")
        print("2. Ensure SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET, SCHWAB_REDIRECT_URI are set in .env")
        print("3. Re-run this verification script")
        logger.error(f"Token file not found: {e}")
        sys.exit(1)

    except SchwabAuthError as e:
        print(f"✗ BLOCKED: Authentication error: {e}")
        print()
        print("Next steps:")
        print("1. Check .env file has SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET, SCHWAB_REDIRECT_URI")
        print("2. Run 'python3 scripts/schwab_setup.py' to re-authenticate")
        logger.error(f"Auth error: {e}")
        sys.exit(1)

    except SchwabTokenExpiredError as e:
        print(f"✗ BLOCKED: {e}")
        print()
        print("Next steps:")
        print("1. Run 'python3 scripts/schwab_setup.py' to re-authenticate")
        logger.error(f"Token expired: {e}")
        sys.exit(1)

    except SchwabAPIError as e:
        print(f"✗ API Error: {e}")
        print()
        print("The API request failed. This may indicate:")
        print("- Rate limiting (wait and retry)")
        print("- Invalid request parameters")
        print("- Schwab API service issues")
        logger.error(f"API error: {e}", exc_info=True)
        sys.exit(1)

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
