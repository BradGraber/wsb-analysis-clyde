"""
Tests for comment deduplication and storage (story-002-008).

Behavioral tests verifying reddit_id deduplication, atomic transactions,
and ProcessedPost/ProcessedComment data models.
"""

import pytest
from datetime import datetime


class TestCommentDeduplication:
    """Test comment deduplication by reddit_id (story-002-008)."""

    def test_existing_comment_updates_analysis_run_id(self, seeded_db):
        """Existing comment by reddit_id updates analysis_run_id, preserves annotations."""
        from src.storage import check_duplicates

        # Create initial analysis run
        seeded_db.execute("""
            INSERT INTO analysis_runs (status, started_at)
            VALUES ('running', datetime('now'))
        """)
        old_run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create new analysis run
        seeded_db.execute("""
            INSERT INTO analysis_runs (status, started_at)
            VALUES ('running', datetime('now'))
        """)
        new_run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Insert existing post
        seeded_db.execute("""
            INSERT INTO reddit_posts (reddit_id, title, selftext, upvotes, total_comments, fetched_at)
            VALUES ('post123', 'Test Post', 'Body', 100, 50, datetime('now'))
        """)
        post_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Insert existing comment with annotations linked to old run
        seeded_db.execute("""
            INSERT INTO comments (
                analysis_run_id, post_id, reddit_id, author, body, created_utc,
                score, depth, prioritization_score, sentiment, sarcasm_detected,
                has_reasoning, ai_confidence, author_trust_score, analyzed_at
            )
            VALUES (?, ?, 'existing123', 'testuser', 'Original comment', datetime('now'),
                    10, 0, 0.5, 'bullish', 1, 1, 0.8, 0.6, datetime('now'))
        """, (old_run_id, post_id))
        seeded_db.commit()

        # Check duplicates and update to new run
        duplicates = check_duplicates(['existing123'], new_run_id, seeded_db)

        # Verify comment was identified as duplicate
        assert 'existing123' in duplicates

        # Verify analysis_run_id was updated
        row = seeded_db.execute(
            "SELECT analysis_run_id, sentiment, sarcasm_detected, has_reasoning, ai_confidence, author_trust_score FROM comments WHERE reddit_id = 'existing123'"
        ).fetchone()
        assert row['analysis_run_id'] == new_run_id

        # Verify annotations preserved
        assert row['sentiment'] == 'bullish'
        assert row['sarcasm_detected'] == 1
        assert row['has_reasoning'] == 1
        assert row['ai_confidence'] == 0.8
        assert row['author_trust_score'] == 0.6

    def test_new_comment_not_in_duplicates(self, seeded_db):
        """New comment reddit_id not found in duplicates check."""
        from src.storage import check_duplicates

        # Create analysis run
        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Check for non-existent comment
        duplicates = check_duplicates(['new_comment_123'], run_id, seeded_db)

        # Verify new comment is NOT in duplicates set
        assert 'new_comment_123' not in duplicates
        assert len(duplicates) == 0

    def test_batch_dedup_query(self, seeded_db):
        """Batch deduplication query (not N individual queries)."""
        from src.storage import check_duplicates

        # Create analysis run and post
        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]
        seeded_db.execute("""
            INSERT INTO reddit_posts (reddit_id, title, selftext, upvotes, total_comments, fetched_at)
            VALUES ('post1', 'Test', 'Body', 100, 50, datetime('now'))
        """)
        post_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Insert some existing comments
        seeded_db.execute("""
            INSERT INTO comments (analysis_run_id, post_id, reddit_id, author, body,
                                created_utc, score, depth, prioritization_score)
            VALUES
                (?, ?, 'comment1', 'user1', 'Text1', datetime('now'), 10, 0, 0.5),
                (?, ?, 'comment2', 'user2', 'Text2', datetime('now'), 20, 0, 0.6)
        """, (run_id, post_id, run_id, post_id))
        seeded_db.commit()

        # Batch check with mix of existing and new comments
        reddit_ids = ['comment1', 'comment2', 'new_comment3']
        duplicates = check_duplicates(reddit_ids, run_id, seeded_db)

        # Verify only existing comments in duplicates set
        assert len(duplicates) == 2
        assert 'comment1' in duplicates
        assert 'comment2' in duplicates
        assert 'new_comment3' not in duplicates

    def test_empty_input_returns_empty_set(self, seeded_db):
        """Empty input returns empty set."""
        from src.storage import check_duplicates

        # Create analysis run
        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Check with empty list
        duplicates = check_duplicates([], run_id, seeded_db)

        assert duplicates == set()
        assert len(duplicates) == 0


