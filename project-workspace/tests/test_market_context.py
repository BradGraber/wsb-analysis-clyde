"""
Tests for market context provider (market_context.py).

Tests cover yfinance data fetching, formatting, and gate logic
for the 0.8% threshold that controls market context injection.
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd


class TestFetchMarketContext:
    """Test fetching market index data."""

    def test_returns_today_and_five_day_data(self):
        """fetch_market_context returns dict with today and five_day keys."""
        from src.market_context import fetch_market_context

        # Build a simple 5-day DataFrame per ticker
        dates = pd.date_range("2026-02-06", periods=5, freq="B")
        spy_data = pd.DataFrame({"Close": [590, 585, 582, 580, 571]}, index=dates)
        qqq_data = pd.DataFrame({"Close": [500, 495, 490, 488, 478]}, index=dates)
        iwm_data = pd.DataFrame({"Close": [220, 219, 218, 217, 215]}, index=dates)

        ticker_map = {"SPY": spy_data, "QQQ": qqq_data, "IWM": iwm_data}

        def mock_ticker(symbol):
            t = MagicMock()
            t.history.return_value = ticker_map[symbol]
            return t

        with patch("src.market_context.yf") as mock_yf:
            mock_yf.Ticker = mock_ticker
            result = fetch_market_context()

        assert result is not None
        assert "today" in result
        assert "five_day" in result
        assert set(result["today"].keys()) == {"SPY", "QQQ", "IWM"}
        assert set(result["five_day"].keys()) == {"SPY", "QQQ", "IWM"}

    def test_today_pct_calculated_correctly(self):
        """Today's pct change = (last close - prev close) / prev close * 100."""
        from src.market_context import fetch_market_context

        dates = pd.date_range("2026-02-06", periods=5, freq="B")
        # SPY: prev close 580, today close 571 -> (571-580)/580 * 100 = -1.55%
        spy_data = pd.DataFrame({"Close": [590, 585, 582, 580, 571]}, index=dates)
        qqq_data = pd.DataFrame({"Close": [500, 500, 500, 500, 500]}, index=dates)
        iwm_data = pd.DataFrame({"Close": [220, 220, 220, 220, 220]}, index=dates)

        ticker_map = {"SPY": spy_data, "QQQ": qqq_data, "IWM": iwm_data}

        def mock_ticker(symbol):
            t = MagicMock()
            t.history.return_value = ticker_map[symbol]
            return t

        with patch("src.market_context.yf") as mock_yf:
            mock_yf.Ticker = mock_ticker
            result = fetch_market_context()

        assert result["today"]["SPY"] == pytest.approx(-1.55, abs=0.01)
        assert result["today"]["QQQ"] == pytest.approx(0.0, abs=0.01)

    def test_five_day_pct_uses_first_and_last_close(self):
        """Five-day pct = (last close - first close) / first close * 100."""
        from src.market_context import fetch_market_context

        dates = pd.date_range("2026-02-06", periods=5, freq="B")
        # SPY: first close 590, last close 571 -> (571-590)/590 * 100 = -3.22%
        spy_data = pd.DataFrame({"Close": [590, 585, 582, 580, 571]}, index=dates)
        qqq_data = pd.DataFrame({"Close": [500, 500, 500, 500, 500]}, index=dates)
        iwm_data = pd.DataFrame({"Close": [220, 220, 220, 220, 220]}, index=dates)

        ticker_map = {"SPY": spy_data, "QQQ": qqq_data, "IWM": iwm_data}

        def mock_ticker(symbol):
            t = MagicMock()
            t.history.return_value = ticker_map[symbol]
            return t

        with patch("src.market_context.yf") as mock_yf:
            mock_yf.Ticker = mock_ticker
            result = fetch_market_context()

        assert result["five_day"]["SPY"] == pytest.approx(-3.22, abs=0.01)

    def test_returns_none_when_yfinance_not_installed(self):
        """Returns None when yfinance is not available."""
        from src import market_context
        from src.market_context import fetch_market_context

        original_yf = market_context.yf
        try:
            market_context.yf = None
            result = fetch_market_context()
            assert result is None
        finally:
            market_context.yf = original_yf

    def test_returns_none_when_all_tickers_fail(self):
        """Returns None when all ticker fetches fail."""
        from src.market_context import fetch_market_context

        def mock_ticker(symbol):
            t = MagicMock()
            t.history.side_effect = Exception("Network error")
            return t

        with patch("src.market_context.yf") as mock_yf:
            mock_yf.Ticker = mock_ticker
            result = fetch_market_context()

        assert result is None

    def test_partial_failure_returns_available_data(self):
        """When one ticker fails, returns data for the others."""
        from src.market_context import fetch_market_context

        dates = pd.date_range("2026-02-06", periods=5, freq="B")
        spy_data = pd.DataFrame({"Close": [590, 585, 582, 580, 571]}, index=dates)
        iwm_data = pd.DataFrame({"Close": [220, 219, 218, 217, 215]}, index=dates)

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "QQQ":
                t.history.side_effect = Exception("Timeout")
            else:
                data = {"SPY": spy_data, "IWM": iwm_data}
                t.history.return_value = data[symbol]
            return t

        with patch("src.market_context.yf") as mock_yf:
            mock_yf.Ticker = mock_ticker
            result = fetch_market_context()

        assert result is not None
        assert "SPY" in result["today"]
        assert "IWM" in result["today"]
        assert "QQQ" not in result["today"]

    def test_insufficient_history_skips_ticker(self):
        """Ticker with < 2 rows of history is skipped."""
        from src.market_context import fetch_market_context

        dates = pd.date_range("2026-02-12", periods=1, freq="B")
        spy_data = pd.DataFrame({"Close": [571]}, index=dates)
        qqq_data = pd.DataFrame({"Close": [478]}, index=dates)
        iwm_data = pd.DataFrame({"Close": [215]}, index=dates)

        ticker_map = {"SPY": spy_data, "QQQ": qqq_data, "IWM": iwm_data}

        def mock_ticker(symbol):
            t = MagicMock()
            t.history.return_value = ticker_map[symbol]
            return t

        with patch("src.market_context.yf") as mock_yf:
            mock_yf.Ticker = mock_ticker
            result = fetch_market_context()

        # All tickers had insufficient data
        assert result is None


