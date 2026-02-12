"""
Tests for image detection and GPT-4o-mini vision analysis (story-002-002).

Behavioral tests verifying 4-level image URL detection cascade,
multi-image support, and vision API retry logic with exponential backoff.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestImageURLDetection:
    """Test 4-level image URL detection cascade."""

    def _make_submission(self, **kwargs):
        """Create a mock submission with specified attributes."""
        sub = MagicMock()
        # Set defaults that won't match
        sub.url = kwargs.get('url', 'https://reddit.com/r/test')
        # Only set attributes that are explicitly provided
        if 'url_overridden_by_dest' in kwargs:
            sub.url_overridden_by_dest = kwargs['url_overridden_by_dest']
        else:
            del sub.url_overridden_by_dest
        if 'media_metadata' in kwargs:
            sub.media_metadata = kwargs['media_metadata']
        else:
            del sub.media_metadata
        if 'preview' in kwargs:
            sub.preview = kwargs['preview']
        else:
            del sub.preview
        return sub

    # Level 1: Direct URL
    def test_direct_url_i_redd_it(self):
        """Level 1: Direct i.redd.it URL returns single-element list."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(url='https://i.redd.it/abc123.png')
        assert detect_image_urls(sub) == ['https://i.redd.it/abc123.png']

    def test_direct_url_i_imgur(self):
        """Level 1: Direct i.imgur.com URL returns single-element list."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(url='https://i.imgur.com/xyz789.jpg')
        assert detect_image_urls(sub) == ['https://i.imgur.com/xyz789.jpg']

    def test_direct_url_image_extension(self):
        """Level 1: URL ending with image extension is detected."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(url='https://example.com/chart.png')
        assert detect_image_urls(sub) == ['https://example.com/chart.png']

    def test_direct_url_excludes_imgur_album(self):
        """Level 1: Imgur album URLs (/a/) are excluded."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(url='https://imgur.com/a/abc123')
        assert detect_image_urls(sub) == []

    def test_direct_url_excludes_imgur_gallery(self):
        """Level 1: Imgur gallery URLs (/gallery/) are excluded."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(url='https://imgur.com/gallery/abc123')
        assert detect_image_urls(sub) == []

    # Level 2: url_overridden_by_dest
    def test_overridden_url_detected(self):
        """Level 2: url_overridden_by_dest with image domain is detected."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(
            url='https://reddit.com/r/test',
            url_overridden_by_dest='https://i.redd.it/overridden.jpg'
        )
        assert detect_image_urls(sub) == ['https://i.redd.it/overridden.jpg']

    def test_overridden_url_with_extension(self):
        """Level 2: url_overridden_by_dest with image extension is detected."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(
            url='https://reddit.com/r/test',
            url_overridden_by_dest='https://example.com/photo.webp'
        )
        assert detect_image_urls(sub) == ['https://example.com/photo.webp']

    # Level 3: media_metadata (galleries)
    def test_gallery_returns_all_images(self):
        """Level 3: Gallery posts return ALL image URLs from media_metadata."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(
            url='https://reddit.com/gallery/abc',
            media_metadata={
                'img1': {'s': {'u': 'https://preview.redd.it/img1.jpg?width=1080'}},
                'img2': {'s': {'u': 'https://preview.redd.it/img2.jpg?width=1080'}},
                'img3': {'s': {'u': 'https://preview.redd.it/img3.jpg?width=1080'}},
            }
        )
        result = detect_image_urls(sub)
        assert len(result) == 3
        # URLs should be transformed: query params stripped, preview→i.redd.it
        assert all('i.redd.it' in url for url in result)
        assert all('?' not in url for url in result)

    def test_gallery_html_unescape(self):
        """Level 3: HTML entities in gallery URLs are unescaped."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(
            url='https://reddit.com/gallery/abc',
            media_metadata={
                'img1': {'s': {'u': 'https://preview.redd.it/img1.jpg?width=1080&amp;format=png'}},
            }
        )
        result = detect_image_urls(sub)
        assert len(result) == 1
        assert '&amp;' not in result[0]

    # Level 4: preview
    def test_preview_transforms_to_i_redd_it(self):
        """Level 4: preview.redd.it URLs are transformed to i.redd.it."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(
            url='https://reddit.com/r/test',
            preview={
                'images': [{
                    'source': {
                        'url': 'https://preview.redd.it/img.jpg?width=1080&amp;auto=webp'
                    }
                }]
            }
        )
        result = detect_image_urls(sub)
        assert len(result) == 1
        assert 'i.redd.it' in result[0]
        assert '?' not in result[0]

    def test_preview_excludes_external_preview(self):
        """Level 4: external-preview.redd.it URLs are excluded."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(
            url='https://reddit.com/r/test',
            preview={
                'images': [{
                    'source': {
                        'url': 'https://external-preview.redd.it/proxied.jpg?auto=webp'
                    }
                }]
            }
        )
        assert detect_image_urls(sub) == []

    # No image
    def test_no_image_returns_empty_list(self):
        """Non-image URL returns empty list."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(url='https://youtube.com/watch?v=xyz')
        assert detect_image_urls(sub) == []

    def test_reddit_self_post_returns_empty_list(self):
        """Reddit self-post URL returns empty list."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(url='https://reddit.com/r/wallstreetbets/comments/abc')
        assert detect_image_urls(sub) == []

    # Priority cascade
    def test_level1_takes_priority_over_level3(self):
        """Level 1 (direct URL) takes priority even if media_metadata exists."""
        from src.reddit import detect_image_urls
        sub = self._make_submission(
            url='https://i.redd.it/direct.png',
            media_metadata={
                'img1': {'s': {'u': 'https://preview.redd.it/gallery.jpg'}},
            }
        )
        result = detect_image_urls(sub)
        assert result == ['https://i.redd.it/direct.png']


