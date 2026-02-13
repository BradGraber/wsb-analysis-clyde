"""Market context provider for AI comment analysis.

Fetches index data (SPY, QQQ, IWM) via yfinance to give the sentiment
analyzer context about market conditions.  When major indexes move >= 0.8%,
the context is injected into the prompt so the model can distinguish
reactive venting from genuinely predictive commentary.
"""

import structlog
from typing import Dict, Optional

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]

logger = structlog.get_logger()

INDEXES = ["SPY", "QQQ", "IWM"]
INDEX_LABELS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000",
}


def fetch_market_context() -> Optional[Dict]:
    """Fetch today's move and 5-day trend for SPY, QQQ, IWM.

    Returns:
        Dict with 'today' and 'five_day' sub-dicts mapping ticker -> pct change,
        or None if yfinance fails entirely.

    Example return::

        {
            "today": {"SPY": -1.52, "QQQ": -2.31, "IWM": -0.84},
            "five_day": {"SPY": -3.10, "QQQ": -4.50, "IWM": -1.20},
        }
    """
    if yf is None:
        logger.warning("yfinance_not_installed")
        return None

    result: Dict = {"today": {}, "five_day": {}}

    for ticker in INDEXES:
        try:
            hist = yf.Ticker(ticker).history(period="5d")

            if hist.empty or len(hist) < 2:
                logger.warning("insufficient_history", ticker=ticker, rows=len(hist))
                continue

            # Today's move: last close vs previous close
            today_close = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2])
            today_pct = ((today_close - prev_close) / prev_close) * 100
            result["today"][ticker] = round(today_pct, 2)

            # 5-day trend: last close vs first close in the window
            first_close = float(hist["Close"].iloc[0])
            five_day_pct = ((today_close - first_close) / first_close) * 100
            result["five_day"][ticker] = round(five_day_pct, 2)

        except Exception as e:
            logger.warning("index_fetch_failed", ticker=ticker, error=str(e))
            continue

    if not result["today"]:
        logger.warning("no_index_data_fetched")
        return None

    return result


def should_include_context(data: Optional[Dict], threshold: float = 0.8) -> bool:
    """Gate check: returns True if any index moved >= threshold% today.

    Args:
        data: Output from fetch_market_context(), or None.
        threshold: Minimum absolute percent move to trigger inclusion (default 0.8%).
    """
    if data is None:
        return False
    return any(abs(pct) >= threshold for pct in data["today"].values())


def format_market_context(data: Dict) -> str:
    """Format market data into a concise prompt-ready string.

    Args:
        data: Output from fetch_market_context().

    Returns:
        Multi-line string suitable for injection into the user prompt.
    """
    today_parts = []
    for ticker in INDEXES:
        if ticker in data["today"]:
            pct = data["today"][ticker]
            sign = "+" if pct >= 0 else ""
            today_parts.append(f"{ticker} ({INDEX_LABELS[ticker]}): {sign}{pct}%")

    five_day_parts = []
    for ticker in INDEXES:
        if ticker in data["five_day"]:
            pct = data["five_day"][ticker]
            sign = "+" if pct >= 0 else ""
            five_day_parts.append(f"{ticker}: {sign}{pct}%")

    lines = [f"Market context (today): {', '.join(today_parts)}"]
    if five_day_parts:
        lines.append(f"5-day trend: {', '.join(five_day_parts)}")

    return "\n".join(lines)
