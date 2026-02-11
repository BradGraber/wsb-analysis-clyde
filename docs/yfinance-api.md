# yfinance API Reference

**Version**: 0.2.x
**Purpose**: Python library for downloading historical market data from Yahoo Finance
**Installation**: `pip install yfinance`

This reference covers the core features needed for fetching historical OHLCV data for individual tickers and benchmark indices.

---

## Overview

yfinance is a web scraper that fetches data from Yahoo Finance. It has no official API documentation from Yahoo, so rate limits and availability are subject to change. Use it as a fallback data source with appropriate error handling.

---

## Ticker Class

### Constructor

```python
import yfinance as yf

ticker = yf.Ticker("MSFT")
```

**Parameters:**
- `ticker` (str): Stock symbol (e.g., "MSFT", "AAPL", "^GSPC" for S&P 500)
- `session` (optional): Requests session object for custom HTTP configuration

**Returns:** Ticker object with methods for fetching various data types

---

## Ticker.history() Method

Fetches historical market data (OHLCV) for a single ticker.

### Method Signature

```python
ticker.history(
    period="1mo",
    interval="1d",
    start=None,
    end=None,
    prepost=False,
    auto_adjust=True,
    actions=True
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | str | `"1mo"` | Data period to download. Valid values: `"1d"`, `"5d"`, `"1mo"`, `"3mo"`, `"6mo"`, `"1y"`, `"2y"`, `"5y"`, `"10y"`, `"ytd"`, `"max"`. Use either `period` OR (`start` + `end`), not both. |
| `interval` | str | `"1d"` | Data interval. Valid values: `"1m"`, `"2m"`, `"5m"`, `"15m"`, `"30m"`, `"60m"`, `"90m"`, `"1h"`, `"1d"`, `"5d"`, `"1wk"`, `"1mo"`, `"3mo"`. Note: 1m data only available for last 7 days; intervals <1d only for last 60 days. |
| `start` | str or datetime | `None` | Start date for data range. Format: `"YYYY-MM-DD"` or datetime object. Use with `end` instead of `period`. |
| `end` | str or datetime | `None` | End date for data range. Format: `"YYYY-MM-DD"` or datetime object. Use with `start` instead of `period`. |
| `prepost` | bool | `False` | Include pre-market and post-market data in results. |
| `auto_adjust` | bool | `True` | Automatically adjust all OHLC prices for splits and dividends. |
| `actions` | bool | `True` | Include dividend and stock split events in the DataFrame. |

### Return Type

**pandas.DataFrame** with the following structure:

**Index:**
- `DatetimeIndex` with timezone-aware timestamps (typically US/Eastern for US stocks)

**Columns (when `actions=True`):**
- `Open` (float64): Opening price
- `High` (float64): Highest price during the interval
- `Low` (float64): Lowest price during the interval
- `Close` (float64): Closing price
- `Volume` (int64): Trading volume
- `Dividends` (float64): Dividend amount (0.0 if none)
- `Stock Splits` (float64): Split ratio (0.0 if none)

**Note:** If `auto_adjust=True`, the `Adj Close` column is not included (all prices are pre-adjusted).

### Usage Examples

#### Fetch daily data for a date range

```python
import yfinance as yf
from datetime import datetime, timedelta

ticker = yf.Ticker("MSFT")
end_date = datetime.now()
start_date = end_date - timedelta(days=365)

df = ticker.history(start=start_date, end=end_date, interval="1d")

