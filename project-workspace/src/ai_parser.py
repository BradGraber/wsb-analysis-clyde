"""AI response parsing and ticker normalization for WSB Analysis Tool.

This module provides functionality for:
1. Extracting and validating JSON from GPT-4o-mini responses
2. Normalizing ticker symbols (uppercase, company name resolution, exclusion filtering)
3. Custom exceptions for malformed responses

Key Functions:
    parse_ai_response() — Strip markdown fences, parse JSON, validate 7 required fields
    normalize_tickers() — Uppercase, resolve company names, filter exclusions, deduplicate

Validation Rules:
    - Sentiment: accepts only "bullish", "bearish", "neutral" (case-insensitive)
    - Confidence: float clamped to [0.0, 1.0] with debug log if out of range
    - Reasoning: reasoning_summary must be null when has_reasoning is false
    - Ticker counts: ticker_sentiments array must match tickers array length
    - Extra fields: silently ignored
    - Missing fields: raises ValueError

Response Format (7 required fields):
    {
        "tickers": ["AAPL", "MSFT"],
        "ticker_sentiments": ["bullish", "neutral"],
        "sentiment": "bullish",
        "sarcasm_detected": false,
        "has_reasoning": true,
        "confidence": 0.8,
        "reasoning_summary": "Strong DD with price targets"
    }
"""

import json
import re
import structlog
from typing import Dict, List, Any, Tuple


class MalformedResponseError(Exception):
    """Raised when AI response JSON cannot be parsed or is invalid.

    This exception is consumed by retry logic in story-003-006 (ai_batch.py).
    """
    pass


# Company name to ticker mapping (configurable)
COMPANY_NAME_MAP = {
    'the mouse': 'DIS',
    'apple': 'AAPL',
    'tesla': 'TSLA',
    'microsoft': 'MSFT',
    'google': 'GOOGL',
    'amazon': 'AMZN',
    'meta': 'META',
    'facebook': 'META',
    'nvidia': 'NVDA',
    'amd': 'AMD',
    'intel': 'INTC',
    'gamestop': 'GME',
    'amc': 'AMC',
    'blackberry': 'BB',
    'palantir': 'PLTR',
    'nio': 'NIO',
    'lucid': 'LCID',
    'rivian': 'RIVN',
    'disney': 'DIS',
    'zuck': 'META',
    'zuckerberg': 'META',
}

# Exclusion list: common words that are not tickers (configurable)
TICKER_EXCLUSION_LIST = {'I', 'A', 'CEO', 'DD', 'YOLO'}


