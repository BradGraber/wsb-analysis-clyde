"""Storage operations for Reddit posts, comments, and AI analysis results.

This module handles all database INSERT/UPDATE operations for the WSB Analysis Tool,
including deduplication logic and atomic transactions.

Key Functions:
    check_duplicates — Batch query comments by reddit_id for deduplication
    store_posts_and_comments — Atomic transaction per post (Phase 2 storage)
    store_analysis_results — Persist AI analysis results with author_trust_score snapshot (Phase 3 storage)
"""

import json
import sqlite3
import structlog
from typing import Any, Dict, List, Optional

from src.models.reddit_models import ProcessedComment

logger = structlog.get_logger()


def check_duplicates(comment_ids: List[str], run_id: int, db_connection: Optional[sqlite3.Connection] = None) -> set:
    """Check for duplicate comments and update their analysis_run_id.

    This function performs a batch query to detect which comment reddit_ids already
    exist in the database. For duplicates found, it updates their analysis_run_id to
    the current run while preserving all existing annotations (sentiment, sarcasm_detected,
    has_reasoning, ai_confidence, reasoning_summary, author_trust_score).

    The function handles large batches efficiently by respecting SQLite's ~999 parameter
    limit for IN clauses by processing in batches of 900.

    Args:
        comment_ids: List of Reddit comment IDs to check for duplicates
        run_id: Current analysis run ID to associate with duplicate comments
        db_connection: SQLite database connection (required)

    Returns:
        Set of reddit_ids that already exist in the database

    Example:
        >>> duplicates = check_duplicates(['abc123', 'def456', 'new789'], run_id=5, db_connection=conn)
        >>> 'abc123' in duplicates  # True if abc123 already exists
        >>> 'new789' in duplicates  # False if new789 is new
    """
    if not comment_ids:
        return set()

    if db_connection is None:
        raise ValueError("db_connection parameter is required")

    conn = db_connection

    duplicate_ids = set()

    # SQLite has a limit of ~999 parameters in a single query
    # Batch the queries if we have more than 900 IDs to be safe
    batch_size = 900

    for i in range(0, len(comment_ids), batch_size):
        batch = comment_ids[i:i + batch_size]

        # Build placeholders for IN clause
        placeholders = ','.join('?' * len(batch))

        # Query for existing comments
        query = f"""
            SELECT reddit_id
            FROM comments
            WHERE reddit_id IN ({placeholders})
        """

        cursor = conn.execute(query, batch)
        rows = cursor.fetchall()

        # Collect duplicate IDs from this batch
        batch_duplicates = {row['reddit_id'] for row in rows}
        duplicate_ids.update(batch_duplicates)

        # Update analysis_run_id for duplicates in this batch
        if batch_duplicates:
            update_placeholders = ','.join('?' * len(batch_duplicates))
            update_query = f"""
                UPDATE comments
                SET analysis_run_id = ?
                WHERE reddit_id IN ({update_placeholders})
            """

            params = [run_id] + list(batch_duplicates)
            conn.execute(update_query, params)

            logger.debug(
                "updated_duplicate_analysis_run_ids",
                run_id=run_id,
                duplicate_count=len(batch_duplicates)
            )

    return duplicate_ids


