"""
Tests for AI response parsing and ticker normalization (stories 003-005, 003-006, 003-009).

Behavioral tests for JSON parsing, validation, malformed response retry,
rate limit handling, and ticker normalization.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestAIResponseParsing:
    """Test AI response parsing (story-003-005)."""

    def test_strip_markdown_code_fences_and_parse_json(self):
        """Strip markdown code fences before parsing JSON."""
        from src.ai_parser import parse_ai_response

        json_with_fences = '''```json
        {
            "tickers": ["AAPL"],
            "ticker_sentiments": ["bullish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": true,
            "confidence": 0.8,
            "reasoning_summary": "Strong DD"
        }
        ```'''

        result = parse_ai_response(json_with_fences)

        assert result['tickers'] == ['AAPL']
        assert result['sentiment'] == 'bullish'

    def test_validate_seven_required_fields(self):
        """Validate 7 required fields present."""
        from src.ai_parser import parse_ai_response

        valid_json = '''
        {
            "tickers": ["TSLA"],
            "ticker_sentiments": ["bearish"],
            "sentiment": "bearish",
            "sarcasm_detected": true,
            "has_reasoning": false,
            "confidence": 0.6,
            "reasoning_summary": null
        }
        '''

        result = parse_ai_response(valid_json)

        assert 'tickers' in result
        assert 'ticker_sentiments' in result
        assert 'sentiment' in result
        assert 'sarcasm_detected' in result
        assert 'has_reasoning' in result
        assert 'confidence' in result
        assert 'reasoning_summary' in result

    @pytest.mark.parametrize('sentiment,normalized', [
        ('bullish', 'bullish'),
        ('BULLISH', 'bullish'),
        ('Bullish', 'bullish'),
        ('bearish', 'bearish'),
        ('BEARISH', 'bearish'),
        ('neutral', 'neutral'),
        ('NEUTRAL', 'neutral'),
    ])
    def test_sentiment_case_insensitive(self, sentiment, normalized):
        """Sentiment values are case-insensitive."""
        from src.ai_parser import parse_ai_response

        json_str = f'''
        {{
            "tickers": ["AAPL"],
            "ticker_sentiments": ["bullish"],
            "sentiment": "{sentiment}",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "confidence": 0.5,
            "reasoning_summary": null
        }}
        '''

        result = parse_ai_response(json_str)
        assert result['sentiment'] == normalized

    def test_confidence_clamped_to_0_1_with_debug_log(self):
        """Confidence clamped to [0.0, 1.0] with debug log if out of range."""
        from src.ai_parser import parse_ai_response

        # Confidence > 1.0
        json_over = '''
        {
            "tickers": [],
            "ticker_sentiments": [],
            "sentiment": "neutral",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "confidence": 1.5,
            "reasoning_summary": null
        }
        '''

        with patch('structlog.get_logger') as mock_logger:
            logger_instance = MagicMock()
            mock_logger.return_value = logger_instance

            result = parse_ai_response(json_over)

            assert result['confidence'] == 1.0
            logger_instance.debug.assert_called()

        # Confidence < 0.0
        json_under = '''
        {
            "tickers": [],
            "ticker_sentiments": [],
            "sentiment": "neutral",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "confidence": -0.2,
            "reasoning_summary": null
        }
        '''

        with patch('structlog.get_logger') as mock_logger:
            logger_instance = MagicMock()
            mock_logger.return_value = logger_instance

            result = parse_ai_response(json_under)

            assert result['confidence'] == 0.0
            logger_instance.debug.assert_called()

    def test_reasoning_summary_null_when_has_reasoning_false(self):
        """reasoning_summary must be null when has_reasoning is false."""
        from src.ai_parser import parse_ai_response

        json_str = '''
        {
            "tickers": ["MSFT"],
            "ticker_sentiments": ["neutral"],
            "sentiment": "neutral",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "confidence": 0.5,
            "reasoning_summary": null
        }
        '''

        result = parse_ai_response(json_str)

        assert result['has_reasoning'] is False
        assert result['reasoning_summary'] is None

    def test_ticker_sentiments_count_matches_tickers(self):
        """ticker_sentiments count must match tickers count."""
        from src.ai_parser import parse_ai_response

        valid = '''
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "ticker_sentiments": ["bullish", "neutral", "bearish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "confidence": 0.6,
            "reasoning_summary": null
        }
        '''

        result = parse_ai_response(valid)
        assert len(result['tickers']) == len(result['ticker_sentiments'])

    def test_mismatched_counts_raises_validation_error(self):
        """Mismatched ticker/sentiment counts raise validation error."""
        from src.ai_parser import parse_ai_response

        invalid = '''
        {
            "tickers": ["AAPL", "MSFT"],
            "ticker_sentiments": ["bullish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "confidence": 0.5,
            "reasoning_summary": null
        }
        '''

        with pytest.raises(Exception):
            parse_ai_response(invalid)

    def test_extra_fields_ignored(self):
        """Extra fields in response are ignored."""
        from src.ai_parser import parse_ai_response

        json_extra = '''
        {
            "tickers": ["AAPL"],
            "ticker_sentiments": ["bullish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "confidence": 0.7,
            "reasoning_summary": null,
            "extra_field": "ignored",
            "another": 123
        }
        '''

        result = parse_ai_response(json_extra)
        assert result['tickers'] == ['AAPL']

    def test_missing_required_field_raises_error(self):
        """Missing required field raises validation error."""
        from src.ai_parser import parse_ai_response

        missing = '''
        {
            "tickers": ["AAPL"],
            "ticker_sentiments": ["bullish"],
            "sentiment": "bullish",
            "sarcasm_detected": false,
            "has_reasoning": false,
            "reasoning_summary": null
        }
        '''

        with pytest.raises(Exception):
            parse_ai_response(missing)


class TestTickerNormalization:
    """Test ticker normalization (story-003-005)."""

    def test_ticker_uppercase_normalization(self):
        """Tickers normalized to uppercase."""
        from src.ai_parser import normalize_tickers

        tickers = ['aapl', 'MSFT', 'GoOgL']
        normalized_tickers, normalized_sentiments = normalize_tickers(tickers)

        assert normalized_tickers == ['AAPL', 'MSFT', 'GOOGL']
        assert normalized_sentiments == []

    def test_company_name_resolution(self):
        """Company names resolved to ticker symbols."""
        from src.ai_parser import normalize_tickers

        # Common company references
        tickers = ['the mouse', 'Apple', 'Tesla']
        normalized_tickers, normalized_sentiments = normalize_tickers(tickers)

        # Should resolve 'the mouse' to DIS, 'Apple' to AAPL, 'Tesla' to TSLA
        assert 'DIS' in normalized_tickers
        assert 'AAPL' in normalized_tickers
        assert 'TSLA' in normalized_tickers
        assert normalized_sentiments == []

    def test_exclusion_list_filtering(self):
        """Non-tickers excluded (I, A, CEO, DD, YOLO)."""
        from src.ai_parser import normalize_tickers

        tickers = ['AAPL', 'I', 'A', 'CEO', 'DD', 'YOLO', 'MSFT']
        normalized_tickers, normalized_sentiments = normalize_tickers(tickers)

        # Should exclude non-tickers
        assert 'I' not in normalized_tickers
        assert 'A' not in normalized_tickers
        assert 'CEO' not in normalized_tickers
        assert 'DD' not in normalized_tickers
        assert 'YOLO' not in normalized_tickers

        # Should keep valid tickers
        assert 'AAPL' in normalized_tickers
        assert 'MSFT' in normalized_tickers
        assert normalized_sentiments == []

    def test_crypto_tickers_included(self):
        """Crypto tickers included (BTC, ETH, etc.)."""
        from src.ai_parser import normalize_tickers

        tickers = ['BTC', 'ETH', 'DOGE']
        normalized_tickers, normalized_sentiments = normalize_tickers(tickers)

        assert 'BTC' in normalized_tickers
        assert 'ETH' in normalized_tickers
        assert 'DOGE' in normalized_tickers
        assert normalized_sentiments == []

    def test_deduplication(self):
        """Duplicate tickers deduplicated."""
        from src.ai_parser import normalize_tickers

        tickers = ['AAPL', 'aapl', 'AAPL', 'MSFT', 'msft']
        normalized_tickers, normalized_sentiments = normalize_tickers(tickers)

        # Should have unique values only
        assert len(normalized_tickers) == 2
        assert 'AAPL' in normalized_tickers
        assert 'MSFT' in normalized_tickers
        assert normalized_sentiments == []

    def test_ticker_sentiments_filtered_to_match_tickers(self):
        """ticker_sentiments array filtered to match cleaned tickers."""
        from src.ai_parser import normalize_tickers

        # Test filtering: 'I' and 'A' should be excluded, along with their sentiments
        tickers = ['AAPL', 'I', 'A', 'MSFT']
        sentiments = ['bullish', 'neutral', 'bearish', 'neutral']

        normalized_tickers, normalized_sentiments = normalize_tickers(tickers, sentiments)

        assert normalized_tickers == ['AAPL', 'MSFT']
        assert normalized_sentiments == ['bullish', 'neutral']

    def test_ticker_sentiments_deduplicated_with_tickers(self):
        """ticker_sentiments deduplicated to match ticker deduplication."""
        from src.ai_parser import normalize_tickers

        # When duplicate tickers are removed, only keep sentiment from first occurrence
        tickers = ['AAPL', 'MSFT', 'aapl', 'NVDA']
        sentiments = ['bullish', 'neutral', 'bearish', 'bullish']

        normalized_tickers, normalized_sentiments = normalize_tickers(tickers, sentiments)

        # Should keep first occurrence of AAPL (bullish), not the duplicate (bearish)
        assert normalized_tickers == ['AAPL', 'MSFT', 'NVDA']
        assert normalized_sentiments == ['bullish', 'neutral', 'bullish']

    def test_company_name_resolution_with_sentiments(self):
        """Company name resolution preserves corresponding sentiments."""
        from src.ai_parser import normalize_tickers

        tickers = ['the mouse', 'Apple', 'I', 'Tesla']
        sentiments = ['bullish', 'neutral', 'bearish', 'bullish']

        normalized_tickers, normalized_sentiments = normalize_tickers(tickers, sentiments)

        # 'I' should be excluded, others resolved to tickers
        assert normalized_tickers == ['DIS', 'AAPL', 'TSLA']
        assert normalized_sentiments == ['bullish', 'neutral', 'bullish']


class TestMalformedJSONRetry:
    """Test malformed JSON retry logic (story-003-006)."""

    @pytest.mark.asyncio
    async def test_malformed_json_retries_once(self):
        """Malformed JSON triggers one retry."""
        from src.ai_batch import process_comment_with_retry

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            # First response is malformed, second is valid
            mock_client.send_chat_completion.side_effect = [
                {'content': 'not valid json{[', 'usage': {'total_tokens': 100}},
                {'content': '{"tickers":[],"ticker_sentiments":[],"sentiment":"neutral","sarcasm_detected":false,"has_reasoning":false,"confidence":0.5,"reasoning_summary":null}', 'usage': {'total_tokens': 100}}
            ]
            mock_client_class.return_value = mock_client

            comment = {'reddit_id': 'test', 'body': 'Test comment'}
            result = await process_comment_with_retry(comment, mock_client, run_id=1)

            # Should have retried once
            assert mock_client.send_chat_completion.call_count == 2
            assert result is not None

    @pytest.mark.asyncio
    async def test_second_failure_skips_and_logs_warning(self):
        """Second malformed response skips comment and logs warning."""
        from src.ai_batch import process_comment_with_retry

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            # Both responses malformed
            mock_client.send_chat_completion.side_effect = [
                {'content': 'bad json 1', 'usage': {'total_tokens': 100}},
                {'content': 'bad json 2', 'usage': {'total_tokens': 100}}
            ]
            mock_client_class.return_value = mock_client

            with patch('structlog.get_logger') as mock_logger:
                logger_instance = MagicMock()
                mock_logger.return_value = logger_instance

                comment = {'reddit_id': 'test', 'body': 'Test'}
                result = await process_comment_with_retry(comment, mock_client, run_id=1)

                # Should skip after 2 attempts
                assert result is None
                assert mock_client.send_chat_completion.call_count == 2
                logger_instance.warning.assert_called()

    @pytest.mark.asyncio
    async def test_retry_is_per_comment_not_per_batch(self):
        """Retry logic is per-comment, not per-batch."""
        from src.ai_batch import process_single_batch

        comments = [
            {'reddit_id': 'good', 'body': 'Good comment'},
            {'reddit_id': 'bad', 'body': 'Bad comment'},
        ]

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()

            call_count = 0

            async def mock_send(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                # 'bad' comment always returns malformed
                if call_count == 2 or call_count == 3:  # bad comment attempts
                    return {'content': 'malformed', 'usage': {'total_tokens': 100}}
                return {'content': '{"tickers":[],"ticker_sentiments":[],"sentiment":"neutral","sarcasm_detected":false,"has_reasoning":false,"confidence":0.5,"reasoning_summary":null}', 'usage': {'total_tokens': 100}}

            mock_client.send_chat_completion = mock_send
            mock_client_class.return_value = mock_client

            results = await process_single_batch(comments, mock_client, run_id=1)

            # Good comment should succeed, bad should fail after retry
            # Total calls: 1 (good) + 2 (bad with retry)
            assert call_count >= 3


class TestRateLimitHandling:
    """Test rate limit retry with exponential backoff (story-003-006)."""

    @pytest.mark.asyncio
    async def test_rate_limit_429_exponential_backoff(self):
        """Rate limit 429 triggers exponential backoff [1s, 2s, 4s, 8s] max 30s."""
        from src.ai_batch import process_comment_with_retry

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()

            # Simulate 429 errors
            from openai import RateLimitError

            mock_client.send_chat_completion.side_effect = [
                RateLimitError("Rate limit exceeded", response=MagicMock(status_code=429), body=None),
                RateLimitError("Rate limit exceeded", response=MagicMock(status_code=429), body=None),
                {'content': '{"tickers":[],"ticker_sentiments":[],"sentiment":"neutral","sarcasm_detected":false,"has_reasoning":false,"confidence":0.5,"reasoning_summary":null}', 'usage': {'total_tokens': 100}}
            ]
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                comment = {'reddit_id': 'test', 'body': 'Test'}
                result = await process_comment_with_retry(comment, mock_client, run_id=1)

                # Should have exponential backoff
                sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
                # First retry: 1s, second retry: 2s
                assert 1 in sleep_calls or 2 in sleep_calls

    @pytest.mark.asyncio
    async def test_rate_limit_max_3_retries(self):
        """Rate limit retries maximum 3 times."""
        from src.ai_batch import process_comment_with_retry

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()

            from openai import RateLimitError

            # Always return 429
            mock_client.send_chat_completion.side_effect = RateLimitError(
                "Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None
            )
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock):
                with patch('structlog.get_logger') as mock_logger:
                    logger_instance = MagicMock()
                    mock_logger.return_value = logger_instance

                    comment = {'reddit_id': 'test', 'body': 'Test'}
                    result = await process_comment_with_retry(comment, mock_client, run_id=1)

                    # Should stop after 3 retries
                    assert mock_client.send_chat_completion.call_count <= 4  # Initial + 3 retries

    @pytest.mark.asyncio
    async def test_backoff_max_30_seconds(self):
        """Backoff delay capped at maximum 30 seconds."""
        from src.ai_batch import calculate_backoff_delay

        # Exponential backoff: 1, 2, 4, 8, 16, 32...
        # Should cap at 30
        assert calculate_backoff_delay(0) == 1
        assert calculate_backoff_delay(1) == 2
        assert calculate_backoff_delay(2) == 4
        assert calculate_backoff_delay(3) == 8
        assert calculate_backoff_delay(4) == 16
        assert calculate_backoff_delay(5) <= 30
        assert calculate_backoff_delay(10) <= 30