def parse_ai_response(raw_content: str) -> Dict[str, Any]:
    """Extract and validate AI response JSON.

    Strips markdown code fences (```json...```), parses JSON, and validates
    the 7-field structure required for AI sentiment analysis.

    Args:
        raw_content: Raw GPT-4o-mini response text (may include markdown)

    Returns:
        Dict with validated fields:
            - tickers: List[str] — Ticker symbols
            - ticker_sentiments: List[str] — Per-ticker sentiments
            - sentiment: str — Overall sentiment (normalized lowercase)
            - sarcasm_detected: bool — Sarcasm flag
            - has_reasoning: bool — Reasoning presence flag
            - confidence: float — AI confidence (clamped to [0.0, 1.0])
            - reasoning_summary: Optional[str] — Reasoning text (or None)

    Raises:
        MalformedResponseError: If JSON cannot be parsed
        ValueError: If required fields missing or validation fails

    Examples:
        >>> parse_ai_response('```json\\n{"tickers": ["AAPL"], ...}\\n```')
        {'tickers': ['AAPL'], 'sentiment': 'bullish', ...}
    """
    # Strip markdown code fences and surrounding whitespace
    stripped = raw_content.strip()

    # Remove ```json and ``` delimiters if present
    if stripped.startswith('```'):
        # Find the first newline after opening fence
        start_idx = stripped.find('\n')
        if start_idx == -1:
            # No newline, might be malformed
            start_idx = 3  # Skip past ```
        else:
            start_idx += 1  # Skip past the newline

        # Find closing fence
        end_idx = stripped.rfind('```')
        if end_idx > start_idx:
            stripped = stripped[start_idx:end_idx].strip()
        else:
            # No closing fence found, just remove opening
            stripped = stripped[start_idx:].strip()

    # Parse JSON
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        structlog.get_logger().warning("Failed to parse AI response JSON", error=str(e), raw_content=raw_content[:200])
        raise MalformedResponseError(f"Invalid JSON: {e}")

    # Validate required fields
    required_fields = [
        'tickers', 'ticker_sentiments', 'sentiment', 'sarcasm_detected',
        'has_reasoning', 'confidence', 'reasoning_summary'
    ]

    missing_fields = [f for f in required_fields if f not in data]
    if missing_fields:
        structlog.get_logger().warning("Missing required fields in AI response", missing=missing_fields)
        raise ValueError(f"Missing required fields: {missing_fields}")

    # Validate and normalize sentiment
    valid_sentiments = {'bullish', 'bearish', 'neutral'}
    sentiment = data['sentiment']

    if isinstance(sentiment, str):
        sentiment_lower = sentiment.lower()
        if sentiment_lower not in valid_sentiments:
            structlog.get_logger().warning("Invalid sentiment value", sentiment=sentiment)
            raise ValueError(f"Invalid sentiment: {sentiment}. Must be one of {valid_sentiments}")
        data['sentiment'] = sentiment_lower
    else:
        structlog.get_logger().warning("Sentiment is not a string", sentiment_type=type(sentiment).__name__)
        raise ValueError(f"Sentiment must be a string, got {type(sentiment).__name__}")

    # Validate and clamp confidence
    confidence = data['confidence']

    if not isinstance(confidence, (int, float)):
        structlog.get_logger().warning("Confidence is not numeric", confidence_type=type(confidence).__name__)
        raise ValueError(f"Confidence must be numeric, got {type(confidence).__name__}")

    # Clamp to [0.0, 1.0] with debug log
    original_confidence = confidence
    confidence = max(0.0, min(1.0, float(confidence)))

    if confidence != original_confidence:
        structlog.get_logger().debug(
            "Confidence clamped to valid range",
            original=original_confidence,
            clamped=confidence
        )

    data['confidence'] = confidence

    # Validate reasoning_summary when has_reasoning is false
    if not data['has_reasoning'] and data['reasoning_summary'] is not None:
        structlog.get_logger().warning(
            "reasoning_summary should be null when has_reasoning is false",
            has_reasoning=data['has_reasoning'],
            reasoning_summary=data['reasoning_summary']
        )
        # Don't raise — log warning and allow (defensive)

    # Validate ticker_sentiments count matches tickers count
    tickers = data['tickers']
    ticker_sentiments = data['ticker_sentiments']

    if not isinstance(tickers, list):
        raise ValueError(f"tickers must be a list, got {type(tickers).__name__}")

    if not isinstance(ticker_sentiments, list):
        raise ValueError(f"ticker_sentiments must be a list, got {type(ticker_sentiments).__name__}")

    if len(tickers) != len(ticker_sentiments):
        structlog.get_logger().warning(
            "Ticker/sentiment count mismatch",
            tickers_count=len(tickers),
            sentiments_count=len(ticker_sentiments)
        )
        raise ValueError(
            f"ticker_sentiments count ({len(ticker_sentiments)}) must match tickers count ({len(tickers)})"
        )

    # Extra fields are silently ignored (dict allows them)

    return data


def normalize_tickers(tickers: List[str], ticker_sentiments: List[str] = None) -> Tuple[List[str], List[str]]:
    """Normalize ticker symbols to uppercase, resolve company names, filter exclusions.

    Normalization steps:
    1. Uppercase conversion
    2. Company name resolution (e.g., "the mouse" → "DIS", "Apple" → "AAPL")
    3. Exclusion filtering (removes: I, A, CEO, DD, YOLO)
    4. Deduplication (preserves order of first occurrence)

    When ticker_sentiments is provided, it is filtered and deduplicated to match the
    cleaned tickers list. Sentiments are kept in sync with their corresponding tickers.

    Args:
        tickers: List of raw ticker strings (may include lowercase, company names)
        ticker_sentiments: Optional list of sentiment strings (same length as tickers)

    Returns:
        Tuple of (normalized_tickers, normalized_sentiments) where:
        - normalized_tickers: List of normalized uppercase ticker symbols (deduplicated, exclusions removed)
        - normalized_sentiments: List of sentiments matching the normalized tickers (or empty list if not provided)

    Examples:
        >>> normalize_tickers(['aapl', 'MSFT', 'aapl', 'I', 'the mouse'])
        (['AAPL', 'MSFT', 'DIS'], [])

        >>> normalize_tickers(['aapl', 'I', 'AAPL'], ['bullish', 'neutral', 'bearish'])
        (['AAPL'], ['bullish'])
    """
    normalized_tickers = []
    normalized_sentiments = []
    seen = set()

    # Track whether we have sentiments to process
    has_sentiments = ticker_sentiments is not None and len(ticker_sentiments) == len(tickers)

    for i, ticker in enumerate(tickers):
        # Convert to string if not already
        ticker_str = str(ticker).strip()

        # Skip empty strings
        if not ticker_str:
            continue

        # Check if it's a company name (case-insensitive)
        ticker_lower = ticker_str.lower()
        if ticker_lower in COMPANY_NAME_MAP:
            ticker_str = COMPANY_NAME_MAP[ticker_lower]
        else:
            # Uppercase conversion
            ticker_str = ticker_str.upper()

        # Filter exclusions
        if ticker_str in TICKER_EXCLUSION_LIST:
            continue

        # Deduplicate
        if ticker_str not in seen:
            seen.add(ticker_str)
            normalized_tickers.append(ticker_str)
            if has_sentiments:
                normalized_sentiments.append(ticker_sentiments[i])

    return (normalized_tickers, normalized_sentiments)