def store_posts_and_comments(conn: sqlite3.Connection, run_id: int, posts: List[Dict[str, Any]]) -> None:
    """Store Reddit posts and comments with atomic transactions per post.

    This function handles Phase 2 storage — ingesting posts and comments from Reddit API
    into the database. Each post is stored in its own transaction. If a post fails,
    it logs an error and continues with the next post.

    Post data should include all 8 ProcessedPost fields.
    Comment data should include all 11 ProcessedComment fields.

    Args:
        conn: SQLite database connection
        run_id: Foreign key to analysis_runs.id
        posts: List of post dicts with 'comments' key containing comment dicts

    Raises:
        Exception: Database operational errors are logged but not raised (graceful degradation)

    Example:
        >>> post_data = {
        ...     'reddit_id': 'abc123',
        ...     'title': 'Test Post',
        ...     'selftext': 'Body text',
        ...     'upvotes': 1000,
        ...     'total_comments': 500,
        ...     'image_url': None,
        ...     'image_analysis': None,
        ...     'comments': [
        ...         {
        ...             'reddit_id': 'comment1',
        ...             'author': 'user1',
        ...             'body': 'Comment text',
        ...             'score': 42,
        ...             'depth': 0,
        ...             'created_utc': 1700000000,
        ...             'priority_score': 0.75,
        ...             'financial_score': 0.5,
        ...             'author_trust_score': 0.6,
        ...             'parent_chain': []
        ...         }
        ...     ]
        ... }
        >>> store_posts_and_comments(conn, run_id=1, posts=[post_data])
    """
    for post in posts:
        try:
            # Insert or get existing post
            post_cursor = conn.execute("""
                INSERT INTO reddit_posts (reddit_id, title, selftext, upvotes, total_comments,
                                         image_url, image_analysis, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(reddit_id) DO UPDATE SET
                    upvotes = excluded.upvotes,
                    total_comments = excluded.total_comments,
                    fetched_at = excluded.fetched_at
                RETURNING id
            """, (
                post['reddit_id'],
                post['title'],
                post['selftext'],
                post['upvotes'],
                post['total_comments'],
                post.get('image_url'),
                post.get('image_analysis')
            ))

            post_db_id = post_cursor.fetchone()[0]

            # Insert comments for this post
            for comment in post.get('comments', []):
                # Serialize parent_chain to JSON
                parent_chain_json = None
                if 'parent_chain' in comment and comment['parent_chain']:
                    parent_chain_json = json.dumps([
                        {
                            'id': entry['id'],
                            'body': entry['body'],
                            'depth': entry['depth'],
                            'author': entry['author']
                        }
                        for entry in comment['parent_chain']
                    ])

                conn.execute("""
                    INSERT INTO comments (
                        analysis_run_id, post_id, reddit_id, author, body, created_utc,
                        score, depth, prioritization_score, author_trust_score, parent_chain
                    )
                    VALUES (?, ?, ?, ?, ?, datetime(?, 'unixepoch'), ?, ?, ?, ?, ?)
                    ON CONFLICT(reddit_id) DO UPDATE SET
                        analysis_run_id = excluded.analysis_run_id,
                        score = excluded.score
                """, (
                    run_id,
                    post_db_id,
                    comment['reddit_id'],
                    comment['author'],
                    comment['body'],
                    comment['created_utc'],
                    comment['score'],
                    comment['depth'],
                    comment.get('priority_score', 0.0),
                    comment.get('author_trust_score', 0.5),
                    parent_chain_json
                ))

            conn.commit()
            logger.info("stored_post_and_comments", reddit_id=post['reddit_id'],
                       comment_count=len(post.get('comments', [])))

        except Exception as e:
            conn.rollback()
            logger.error("failed_to_store_post", reddit_id=post.get('reddit_id', 'unknown'),
                        error=str(e))
            # Continue with next post


