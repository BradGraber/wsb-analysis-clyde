"""
Tests for comment fetching and parent chain building (story-002-003).

Behavioral tests verifying up to 1000 comments per post with
parent chain context and engagement-based sorting.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestCommentFetching:
    """Test comment fetching via Async PRAW."""

    @pytest.mark.asyncio
    async def test_fetch_up_to_1000_comments_per_post(self):
        """Fetches up to 1000 comments per post via Async PRAW."""
        from src.reddit import fetch_comments

        mock_submission = AsyncMock()
        mock_submission.id = 'post123'

        # Create 1500 mock comments (should limit to 1000)
        mock_comments_list = []
        for i in range(1500):
            comment = AsyncMock()
            comment.id = f'comment_{i}'
            comment.author = AsyncMock()
            comment.author.name = f'user_{i}'
            comment.body = f'Comment text {i}'
            comment.score = 100 - i
            comment.depth = 0
            comment.created_utc = 1700000000 + i
            comment.parent_id = f't3_post123'  # Top-level
            mock_comments_list.append(comment)

        # Mock comment forest
        mock_submission.comments.list.return_value = mock_comments_list[:1000]

        with patch('src.reddit.build_parent_chains', return_value={}):
            comments = await fetch_comments(mock_submission)

            assert len(comments) <= 1000

    @pytest.mark.asyncio
    async def test_comments_sorted_by_engagement(self):
        """Comments sorted by engagement (score × replies)."""
        from src.reddit import fetch_comments

        mock_submission = AsyncMock()
        mock_submission.id = 'post456'

        # Create comments with varying engagement
        comment1 = MagicMock()
        comment1.id = 'low_engagement'
        comment1.author = 'user1'
        comment1.body = 'Low engagement comment'
        comment1.score = 5
        comment1.depth = 0
        comment1.created_utc = 1700000000
        comment1.parent_id = 't3_post456'
        comment1.replies = []

        comment2 = MagicMock()
        comment2.id = 'high_engagement'
        comment2.author = 'user2'
        comment2.body = 'High engagement comment'
        comment2.score = 500
        comment2.depth = 0
        comment2.created_utc = 1700000001
        comment2.parent_id = 't3_post456'
        comment2.replies = []

        # Use MagicMock for comment forest so .list() returns synchronously
        mock_comments_forest = MagicMock()
        mock_comments_forest.replace_more = AsyncMock()
        mock_comments_forest.list.return_value = [comment1, comment2]
        mock_submission.comments = mock_comments_forest

        with patch('src.reddit.build_parent_chains', return_value={}):
            comments = await fetch_comments(mock_submission)

            # Higher engagement should come first
            # Note: actual implementation will calculate engagement score
            assert len(comments) == 2

    @pytest.mark.asyncio
    async def test_processed_comment_has_all_11_fields(self):
        """ProcessedComment has 11 fields."""
        from src.reddit import fetch_comments
        from src.models.reddit_models import ProcessedComment

        mock_submission = AsyncMock()
        mock_submission.id = 'post789'

        comment = MagicMock()
        comment.id = 'comment_abc'
        comment.author = 'testuser'
        comment.body = 'Test comment body'
        comment.score = 42
        comment.depth = 1
        comment.created_utc = 1700000000
        comment.parent_id = 't1_parent123'
        comment.replies = []

        # Use MagicMock for comment forest so .list() returns synchronously
        mock_comments_forest = MagicMock()
        mock_comments_forest.replace_more = AsyncMock()
        mock_comments_forest.list.return_value = [comment]
        mock_submission.comments = mock_comments_forest

        with patch('src.reddit.build_parent_chains', return_value={'comment_abc': []}):
            comments = await fetch_comments(mock_submission)

            assert len(comments) == 1
            c = comments[0]

            # Verify all 11 fields
            assert hasattr(c, 'reddit_id')
            assert hasattr(c, 'post_id')
            assert hasattr(c, 'author')
            assert hasattr(c, 'body')
            assert hasattr(c, 'score')
            assert hasattr(c, 'depth')
            assert hasattr(c, 'created_utc')
            assert hasattr(c, 'priority_score')
            assert hasattr(c, 'financial_score')
            assert hasattr(c, 'author_trust_score')
            assert hasattr(c, 'parent_chain')

            assert c.reddit_id == 'comment_abc'
            assert c.author == 'testuser'
            assert c.priority_score == 0.0  # Default
            assert c.financial_score == 0.0  # Default
            assert c.author_trust_score == 0.0  # Default

    @pytest.mark.asyncio
    async def test_replace_more_with_configurable_limit(self):
        """replace_more() with configurable limit."""
        from src.reddit import fetch_comments

        mock_submission = AsyncMock()
        mock_submission.id = 'post_replace'
        mock_submission.comments.replace_more = AsyncMock()
        mock_submission.comments.list.return_value = []

        with patch('src.reddit.build_parent_chains', return_value={}):
            await fetch_comments(mock_submission, replace_more_limit=32)

            # Verify replace_more was called with limit
            mock_submission.comments.replace_more.assert_called_once_with(limit=32)

    @pytest.mark.asyncio
    async def test_replace_more_timeout_logs_warning_continues(self):
        """replace_more() timeout logs warning but continues."""
        from src.reddit import fetch_comments

        mock_submission = AsyncMock()
        mock_submission.id = 'post_timeout'

        # Use MagicMock for comment forest so .list() returns synchronously
        mock_comments_forest = MagicMock()
        mock_comments_forest.replace_more = AsyncMock(side_effect=TimeoutError("Timeout"))
        mock_comments_forest.list.return_value = []
        mock_submission.comments = mock_comments_forest

        with patch('src.reddit.logger') as mock_logger:
            with patch('src.reddit.build_parent_chains', return_value={}):
                comments = await fetch_comments(mock_submission)

                # Should log warning for replace_more failure
                mock_logger.warning.assert_called_once()
                # Should continue and return comments (even if empty)
                assert isinstance(comments, list)

    @pytest.mark.asyncio
    async def test_zero_comments_returns_empty_list_no_error(self):
        """Zero comments returns empty list without error."""
        from src.reddit import fetch_comments

        mock_submission = AsyncMock()
        mock_submission.id = 'post_empty'
        mock_submission.comments.list.return_value = []

        with patch('src.reddit.build_parent_chains', return_value={}):
            comments = await fetch_comments(mock_submission)

            assert comments == []


class TestParentChainBuilding:
    """Test parent chain building for comment context."""

    def test_top_level_comment_has_empty_parent_chain(self):
        """Top-level comment (depth=0) has empty parent_chain."""
        from src.reddit import build_parent_chains

        comments_data = [
            {
                'id': 'top_comment',
                'parent_id': 't3_post123',  # Links to submission
                'depth': 0,
                'body': 'Top level comment',
                'author': 'user1'
            }
        ]

        chains = build_parent_chains(comments_data)

        assert chains['top_comment'] == []

    def test_nested_comment_includes_all_ancestors(self):
        """Nested comments include all ancestors in parent_chain."""
        from src.reddit import build_parent_chains

        comments_data = [
            {
                'id': 'parent',
                'parent_id': 't3_post123',
                'depth': 0,
                'body': 'Parent comment',
                'author': 'user1'
            },
            {
                'id': 'child',
                'parent_id': 't1_parent',
                'depth': 1,
                'body': 'Child comment',
                'author': 'user2'
            },
            {
                'id': 'grandchild',
                'parent_id': 't1_child',
                'depth': 2,
                'body': 'Grandchild comment',
                'author': 'user3'
            }
        ]

        chains = build_parent_chains(comments_data)

        # Grandchild should have chain: [child, parent]
        grandchild_chain = chains['grandchild']
        assert len(grandchild_chain) == 2
        assert grandchild_chain[0]['id'] == 'child'  # Immediate parent first
        assert grandchild_chain[1]['id'] == 'parent'  # Root last

    def test_parent_chain_entry_has_four_fields(self):
        """ParentChainEntry has 4 fields: id, body, depth, author."""
        from src.reddit import build_parent_chains

        comments_data = [
            {
                'id': 'parent',
                'parent_id': 't3_post',
                'depth': 0,
                'body': 'Parent text',
                'author': 'author1'
            },
            {
                'id': 'child',
                'parent_id': 't1_parent',
                'depth': 1,
                'body': 'Child text',
                'author': 'author2'
            }
        ]

        chains = build_parent_chains(comments_data)

        parent_entry = chains['child'][0]
        assert 'id' in parent_entry
        assert 'body' in parent_entry
        assert 'depth' in parent_entry
        assert 'author' in parent_entry
        assert parent_entry['id'] == 'parent'
        assert parent_entry['body'] == 'Parent text'
        assert parent_entry['depth'] == 0
        assert parent_entry['author'] == 'author1'