class TestShouldIncludeContext:
    """Test the 0.8% gate check."""

    def test_returns_true_when_any_index_above_threshold(self):
        """Returns True when any index moved >= 0.8%."""
        from src.market_context import should_include_context

        data = {
            "today": {"SPY": -1.5, "QQQ": -2.3, "IWM": -0.8},
            "five_day": {"SPY": -3.1, "QQQ": -4.5, "IWM": -1.2},
        }
        assert should_include_context(data) is True

    def test_returns_true_for_positive_moves(self):
        """Positive moves >= 0.8% also trigger inclusion."""
        from src.market_context import should_include_context

        data = {
            "today": {"SPY": 1.2, "QQQ": 0.3, "IWM": 0.1},
            "five_day": {},
        }
        assert should_include_context(data) is True

    def test_returns_false_when_all_below_threshold(self):
        """Returns False when all indexes moved < 0.8%."""
        from src.market_context import should_include_context

        data = {
            "today": {"SPY": 0.2, "QQQ": -0.3, "IWM": 0.1},
            "five_day": {"SPY": 1.0, "QQQ": -2.0, "IWM": 0.5},
        }
        assert should_include_context(data) is False

    def test_returns_false_for_none_data(self):
        """Returns False when data is None."""
        from src.market_context import should_include_context

        assert should_include_context(None) is False

    def test_custom_threshold(self):
        """Custom threshold works."""
        from src.market_context import should_include_context

        data = {"today": {"SPY": 0.5, "QQQ": 0.3, "IWM": 0.2}, "five_day": {}}
        assert should_include_context(data, threshold=0.4) is True
        assert should_include_context(data, threshold=0.6) is False

    def test_exactly_at_threshold(self):
        """Exactly at threshold triggers inclusion."""
        from src.market_context import should_include_context

        data = {"today": {"SPY": 0.8, "QQQ": 0.0, "IWM": 0.0}, "five_day": {}}
        assert should_include_context(data) is True


class TestFormatMarketContext:
    """Test formatting market data into prompt-ready string."""

    def test_formats_today_and_five_day(self):
        """Output includes today and 5-day trend lines."""
        from src.market_context import format_market_context

        data = {
            "today": {"SPY": -1.52, "QQQ": -2.31, "IWM": -0.84},
            "five_day": {"SPY": -3.10, "QQQ": -4.50, "IWM": -1.20},
        }
        result = format_market_context(data)

        assert "Market context (today):" in result
        assert "5-day trend:" in result
        assert "SPY" in result
        assert "QQQ" in result
        assert "IWM" in result

    def test_negative_values_have_minus_sign(self):
        """Negative percentages show minus sign."""
        from src.market_context import format_market_context

        data = {
            "today": {"SPY": -1.52, "QQQ": -2.31, "IWM": -0.84},
            "five_day": {"SPY": -3.10, "QQQ": -4.50, "IWM": -1.20},
        }
        result = format_market_context(data)

        assert "-1.52%" in result
        assert "-2.31%" in result

    def test_positive_values_have_plus_sign(self):
        """Positive percentages show plus sign."""
        from src.market_context import format_market_context

        data = {
            "today": {"SPY": 1.20, "QQQ": 0.50, "IWM": 0.10},
            "five_day": {"SPY": 2.50, "QQQ": 1.80, "IWM": 0.30},
        }
        result = format_market_context(data)

        assert "+1.2%" in result or "+1.20%" in result

    def test_includes_index_labels(self):
        """Output includes human-readable index labels."""
        from src.market_context import format_market_context

        data = {
            "today": {"SPY": -1.0, "QQQ": -0.5, "IWM": -0.3},
            "five_day": {"SPY": -2.0, "QQQ": -1.0, "IWM": -0.5},
        }
        result = format_market_context(data)

        assert "S&P 500" in result
        assert "Nasdaq 100" in result
        assert "Russell 2000" in result