# Access OHLCV data
print(df[['Open', 'High', 'Low', 'Close', 'Volume']].head())
```

#### Fetch S&P 500 benchmark data

```python
sp500 = yf.Ticker("^GSPC")
df = sp500.history(period="1y", interval="1d")
```

#### Get the latest closing price

```python
ticker = yf.Ticker("AAPL")
df = ticker.history(period="1d", interval="1d")
latest_close = df['Close'].iloc[-1]
```

#### Fetch data without dividends/splits

```python
df = ticker.history(period="6mo", interval="1d", actions=False)
# DataFrame will only have: Open, High, Low, Close, Volume
```

---

## download() Function

Download historical market data for **multiple tickers** simultaneously with multithreading support.

### Function Signature

```python
yf.download(
    tickers,
    period="1mo",
    interval="1d",
    start=None,
    end=None,
    group_by="column",
    auto_adjust=False,
    prepost=False,
    actions=True,
    threads=True
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tickers` | str or list | required | Single ticker string or list of ticker symbols (e.g., `["MSFT", "AAPL", "GOOG"]` or space-separated `"MSFT AAPL GOOG"`). |
| `period` | str | `"1mo"` | Same as `Ticker.history()`. Use either `period` OR (`start` + `end`). |
| `interval` | str | `"1d"` | Same as `Ticker.history()`. |
| `start` | str or datetime | `None` | Start date (format: `"YYYY-MM-DD"`). |
| `end` | str or datetime | `None` | End date (format: `"YYYY-MM-DD"`). |
| `group_by` | str | `"column"` | Group DataFrame columns by `"column"` (all tickers share columns) or `"ticker"` (each ticker gets its own column group). |
| `auto_adjust` | bool | `False` | Adjust OHLC for splits/dividends. Note: default is `False` (unlike `Ticker.history()`). |
| `prepost` | bool | `False` | Include pre/post-market data. |
| `actions` | bool | `True` | Include dividends and splits. |
| `threads` | bool or int | `True` | Enable multithreading for faster downloads. Set to `True` for auto thread count or specify number. |

### Return Type

**pandas.DataFrame** with MultiIndex columns when downloading multiple tickers:

**When `group_by="column"` (default):**
- Columns: MultiIndex with levels `(Data Type, Ticker)`
- Example: `('Open', 'MSFT')`, `('High', 'MSFT')`, `('Open', 'AAPL')`, etc.

**When `group_by="ticker"`:**
- Columns: MultiIndex with levels `(Ticker, Data Type)`
- Example: `('MSFT', 'Open')`, `('MSFT', 'High')`, `('AAPL', 'Open')`, etc.

**When downloading a single ticker:**
- Standard DataFrame (same as `Ticker.history()`)

### Usage Examples

#### Batch download multiple tickers

```python
import yfinance as yf

tickers = ["MSFT", "AAPL", "GOOG"]
df = yf.download(tickers, period="1y", interval="1d", threads=True)

# Access data for specific ticker
msft_open = df['Open']['MSFT']  # when group_by="column"
```

#### Download with ticker grouping

```python
df = yf.download(
    ["MSFT", "AAPL"],
    start="2024-01-01",
    end="2024-12-31",
    group_by="ticker"
)

# Access data
msft_data = df['MSFT']  # All columns for MSFT
msft_close = df['MSFT']['Close']
```

#### Split into batches to avoid rate limits

```python
import time

tickers = ["MSFT", "AAPL", "GOOG", "TSLA", "NVDA", "META"]
batch_size = 3
all_data = []

for i in range(0, len(tickers), batch_size):
    batch = tickers[i:i+batch_size]
    df = yf.download(batch, period="1mo", threads=True)
    all_data.append(df)
    time.sleep(2)  # Rate limit mitigation
```

---

## Error Handling

### Common Errors

yfinance does **not always raise exceptions** for invalid tickers or missing data. Instead, it often returns an empty DataFrame or logs warnings.

### Invalid Ticker Symbol

```python
ticker = yf.Ticker("INVALIDTICKER")
df = ticker.history(period="1mo")

if df.empty:
    print("No data found - ticker may be invalid or delisted")
```

**Error messages you might see:**
- `"No data found for this date range, symbol may be delisted"`
- `"No timezone found, symbol may be delisted"`
- `"Failed to get ticker 'XXX' reason: Expecting value: line 1 column 1 (char 0)"`

### Data Unavailable for Date Range

```python
# Requesting data for a future date or outside available range
df = ticker.history(start="2030-01-01", end="2030-12-31")
# Result: Empty DataFrame
```

### Checking for Errors After Download

yfinance stores errors in a shared dictionary:

```python
import yfinance as yf

yf.download(["MSFT", "BADTICKER", "AAPL"], period="1mo")

# Check for errors
if yf.shared._ERRORS:
    print("Errors encountered:")
    for symbol, error in yf.shared._ERRORS.items():
        print(f"{symbol}: {error}")
```

### Recommended Error Handling Pattern

```python
import yfinance as yf
import pandas as pd

def fetch_ticker_data(symbol, start, end):
    """
    Fetch historical data with error handling.

    Returns:
        DataFrame or None if data unavailable
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval="1d")

        if df.empty:
            print(f"No data available for {symbol}")
            return None

        return df

    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

# Usage
data = fetch_ticker_data("MSFT", "2024-01-01", "2024-12-31")
if data is not None:
    print(f"Fetched {len(data)} rows")
```

---

## Rate Limiting and Best Practices

### Rate Limit Overview

Yahoo Finance does **not publish official rate limits**, but community observations suggest:
- Approximately **a few hundred requests per day** per IP address before throttling
- **429 "Too Many Requests"** error indicates you've hit the limit
- Rate limits have become stricter as of 2025

### Error: 429 Too Many Requests

```python
# You may see:
# requests.exceptions.HTTPError: 429 Client Error: Too Many Requests
```

This is usually **temporary** - Yahoo may block your IP for minutes to hours.

### Best Practices

#### 1. Add Delays Between Requests

```python
import time

for ticker_symbol in ticker_list:
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(period="1y")
    process_data(df)
    time.sleep(2)  # 2-second delay between requests
```

#### 2. Use Batch Downloads with `download()`

```python
# Instead of individual requests:
# for symbol in symbols:
#     yf.Ticker(symbol).history(...)

# Use batch download with multithreading:
df = yf.download(symbols, period="1y", threads=True)
```

This reduces total request count and is much faster.

#### 3. Implement Exponential Backoff for Retries

```python
import time
import requests

def fetch_with_retry(ticker_symbol, max_retries=3):
    """Fetch data with exponential backoff on failure."""
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period="1mo")

            if not df.empty:
                return df

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                wait_time = 2 ** attempt  # Exponential: 1s, 2s, 4s
                print(f"Rate limited. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise

    return None
```

#### 4. Cache Data Locally

```python
import os
import pandas as pd

def fetch_or_load_cached(symbol, start, end, cache_dir="cache"):
    """Fetch data or load from cache to minimize API calls."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = f"{cache_dir}/{symbol}_{start}_{end}.csv"

    if os.path.exists(cache_file):
        print(f"Loading {symbol} from cache")
        return pd.read_csv(cache_file, index_col=0, parse_dates=True)

    print(f"Fetching {symbol} from yfinance")
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end)

    if not df.empty:
        df.to_csv(cache_file)

    return df