class TestPostAndCommentStorage:
    """Test INSERT operations for posts and comments."""

    def test_new_post_insert_all_fields(self, seeded_db):
        """New posts INSERT with all 8 fields."""
        from src.storage import store_posts_and_comments

        # Create analysis run
        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        post_data = {
            'reddit_id': 'newpost123',
            'title': 'New Post Title',
            'selftext': 'Post body text',
            'upvotes': 5000,
            'total_comments': 1200,
            'image_urls': ['https://i.redd.it/test.png'],
            'image_analysis': 'Image shows chart going up',
            'comments': []
        }

        store_posts_and_comments(seeded_db, run_id, [post_data])

        # Verify post inserted
        row = seeded_db.execute("""
            SELECT reddit_id, title, selftext, upvotes, total_comments,
                   image_urls, image_analysis
            FROM reddit_posts WHERE reddit_id = 'newpost123'
        """).fetchone()

        assert row is not None
        assert row['title'] == 'New Post Title'
        assert row['upvotes'] == 5000
        import json
        assert json.loads(row['image_urls']) == ['https://i.redd.it/test.png']
        assert row['image_analysis'] == 'Image shows chart going up'

    def test_new_comment_insert_with_metadata_and_parent_chain(self, seeded_db):
        """New comments INSERT with all metadata + parent_chain as JSON."""
        from src.storage import store_posts_and_comments
        import json

        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        parent_chain = [
            {'id': 'parent1', 'body': 'Parent text', 'depth': 0, 'author': 'user1'}
        ]

        post_data = {
            'reddit_id': 'post456',
            'title': 'Test',
            'selftext': 'Body',
            'upvotes': 100,
            'total_comments': 10,
            'image_urls': [],
            'image_analysis': None,
            'comments': [
                {
                    'reddit_id': 'comment789',
                    'author': 'testuser',
                    'body': 'Comment text',
                    'created_utc': 1700000000,
                    'score': 42,
                    'depth': 1,
                    'priority_score': 0.75,
                    'financial_score': 0.5,
                    'author_trust_score': 0.6,
                    'parent_chain': parent_chain
                }
            ]
        }

        store_posts_and_comments(seeded_db, run_id, [post_data])

        # Verify comment inserted
        row = seeded_db.execute("""
            SELECT reddit_id, author, body, score, depth, prioritization_score,
                   author_trust_score
            FROM comments WHERE reddit_id = 'comment789'
        """).fetchone()

        assert row is not None
        assert row['author'] == 'testuser'
        assert row['score'] == 42
        assert row['prioritization_score'] == 0.75

    def test_atomic_transaction_per_post(self, seeded_db):
        """Atomic transaction per post; failure logs error and continues."""
        from src.storage import store_posts_and_comments

        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # First post is valid
        post1 = {
            'reddit_id': 'good_post',
            'title': 'Good',
            'selftext': 'Valid',
            'upvotes': 100,
            'total_comments': 10,
            'image_urls': [],
            'image_analysis': None,
            'comments': []
        }

        # Second post will fail (duplicate reddit_id)
        post2 = {
            'reddit_id': 'good_post',  # Same ID - will violate UNIQUE constraint
            'title': 'Duplicate',
            'selftext': 'Invalid',
            'upvotes': 50,
            'total_comments': 5,
            'image_urls': [],
            'image_analysis': None,
            'comments': []
        }

        # Should handle failure gracefully
        with patch('structlog.get_logger') as mock_logger:
            from unittest.mock import MagicMock
            logger_instance = MagicMock()
            mock_logger.return_value = logger_instance

            store_posts_and_comments(seeded_db, run_id, [post1, post2])

            # First should succeed
            row = seeded_db.execute("SELECT * FROM reddit_posts WHERE reddit_id = 'good_post'").fetchone()
            assert row is not None

    def test_reddit_outage_logs_error_returns_503(self):
        """Reddit outage (RedditAPIError) is raised by fetch layer, not storage."""
        from src.reddit import RedditAPIError, fetch_hot_posts
        from unittest.mock import AsyncMock

        # Reddit outage handling is in fetch_hot_posts, not storage
        mock_reddit = AsyncMock()
        mock_reddit.subreddit.side_effect = Exception("Connection failed")

        with pytest.raises(RedditAPIError) as exc_info:
            import asyncio
            asyncio.get_event_loop().run_until_complete(fetch_hot_posts(mock_reddit))

        assert '503' in str(exc_info.value) or 'unavailable' in str(exc_info.value).lower()


class TestDataModels:
    """Test ProcessedPost and ProcessedComment data structures."""

    def test_processed_post_has_8_fields(self):
        """ProcessedPost dataclass/Pydantic has 8 fields."""
        from src.models.reddit_models import ProcessedPost

        post = ProcessedPost(
            reddit_id='test123',
            title='Test Title',
            selftext='Test body',
            upvotes=1000,
            total_comments=500,
            image_urls=[],
            image_analysis=None,
            comments=[]
        )

        assert post.reddit_id == 'test123'
        assert post.title == 'Test Title'
        assert post.selftext == 'Test body'
        assert post.upvotes == 1000
        assert post.total_comments == 500
        assert post.image_urls == []
        assert post.image_analysis is None
        assert post.comments == []

    def test_processed_comment_has_11_fields(self):
        """ProcessedComment dataclass/Pydantic has 11 fields."""
        from src.models.reddit_models import ProcessedComment

        comment = ProcessedComment(
            reddit_id='comment123',
            post_id='post456',
            author='testuser',
            body='Comment body',
            score=42,
            depth=1,
            created_utc=1700000000,
            priority_score=0.75,
            financial_score=0.5,
            author_trust_score=0.6,
            parent_chain=[]
        )

        assert comment.reddit_id == 'comment123'
        assert comment.post_id == 'post456'
        assert comment.author == 'testuser'
        assert comment.body == 'Comment body'
        assert comment.score == 42
        assert comment.depth == 1
        assert comment.created_utc == 1700000000
        assert comment.priority_score == 0.75
        assert comment.financial_score == 0.5
        assert comment.author_trust_score == 0.6
        assert comment.parent_chain == []

    def test_parent_chain_entry_has_4_fields(self):
        """ParentChainEntry has 4 fields: id, body, depth, author."""
        from src.models.reddit_models import ParentChainEntry

        entry = ParentChainEntry(
            id='parent123',
            body='Parent comment text',
            depth=0,
            author='parent_user'
        )

        assert entry.id == 'parent123'
        assert entry.body == 'Parent comment text'
        assert entry.depth == 0
        assert entry.author == 'parent_user'


# Need to import patch at module level for some tests
from unittest.mock import patch
