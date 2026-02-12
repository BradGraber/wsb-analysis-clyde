"""
Tests for comment_tickers junction table (story-003-009).

Behavioral tests verifying ticker-sentiment pairs are inserted
into comment_tickers junction table within batch transactions.
"""

import pytest


class TestCommentTickersJunction:
    """Test comment_tickers junction table inserts (story-003-009)."""

    def test_insert_ticker_sentiment_pairs(self, seeded_db):
        """For each ticker-sentiment pair, INSERT OR IGNORE into comment_tickers."""
        from src.ai_batch import store_comment_tickers

        # Create analysis run
        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create post
        seeded_db.execute("""
            INSERT INTO reddit_posts (reddit_id, title, selftext, upvotes, total_comments, fetched_at)
            VALUES ('post1', 'Test', 'Body', 100, 50, datetime('now'))
        """)
        post_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create comment
        seeded_db.execute("""
            INSERT INTO comments (
                analysis_run_id, post_id, reddit_id, author, body, created_utc,
                score, depth, prioritization_score
            )
            VALUES (?, ?, 'comment1', 'user1', 'I like AAPL and MSFT', datetime('now'),
                    10, 0, 0.5)
        """, (run_id, post_id))
        comment_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]
        seeded_db.commit()

        # Store ticker-sentiment pairs
        tickers = ['AAPL', 'MSFT']
        sentiments = ['bullish', 'neutral']

        store_comment_tickers(seeded_db, comment_id, tickers, sentiments)

        # Verify inserts
        rows = seeded_db.execute("""
            SELECT ticker, sentiment FROM comment_tickers
            WHERE comment_id = ?
            ORDER BY ticker
        """, (comment_id,)).fetchall()

        assert len(rows) == 2
        assert rows[0]['ticker'] == 'AAPL'
        assert rows[0]['sentiment'] == 'bullish'
        assert rows[1]['ticker'] == 'MSFT'
        assert rows[1]['sentiment'] == 'neutral'

    def test_uses_comment_id_not_reddit_id(self, seeded_db):
        """Uses comment_id FK (not reddit_id)."""
        from src.ai_batch import store_comment_tickers

        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        seeded_db.execute("""
            INSERT INTO reddit_posts (reddit_id, title, selftext, upvotes, total_comments, fetched_at)
            VALUES ('post1', 'Test', 'Body', 100, 50, datetime('now'))
        """)
        post_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        seeded_db.execute("""
            INSERT INTO comments (
                analysis_run_id, post_id, reddit_id, author, body, created_utc,
                score, depth, prioritization_score
            )
            VALUES (?, ?, 'reddit_abc123', 'user1', 'Text', datetime('now'),
                    10, 0, 0.5)
        """, (run_id, post_id))
        comment_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]
        seeded_db.commit()

        # Store using comment_id (integer PK), not reddit_id (string)
        store_comment_tickers(seeded_db, comment_id, ['TSLA'], ['bearish'])

        # Verify FK is comment.id
        row = seeded_db.execute("""
            SELECT comment_id FROM comment_tickers WHERE ticker = 'TSLA'
        """).fetchone()

        assert row['comment_id'] == comment_id

    def test_ticker_uppercase_stored(self, seeded_db):
        """Ticker stored as uppercase."""
        from src.ai_batch import store_comment_tickers

        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        seeded_db.execute("""
            INSERT INTO reddit_posts (reddit_id, title, selftext, upvotes, total_comments, fetched_at)
            VALUES ('post1', 'Test', 'Body', 100, 50, datetime('now'))
        """)
        post_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        seeded_db.execute("""
            INSERT INTO comments (
                analysis_run_id, post_id, reddit_id, author, body, created_utc,
                score, depth, prioritization_score
            )
            VALUES (?, ?, 'comment1', 'user1', 'Text', datetime('now'),
                    10, 0, 0.5)
        """, (run_id, post_id))
        comment_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]
        seeded_db.commit()

        # Pass lowercase ticker
        store_comment_tickers(seeded_db, comment_id, ['aapl'], ['bullish'])

        # Should be stored as uppercase
        row = seeded_db.execute("""
            SELECT ticker FROM comment_tickers WHERE comment_id = ?
        """, (comment_id,)).fetchone()

        assert row['ticker'] == 'AAPL'

    def test_empty_tickers_zero_inserts(self, seeded_db):
        """Empty tickers array results in zero inserts."""
        from src.ai_batch import store_comment_tickers

        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        seeded_db.execute("""
            INSERT INTO reddit_posts (reddit_id, title, selftext, upvotes, total_comments, fetched_at)
            VALUES ('post1', 'Test', 'Body', 100, 50, datetime('now'))
        """)
        post_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        seeded_db.execute("""
            INSERT INTO comments (
                analysis_run_id, post_id, reddit_id, author, body, created_utc,
                score, depth, prioritization_score
            )
            VALUES (?, ?, 'comment1', 'user1', 'Text', datetime('now'),
                    10, 0, 0.5)
        """, (run_id, post_id))
        comment_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]
        seeded_db.commit()

        # Empty tickers
        store_comment_tickers(seeded_db, comment_id, [], [])

        # Should have zero inserts
        count = seeded_db.execute("""
            SELECT COUNT(*) FROM comment_tickers WHERE comment_id = ?
        """, (comment_id,)).fetchone()[0]

        assert count == 0

    def test_within_same_transaction_as_comment(self, seeded_db):
        """comment_tickers inserts within same transaction as parent comment."""
        from src.ai_batch import commit_analysis_batch

        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        seeded_db.execute("""
            INSERT INTO reddit_posts (reddit_id, title, selftext, upvotes, total_comments, fetched_at)
            VALUES ('post1', 'Test', 'Body', 100, 50, datetime('now'))
        """)
        post_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]
        seeded_db.commit()

        # Batch with comment + tickers
        analysis_results = [
            {
                'reddit_id': 'comment_with_tickers',
                'post_id': post_id,
                'author': 'user1',
                'body': 'I like AAPL and TSLA',
                'sentiment': 'bullish',
                'ai_confidence': 0.8,
                'tickers': ['AAPL', 'TSLA'],
                'ticker_sentiments': ['bullish', 'bullish']
            }
        ]

        # Should commit comment and tickers together
        commit_analysis_batch(seeded_db, run_id, analysis_results)

        # Verify both exist
        comment_row = seeded_db.execute("""
            SELECT id FROM comments WHERE reddit_id = 'comment_with_tickers'
        """).fetchone()
        assert comment_row is not None

        ticker_count = seeded_db.execute("""
            SELECT COUNT(*) FROM comment_tickers WHERE comment_id = ?
        """, (comment_row['id'],)).fetchone()[0]
        assert ticker_count == 2

    def test_duplicate_ticker_per_comment_ignored(self, seeded_db):
        """INSERT OR IGNORE prevents duplicate (comment_id, ticker) pairs."""
        from src.ai_batch import store_comment_tickers

        seeded_db.execute("INSERT INTO analysis_runs (status, started_at) VALUES ('running', datetime('now'))")
        run_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        seeded_db.execute("""
            INSERT INTO reddit_posts (reddit_id, title, selftext, upvotes, total_comments, fetched_at)
            VALUES ('post1', 'Test', 'Body', 100, 50, datetime('now'))
        """)
        post_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        seeded_db.execute("""
            INSERT INTO comments (
                analysis_run_id, post_id, reddit_id, author, body, created_utc,
                score, depth, prioritization_score
            )
            VALUES (?, ?, 'comment1', 'user1', 'Text', datetime('now'),
                    10, 0, 0.5)
        """, (run_id, post_id))
        comment_id = seeded_db.execute("SELECT last_insert_rowid()").fetchone()[0]
        seeded_db.commit()

        # Insert once
        store_comment_tickers(seeded_db, comment_id, ['AAPL'], ['bullish'])

        # Insert again (duplicate)
        store_comment_tickers(seeded_db, comment_id, ['AAPL'], ['bearish'])  # Different sentiment

        # Should still have only one row (OR IGNORE)
        count = seeded_db.execute("""
            SELECT COUNT(*) FROM comment_tickers
            WHERE comment_id = ? AND ticker = 'AAPL'
        """, (comment_id,)).fetchone()[0]

        assert count == 1