```

#### 5. Request Only What You Need

```python
# Bad: Fetching all ticker info when you only need price history
ticker = yf.Ticker("MSFT")
info = ticker.info  # Makes additional API call
df = ticker.history(period="1y")

# Good: Fetch only history
ticker = yf.Ticker("MSFT")
df = ticker.history(period="1y")
```

#### 6. Batch Splitting Strategy

```python
import time

def download_in_batches(tickers, batch_size=10, delay=3):
    """Download tickers in batches with delays."""
    all_data = []

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        print(f"Downloading batch {i//batch_size + 1}: {batch}")

        df = yf.download(batch, period="1mo", threads=True)
        all_data.append(df)

        if i + batch_size < len(tickers):
            time.sleep(delay)  # Wait between batches

    return all_data
```

---

## Common Patterns

### Pattern 1: Fetch Daily OHLCV for Date Range

```python
import yfinance as yf

ticker = yf.Ticker("MSFT")
df = ticker.history(start="2024-01-01", end="2024-12-31", interval="1d")

# Extract OHLCV
ohlcv = df[['Open', 'High', 'Low', 'Close', 'Volume']]
print(ohlcv.head())
```

### Pattern 2: Get Latest Close Price

```python
ticker = yf.Ticker("AAPL")
df = ticker.history(period="1d")
latest_close = df['Close'].iloc[-1]
latest_date = df.index[-1]

