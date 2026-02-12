"""
Tests for Reddit authentication and hot posts fetching (story-002-001).

Behavioral tests verifying Async PRAW client authentication and
fetching of top 10 hot posts from r/wallstreetbets.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestAsyncPRAWAuthentication:
    """Test Async PRAW client authentication via OAuth2."""

    @pytest.mark.asyncio
    async def test_client_authenticates_with_valid_credentials(self):
        """PRAW client authenticates successfully with all required env vars."""
        from src.reddit import get_reddit_client

        with patch.dict('os.environ', {
            'REDDIT_CLIENT_ID': 'test_client_id',
            'REDDIT_CLIENT_SECRET': 'test_secret',
            'REDDIT_USER_AGENT': 'test_agent/1.0'
        }):
            with patch('asyncpraw.Reddit') as mock_reddit:
                mock_instance = AsyncMock()
                mock_reddit.return_value = mock_instance

                client = await get_reddit_client()

                assert client is not None
                mock_reddit.assert_called_once_with(
                    client_id='test_client_id',
                    client_secret='test_secret',
                    user_agent='test_agent/1.0'
                )

    @pytest.mark.asyncio
    @pytest.mark.parametrize('missing_var', [
        'REDDIT_CLIENT_ID',
        'REDDIT_CLIENT_SECRET',
        'REDDIT_USER_AGENT'
    ])
    async def test_client_raises_clear_error_on_missing_env_var(self, missing_var):
        """Missing/empty env var raises clear error identifying which variable."""
        from src.reddit import get_reddit_client

        env = {
            'REDDIT_CLIENT_ID': 'test_id',
            'REDDIT_CLIENT_SECRET': 'test_secret',
            'REDDIT_USER_AGENT': 'test_agent'
        }
        env[missing_var] = ''  # Empty string

        with patch.dict('os.environ', env, clear=True):
            with pytest.raises(ValueError, match=missing_var):
                await get_reddit_client()

    @pytest.mark.asyncio
    async def test_client_raises_error_when_env_var_not_set(self):
        """Completely missing env var raises ValueError."""
        from src.reddit import get_reddit_client

        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match='REDDIT_CLIENT_ID'):
                await get_reddit_client()


class TestHotPostsFetching:
    """Test fetching top 10 hot posts from r/wallstreetbets."""

    @pytest.mark.asyncio
    async def test_fetch_exactly_10_hot_posts(self):
        """Fetches exactly top 10 hot posts from r/wallstreetbets."""
        from src.reddit import fetch_hot_posts

        mock_reddit = AsyncMock()
        mock_subreddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        # Create 15 mock submissions (should only take first 10)
        mock_submissions = []
        for i in range(15):
            sub = MagicMock()
            sub.id = f'post_{i}'
            sub.title = f'Test Post {i}'
            sub.selftext = f'Body {i}'
            sub.score = 1000 - i
            sub.num_comments = 500 - i
            sub.url = f'https://reddit.com/r/test/{i}'
            mock_submissions.append(sub)

        # subreddit.hot() returns an async iterator directly (not a coroutine)
        async def async_iter(limit):
            for sub in mock_submissions[:limit]:
                yield sub

        mock_subreddit.hot = lambda limit=10: async_iter(limit)

        posts = await fetch_hot_posts(mock_reddit)

        assert len(posts) == 10

    @pytest.mark.asyncio
    async def test_processed_post_has_all_eight_fields(self):
        """Each post returns ProcessedPost with 8 fields."""
        from src.reddit import fetch_hot_posts
        from src.models.reddit_models import ProcessedPost

        mock_reddit = AsyncMock()
        mock_subreddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        mock_sub = MagicMock()
        mock_sub.id = 'abc123'
        mock_sub.title = 'Test Title'
        mock_sub.selftext = 'Test body text'
        mock_sub.score = 5000
        mock_sub.num_comments = 1200
        mock_sub.url = 'https://reddit.com/r/wallstreetbets/test'

        async def async_iter(limit=10):
            yield mock_sub

        mock_subreddit.hot = lambda limit=10: async_iter(limit)

        posts = await fetch_hot_posts(mock_reddit)

        assert len(posts) == 1
        post = posts[0]

        # Verify all 8 fields exist
        assert hasattr(post, 'reddit_id')
        assert hasattr(post, 'title')
        assert hasattr(post, 'selftext')
        assert hasattr(post, 'upvotes')
        assert hasattr(post, 'total_comments')
        assert hasattr(post, 'image_url')
        assert hasattr(post, 'image_analysis')
        assert hasattr(post, 'comments')

        assert post.reddit_id == 'abc123'
        assert post.title == 'Test Title'
        assert post.selftext == 'Test body text'
        assert post.upvotes == 5000
        assert post.total_comments == 1200
        assert post.image_url is None  # Default when no image
        assert post.image_analysis is None  # Default when no image
        assert post.comments == []  # Empty list initially

    @pytest.mark.asyncio
    async def test_reddit_outage_returns_503_error(self):
        """Reddit outage is caught, logged via structlog, raises HTTP 503."""
        from src.reddit import fetch_hot_posts, RedditAPIError

        mock_reddit = AsyncMock()
        mock_reddit.subreddit.side_effect = Exception("Connection failed")

        with pytest.raises(RedditAPIError) as exc_info:
            await fetch_hot_posts(mock_reddit)

        assert '503' in str(exc_info.value) or 'unavailable' in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_fewer_than_10_posts_returns_all_without_error(self):
        """Fewer than 10 posts available returns all without error."""
        from src.reddit import fetch_hot_posts

        mock_reddit = AsyncMock()
        mock_subreddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        # Only 5 posts available
        mock_submissions = []
        for i in range(5):
            sub = MagicMock()
            sub.id = f'post_{i}'
            sub.title = f'Test {i}'
            sub.selftext = f'Body {i}'
            sub.score = 100
            sub.num_comments = 50
            sub.url = f'https://reddit.com/test/{i}'
            mock_submissions.append(sub)

        async def async_iter(limit=10):
            for sub in mock_submissions:  # Only yield 5
                yield sub

        mock_subreddit.hot = lambda limit=10: async_iter(limit)

        posts = await fetch_hot_posts(mock_reddit)

        # Should return all 5 without error
        assert len(posts) == 5