def store_analysis_results(
    conn: sqlite3.Connection,
    comment: ProcessedComment,
    run_id: int,
    ai_result: Dict[str, Any]
) -> None:
    """Persist AI analysis results for a single comment.

    This function handles Phase 3 storage — updating a comment record with AI annotations
    after analysis. It preserves the author_trust_score that was set during Phase 2
    (story-002-005) and persists it to the database.

    Key behaviors:
    - INSERT if comment doesn't exist (new comment discovered during analysis)
    - UPDATE if comment exists (add AI annotations)
    - NEVER overwrites author_trust_score on UPDATE (dedup path)
    - Includes author_trust_score in INSERT (new comment path)
    - Does NOT query the authors table (Phase 2 already did the lookup)

    This function is called by commit_analysis_batch() in src/ai_batch.py as part of
    the batch-of-5 transaction commit (story-003-008).

    Args:
        conn: SQLite database connection (within an active transaction)
        comment: ProcessedComment with author_trust_score already set by Phase 2
        run_id: Foreign key to analysis_runs.id
        ai_result: Dict with AI analysis fields:
            - sentiment: str (bullish/bearish/neutral)
            - sarcasm_detected: bool
            - has_reasoning: bool
            - reasoning_summary: str
            - confidence: float (0.0-1.0)

    Example:
        >>> comment = ProcessedComment(
        ...     reddit_id='abc123',
        ...     post_id='post456',
        ...     author='user1',
        ...     body='AAPL calls look good',
        ...     score=42,
        ...     depth=0,
        ...     created_utc=1700000000,
        ...     priority_score=0.75,
        ...     financial_score=0.5,
        ...     author_trust_score=0.8  # Set by Phase 2 lookup
        ... )
        >>> ai_result = {
        ...     'sentiment': 'bullish',
        ...     'sarcasm_detected': False,
        ...     'has_reasoning': True,
        ...     'reasoning_summary': 'Strong technicals',
        ...     'confidence': 0.85
        ... }
        >>> store_analysis_results(conn, comment, run_id=1, ai_result=ai_result)
    """
    # Get post_db_id from reddit_posts using post_id (which is the reddit_id)
    cursor = conn.execute(
        "SELECT id FROM reddit_posts WHERE reddit_id = ?",
        (comment.post_id,)
    )
    row = cursor.fetchone()

    if not row:
        logger.error(
            "post_not_found_for_comment",
            comment_reddit_id=comment.reddit_id,
            post_reddit_id=comment.post_id
        )
        return

    post_db_id = row[0]

    # Check if comment exists
    existing_cursor = conn.execute(
        "SELECT id, author_trust_score FROM comments WHERE reddit_id = ?",
        (comment.reddit_id,)
    )
    existing = existing_cursor.fetchone()

    if existing:
        # UPDATE path: preserve existing author_trust_score (dedup)
        # Only update AI annotations, not the trust score
        conn.execute("""
            UPDATE comments
            SET sentiment = ?,
                sarcasm_detected = ?,
                has_reasoning = ?,
                reasoning_summary = ?,
                ai_confidence = ?,
                analyzed_at = datetime('now')
            WHERE reddit_id = ?
        """, (
            ai_result['sentiment'],
            ai_result['sarcasm_detected'],
            ai_result['has_reasoning'],
            ai_result.get('reasoning_summary'),
            ai_result['confidence'],
            comment.reddit_id
        ))

        logger.debug(
            "updated_comment_ai_annotations",
            reddit_id=comment.reddit_id,
            preserved_trust_score=existing['author_trust_score']
        )

    else:
        # INSERT path: include author_trust_score from ProcessedComment
        conn.execute("""
            INSERT INTO comments (
                analysis_run_id, post_id, reddit_id, author, body, created_utc,
                score, depth, prioritization_score, sentiment, sarcasm_detected,
                has_reasoning, reasoning_summary, ai_confidence, author_trust_score,
                analyzed_at
            )
            VALUES (?, ?, ?, ?, ?, datetime(?, 'unixepoch'), ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            run_id,
            post_db_id,
            comment.reddit_id,
            comment.author,
            comment.body,
            comment.created_utc,
            comment.score,
            comment.depth,
            comment.priority_score,
            ai_result['sentiment'],
            ai_result['sarcasm_detected'],
            ai_result['has_reasoning'],
            ai_result.get('reasoning_summary'),
            ai_result['confidence'],
            comment.author_trust_score  # Phase 2 snapshot, NOT a new lookup
        ))

        logger.debug(
            "inserted_comment_with_ai_annotations",
            reddit_id=comment.reddit_id,
            author_trust_score=comment.author_trust_score
        )