class TestVisionAnalysis:
    """Test GPT-4o-mini vision API integration."""

    @pytest.mark.asyncio
    async def test_vision_api_called_for_single_image(self):
        """GPT-4o-mini vision API called for a single image URL."""
        from src.reddit import analyze_post_images

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.send_vision_analysis.return_value = {
                'content': 'A chart showing stock prices going up',
                'usage': {'total_tokens': 500}
            }
            mock_client_class.return_value = mock_client

            result = await analyze_post_images(['https://i.redd.it/test.png'])

            assert result == 'A chart showing stock prices going up'
            mock_client.send_vision_analysis.assert_called_once_with('https://i.redd.it/test.png')

    @pytest.mark.asyncio
    async def test_multi_image_concatenation(self):
        """Multiple images have descriptions concatenated with double newline."""
        from src.reddit import analyze_post_images

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.send_vision_analysis.side_effect = [
                {'content': 'Chart 1 description', 'usage': {'total_tokens': 200}},
                {'content': 'Chart 2 description', 'usage': {'total_tokens': 200}},
            ]
            mock_client_class.return_value = mock_client

            result = await analyze_post_images([
                'https://i.redd.it/chart1.png',
                'https://i.redd.it/chart2.png',
            ])

            assert result == 'Chart 1 description\n\nChart 2 description'
            assert mock_client.send_vision_analysis.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_urls_returns_none(self):
        """Empty URL list returns None without calling API."""
        from src.reddit import analyze_post_images

        result = await analyze_post_images([])
        assert result is None

    @pytest.mark.asyncio
    async def test_all_failures_returns_none(self):
        """When all image analyses fail, returns None."""
        from src.reddit import analyze_post_images

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.send_vision_analysis.side_effect = Exception("API Error")
            mock_client_class.return_value = mock_client

            with patch('structlog.get_logger') as mock_logger:
                mock_logger.return_value = MagicMock()
                with patch('asyncio.sleep', new_callable=AsyncMock):
                    result = await analyze_post_images(['https://i.redd.it/fail.png'])

                    assert result is None

    @pytest.mark.asyncio
    async def test_vision_api_retry_with_exponential_backoff(self):
        """Retry 3x with [2s, 5s, 10s] backoff on failure."""
        from src.reddit import _analyze_single_image

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
                result = await _analyze_single_image('https://i.redd.it/test.png')

                assert result == 'Success'
                assert mock_client.send_vision_analysis.call_count == 3

                # Verify backoff delays: [2s, 5s]
                sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
                assert sleep_calls == [2, 5]

    @pytest.mark.asyncio
    async def test_vision_api_failure_after_3_retries_logs_warning(self):
        """After 3 failures, log warning, image_analysis=NULL, continue."""
        from src.reddit import _analyze_single_image

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.send_vision_analysis.side_effect = Exception("API Error")
            mock_client_class.return_value = mock_client

            with patch('structlog.get_logger') as mock_logger:
                logger_instance = MagicMock()
                mock_logger.return_value = logger_instance

                with patch('asyncio.sleep', new_callable=AsyncMock):
                    result = await _analyze_single_image('https://i.redd.it/test.png')

                    assert result is None  # NULL after all retries fail
                    assert mock_client.send_vision_analysis.call_count == 3
                    logger_instance.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_delays_correct_sequence(self):
        """Retry delays follow [2s, 5s, 10s] backoff pattern."""
        from src.reddit import _analyze_single_image

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
                    result = await _analyze_single_image('https://preview.redd.it/img.jpg')

                    # After 3 failures, should have slept twice (before retries 2 and 3)
                    assert mock_sleep.call_count == 2
                    sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
                    assert sleep_calls == [2, 5]

    @pytest.mark.asyncio
    async def test_partial_multi_image_failure(self):
        """When some images fail but others succeed, returns successful descriptions."""
        from src.reddit import analyze_post_images

        with patch('src.ai_client.OpenAIClient') as mock_client_class:
            mock_client = AsyncMock()
            # First image succeeds, second fails all retries
            call_count = 0

            async def side_effect(url):
                nonlocal call_count
                call_count += 1
                if 'chart1' in url:
                    return {'content': 'Chart 1 analysis', 'usage': {'total_tokens': 200}}
                raise Exception("API Error")

            mock_client.send_vision_analysis.side_effect = side_effect
            mock_client_class.return_value = mock_client

            with patch('structlog.get_logger') as mock_logger:
                mock_logger.return_value = MagicMock()
                with patch('asyncio.sleep', new_callable=AsyncMock):
                    result = await analyze_post_images([
                        'https://i.redd.it/chart1.png',
                        'https://i.redd.it/chart2.png',
                    ])

                    # Only the successful description should be returned
                    assert result == 'Chart 1 analysis'
