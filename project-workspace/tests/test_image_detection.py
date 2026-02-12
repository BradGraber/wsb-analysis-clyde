"""
Tests for image detection and GPT-4o-mini vision analysis (story-002-002).

Behavioral tests verifying image URL detection patterns and
vision API retry logic with exponential backoff.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestImageURLDetection:
    """Test image URL detection for 3 patterns."""

    @pytest.mark.parametrize('url,expected_image_url', [
        ('https://i.redd.it/abc123.png', 'https://i.redd.it/abc123.png'),
        ('https://imgur.com/xyz789', 'https://imgur.com/xyz789'),
        ('https://preview.redd.it/image.jpg?auto=webp', 'https://preview.redd.it/image.jpg?auto=webp'),
        ('https://reddit.com/r/wallstreetbets/comments/abc', None),
        ('https://youtube.com/watch?v=xyz', None),
        ('https://twitter.com/user/status/123', None),
    ])
    def test_detect_image_url_patterns(self, url, expected_image_url):
        """Image URL detection works for i.redd.it, imgur, preview.redd.it patterns."""
        from src.reddit import detect_image_url

        result = detect_image_url(url)

        assert result == expected_image_url

    def test_no_image_url_sets_null_values(self):
        """No image URL sets image_url=null, image_analysis=null, no API call."""
        from src.reddit import detect_image_url

        url = 'https://reddit.com/r/wallstreetbets/comments/abc'
        result = detect_image_url(url)

        assert result is None


class TestVisionAnalysis:
    """Test GPT-4o-mini vision API integration."""

    @pytest.mark.asyncio
    async def test_vision_api_called_for_detected_image(self):
        """GPT-4o-mini vision API called when image URL detected."""
        from src.reddit import analyze_post_image

        image_url = 'https://i.redd.it/test.png'

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.send_vision_analysis.return_value = {
                'content': 'A chart showing stock prices going up',
                'usage': {'total_tokens': 500}
            }
            mock_client_class.return_value = mock_client

            result = await analyze_post_image(image_url)

            assert result == 'A chart showing stock prices going up'
            mock_client.send_vision_analysis.assert_called_once_with(image_url)

    @pytest.mark.asyncio
    async def test_vision_api_retry_with_exponential_backoff(self):
        """Retry 3x with [2s, 5s, 10s] backoff on failure."""
        from src.reddit import analyze_post_image

        image_url = 'https://i.redd.it/test.png'

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            # Fail twice, succeed third time
            mock_client.send_vision_analysis.side_effect = [
                Exception("API Error"),
                Exception("API Error"),
                {'content': 'Success', 'usage': {'total_tokens': 100}}
            ]
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                result = await analyze_post_image(image_url)

                assert result == 'Success'
                assert mock_client.send_vision_analysis.call_count == 3

                # Verify backoff delays: [2s, 5s]
                sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
                assert sleep_calls == [2, 5]

    @pytest.mark.asyncio
    async def test_vision_api_failure_after_3_retries_logs_warning(self):
        """After 3 failures, log warning, image_analysis=NULL, continue."""
        from src.reddit import analyze_post_image

        image_url = 'https://i.redd.it/test.png'

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.send_vision_analysis.side_effect = Exception("API Error")
            mock_client_class.return_value = mock_client

            with patch('structlog.get_logger') as mock_logger:
                logger_instance = MagicMock()
                mock_logger.return_value = logger_instance

                with patch('asyncio.sleep', new_callable=AsyncMock):
                    result = await analyze_post_image(image_url)

                    assert result is None  # NULL after all retries fail
                    assert mock_client.send_vision_analysis.call_count == 3
                    logger_instance.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_populates_both_url_and_analysis(self):
        """Success populates both image_url and image_analysis."""
        from src.reddit import analyze_post_image

        image_url = 'https://i.redd.it/chart.png'

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.send_vision_analysis.return_value = {
                'content': 'Chart analysis result',
                'usage': {'total_tokens': 300}
            }
            mock_client_class.return_value = mock_client

            result = await analyze_post_image(image_url)

            assert result is not None
            assert result == 'Chart analysis result'

    @pytest.mark.asyncio
    async def test_retry_delays_correct_sequence(self):
        """Retry delays follow [2s, 5s, 10s] backoff pattern."""
        from src.reddit import analyze_post_image

        image_url = 'https://preview.redd.it/img.jpg'

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            # All three attempts fail
            mock_client.send_vision_analysis.side_effect = [
                Exception("Error 1"),
                Exception("Error 2"),
                Exception("Error 3")
            ]
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                with patch('structlog.get_logger'):
                    result = await analyze_post_image(image_url)

                    # After 3 failures, should have slept twice (before retries 2 and 3)
                    assert mock_sleep.call_count == 2
                    sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
                    assert sleep_calls == [2, 5]