print(f"Latest close for AAPL on {latest_date}: ${latest_close:.2f}")
```

### Pattern 3: Fallback from Primary Data Source

```python
def get_stock_data(symbol, start, end):
    """Try primary API first, fallback to yfinance."""
    try:
        # Try primary API (e.g., Schwab)
        data = primary_api.get_price_history(symbol, start, end)
        return data
    except Exception as e:
        print(f"Primary API failed: {e}. Falling back to yfinance.")

        # Fallback to yfinance
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end)

        if df.empty:
            raise ValueError(f"No data available for {symbol}")

        return df
```

### Pattern 4: Compare Stock to Benchmark (S&P 500)

```python
import yfinance as yf

# Fetch stock and benchmark data
stock_ticker = yf.Ticker("TSLA")
sp500_ticker = yf.Ticker("^GSPC")

stock_data = stock_ticker.history(start="2024-01-01", end="2024-12-31")
sp500_data = sp500_ticker.history(start="2024-01-01", end="2024-12-31")

# Calculate returns
stock_return = (stock_data['Close'].iloc[-1] / stock_data['Close'].iloc[0] - 1) * 100
sp500_return = (sp500_data['Close'].iloc[-1] / sp500_data['Close'].iloc[0] - 1) * 100

print(f"Stock return: {stock_return:.2f}%")
print(f"S&P 500 return: {sp500_return:.2f}%")
```

### Pattern 5: Download Multiple Tickers Safely

```python
import yfinance as yf
import time

def safe_batch_download(tickers, start, end, batch_size=10):
    """Download multiple tickers with rate limit protection."""
    results = {}

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]

        try:
            df = yf.download(
                batch,
                start=start,
                end=end,
                group_by="ticker",
                threads=True
            )

            # Store each ticker's data separately
            for ticker in batch:
                if ticker in df.columns.levels[0]:
                    results[ticker] = df[ticker]

            # Rate limit mitigation
            if i + batch_size < len(tickers):
                time.sleep(3)

        except Exception as e:
            print(f"Batch {i//batch_size + 1} failed: {e}")

    return results
```

---

## Summary

**Key Points:**
- yfinance is a web scraper, not an official API - expect occasional failures
- Use `Ticker.history()` for single ticker, `download()` for multiple tickers with threading
- Always check for empty DataFrames - yfinance often doesn't raise exceptions
- Implement delays (2-5 seconds) between requests to avoid 429 errors
- Cache data locally to minimize API calls
- Use batch downloads instead of individual requests when fetching multiple tickers
- Consider yfinance as a fallback, not a primary data source

**Best for:**
- Quick prototyping and analysis
- Fallback when primary APIs are unavailable
- Historical data for visualization and backtesting

**Not recommended for:**
- High-frequency trading or real-time applications
- Production systems requiring guaranteed uptime
- Applications needing >1000 requests/day per IP

---

## Sources

- [yfinance Library - A Complete Guide - AlgoTrading101 Blog](https://algotrading101.com/learn/yfinance-guide/)
- [yfinance documentation](https://ranaroussi.github.io/yfinance/)
- [Ticker and Tickers — yfinance](https://ranaroussi.github.io/yfinance/reference/yfinance.ticker_tickers.html)
- [Functions and Utilities — yfinance](https://ranaroussi.github.io/yfinance/reference/yfinance.functions.html)
- [Rate Limiting and API Best Practices for yfinance - Sling Academy](https://www.slingacademy.com/rate-limiting-and-api-best-practices-for-yfinance/)
- [Error Handling · ranaroussi/yfinance · Discussion #1555](https://github.com/ranaroussi/yfinance/discussions/1555)
- [Pandas DataFrame Explained: yfinance Multiindex Tutorial for Beginners | Medium](https://medium.com/@research_61401/pandas-dataframe-explained-yfinance-multiindex-tutorial-for-beginners-cbd9739f45c1)
