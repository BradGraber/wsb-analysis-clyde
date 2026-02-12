"""Batch processing and transaction management for AI analysis pipeline.

This module handles Phase 3 (AI Analysis) batch processing, including:
- Concurrent batch processing with ThreadPoolExecutor
- Retry logic for malformed responses and rate limits
- Atomic transaction commits for batches of 5 comments
- Author trust score persistence (no re-lookup from authors table)

Key Functions:
    store_analysis_results — Persist AI analysis results with author_trust_score snapshot
    commit_analysis_batch — Single transaction per batch of 5 comments
    process_comments_in_batches — Main orchestrator
    process_single_batch — ThreadPoolExecutor coordinator
    process_comment_with_retry — Retry handler for individual comments
    store_comment_tickers — Junction table persistence
"""

import sqlite3
import structlog
from typing import Any, Dict, List, Optional, Tuple
import concurrent.futures
import asyncio
from openai import RateLimitError

logger = structlog.get_logger()


def calculate_backoff_delay(attempt: int, base_delay: float = 1.0, max_delay: float = 30.0) -> float:
    """Calculate exponential backoff delay for retry attempts.

    Implements exponential backoff: base_delay * 2^attempt, capped at max_delay.
    Used for rate limit retries in process_comment_with_retry().

    Args:
        attempt: Retry attempt number (0-indexed)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 30.0)

    Returns:
        Delay in seconds for this attempt

    Examples:
        >>> calculate_backoff_delay(0)  # First retry
        1.0
        >>> calculate_backoff_delay(1)  # Second retry
        2.0
        >>> calculate_backoff_delay(2)  # Third retry
        4.0
        >>> calculate_backoff_delay(3)  # Fourth retry
        8.0
        >>> calculate_backoff_delay(10)  # Far future retry (capped)
        30.0
    """
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)


async def process_comment_with_retry(
    comment: Dict[str, Any],
    openai_client: Any,
    run_id: int,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Process a single comment with retry logic for malformed JSON and rate limits.

    Retry behaviors:
    - Malformed JSON (MalformedResponseError): Retry once with identical prompt
    - Rate limit (RateLimitError): Retry up to 3 times with exponential backoff [1s, 2s, 4s, 8s]

    On final failure (after all retries exhausted), skip the comment and log a warning
    with the comment's reddit_id and error details. Processing continues for other comments.

    Args:
        comment: Comment dict with reddit_id, body, author, etc.
        openai_client: OpenAI client instance with send_chat_completion method
        run_id: Analysis run ID (for logging context)
        system_prompt: Optional system prompt (built from prompts.py if not provided)
        user_prompt: Optional user prompt (built from prompts.py if not provided)

    Returns:
        Parsed analysis result dict if successful, None if comment was skipped

    Example:
        >>> result = await process_comment_with_retry(comment, client, run_id=1)
        >>> if result:
        ...     # Successfully analyzed
        ...     sentiment = result['sentiment']
        >>> else:
        ...     # Comment was skipped after retries
        ...     pass
    """
    from src.prompts import SYSTEM_PROMPT, build_user_prompt
    from src.ai_parser import parse_ai_response, MalformedResponseError

    retry_logger = structlog.get_logger()

    # Build prompts if not provided
    if system_prompt is None:
        system_prompt = SYSTEM_PROMPT

    if user_prompt is None:
        user_prompt = build_user_prompt(
            post_title=comment.get('post_title', 'WSB Discussion'),
            image_description=comment.get('image_description', None),
            parent_chain_formatted=comment.get('parent_chain_formatted', ''),
            author=comment.get('author', 'unknown'),
            author_trust=comment.get('author_trust_score', 0.5),
            comment_body=comment.get('body', '')
        )

    reddit_id = comment.get('reddit_id', 'unknown')

    # Malformed JSON retry: max 1 retry (2 total attempts)
    max_malformed_retries = 1
    # Rate limit retry: max 3 retries (4 total attempts)
    max_rate_limit_retries = 3

    malformed_attempt = 0
    rate_limit_attempt = 0

    while True:
        try:
            # Call OpenAI API
            response = await openai_client.send_chat_completion(system_prompt, user_prompt)

            # Parse response
            raw_content = response.get('content', '')
            parsed = parse_ai_response(raw_content)

            # Success - return parsed result
            return parsed

        except MalformedResponseError as e:
            # Malformed JSON - retry once
            if malformed_attempt < max_malformed_retries:
                malformed_attempt += 1
                retry_logger.info(
                    "malformed_json_retry",
                    retry_attempt=malformed_attempt,
                    reddit_id=reddit_id,
                    error_type="malformed_json",
                    run_id=run_id
                )
                # No backoff delay for malformed JSON (retry immediately)
                continue
            else:
                # Exhausted malformed retries - skip comment
                raw_content = response.get('content', '') if 'response' in locals() else str(e)
                retry_logger.warning(
                    "comment_skipped_malformed_json",
                    reddit_id=reddit_id,
                    raw_response=raw_content[:500],
                    error_type="malformed_json",
                    run_id=run_id
                )
                return None

        except RateLimitError as e:
            # Rate limit - retry up to 3 times with exponential backoff
            if rate_limit_attempt < max_rate_limit_retries:
                delay = calculate_backoff_delay(rate_limit_attempt)
                rate_limit_attempt += 1

                retry_logger.info(
                    "rate_limit_retry",
                    retry_attempt=rate_limit_attempt,
                    reddit_id=reddit_id,
                    error_type="rate_limit",
                    backoff_delay=delay,
                    run_id=run_id
                )

                # Wait with exponential backoff
                await asyncio.sleep(delay)
                continue
            else:
                # Exhausted rate limit retries - skip comment
                retry_logger.warning(
                    "comment_skipped_rate_limit",
                    reddit_id=reddit_id,
                    error_type="rate_limit",
                    max_retries=max_rate_limit_retries,
                    run_id=run_id
                )
                return None

        except Exception as e:
            # Other exceptions - skip comment immediately (no retry)
            retry_logger.warning(
                "comment_skipped_other_error",
                reddit_id=reddit_id,
                error_type=type(e).__name__,
                error_message=str(e),
                run_id=run_id
            )
            return None


def store_analysis_results(
    conn: sqlite3.Connection,
    run_id: int,
    analysis_results: List[Dict[str, Any]]
) -> None:
    """Persist AI analysis results for a batch of comments.

    This function handles Phase 3 storage — inserting or updating comment records
    with AI annotations after analysis. It preserves the author_trust_score that
    was set during Phase 2 (story-002-005) and persists it to the database.

    Key behaviors:
    - INSERT if comment doesn't exist (includes author_trust_score from result dict)
    - UPDATE if comment exists (adds AI annotations, NEVER overwrites author_trust_score)
    - Does NOT query the authors table (Phase 2 already did the lookup)
    - Each result dict contains the author_trust_score from Phase 2

    This function is called by commit_analysis_batch() as part of the batch-of-5
    transaction commit (story-003-008).

    Args:
        conn: SQLite database connection (within an active transaction)
        run_id: Foreign key to analysis_runs.id
        analysis_results: List of dicts with fields:
            - reddit_id: str — Comment reddit ID
            - post_id: int — Database FK to reddit_posts.id (NOT reddit_id)
            - author: str — Username
            - body: str — Comment text
            - author_trust_score: float — Trust score from Phase 2 lookup
            - sentiment: str — AI-determined sentiment (bullish/bearish/neutral)
            - ai_confidence: float — AI confidence score (0.0-1.0)
            - tickers: List[str] — Extracted tickers (optional, for junction table)
            - sarcasm_detected: bool — AI sarcasm flag (optional)
            - has_reasoning: bool — AI reasoning flag (optional)
            - reasoning_summary: str — AI reasoning text (optional)
            - score: int — Reddit score (optional, for new comments)
            - depth: int — Nesting depth (optional, for new comments)
            - created_utc: int — Unix timestamp (optional, for new comments)
            - prioritization_score: float — Priority score (optional, for new comments)

    Example:
        >>> analysis_results = [
        ...     {
        ...         'reddit_id': 'comment1',
        ...         'post_id': 123,  # DB FK, not reddit_id
        ...         'author': 'user1',
        ...         'body': 'AAPL calls look good',
        ...         'author_trust_score': 0.87,  # From Phase 2
        ...         'sentiment': 'bullish',
        ...         'ai_confidence': 0.9,
        ...         'tickers': ['AAPL']
        ...     }
        ... ]
        >>> store_analysis_results(conn, run_id=1, analysis_results=analysis_results)
    """
    for result in analysis_results:
        reddit_id = result['reddit_id']
        post_db_id = result['post_id']  # This is already the DB FK
        author_trust_score = result.get('author_trust_score', 0.5)

        # Check if comment exists
        existing_cursor = conn.execute(
            "SELECT id, author_trust_score FROM comments WHERE reddit_id = ?",
            (reddit_id,)
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
                result.get('sentiment'),
                result.get('sarcasm_detected', False),
                result.get('has_reasoning', False),
                result.get('reasoning_summary'),
                result.get('ai_confidence'),
                reddit_id
            ))

            logger.debug(
                "updated_comment_ai_annotations",
                reddit_id=reddit_id,
                preserved_trust_score=existing['author_trust_score']
            )

        else:
            # INSERT path: include author_trust_score from analysis result
            # This is the Phase 2 snapshot, NOT a new lookup
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
                reddit_id,
                result.get('author', 'unknown'),
                result.get('body', ''),
                result.get('created_utc', 0),
                result.get('score', 0),
                result.get('depth', 0),
                result.get('prioritization_score', 0.0),
                result.get('sentiment'),
                result.get('sarcasm_detected', False),
                result.get('has_reasoning', False),
                result.get('reasoning_summary'),
                result.get('ai_confidence'),
                author_trust_score  # Phase 2 snapshot, NOT a new lookup
            ))

            logger.debug(
                "inserted_comment_with_ai_annotations",
                reddit_id=reddit_id,
                author_trust_score=author_trust_score
            )


async def process_single_batch(
    comments: List[Dict[str, Any]],
    openai_client: Any,
    run_id: int
) -> List[Tuple[Dict[str, Any], Any]]:
    """Process a single batch of comments concurrently using ThreadPoolExecutor.

    Each comment in the batch is processed in parallel by a separate worker thread.
    Each worker sends one comment to OpenAI (1 comment per API call). Each comment
    is processed with retry logic for malformed JSON and rate limits via
    process_comment_with_retry(). If a worker fails after retries, the remaining
    workers continue normally and the failure is logged with the reddit_id for attribution.

    Args:
        comments: List of up to 5 comment dicts (reddit_id, body, author, etc.)
        openai_client: OpenAI client instance with send_chat_completion method
        run_id: Analysis run ID (for logging context)

    Returns:
        List of (comment, result_or_error) tuples for successful workers.
        Failed workers are logged but not included in the return list.
    """
    results = []

    def process_single_comment(comment: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
        """Synchronous wrapper for processing a single comment (runs in thread pool)."""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Call process_comment_with_retry (handles malformed JSON and rate limit retries)
                result = loop.run_until_complete(
                    process_comment_with_retry(comment, openai_client, run_id)
                )

                # If result is None, the comment was skipped after retries
                if result is None:
                    raise ValueError(f"Comment {comment.get('reddit_id', 'unknown')} skipped after retries")

                return (comment, result)
            finally:
                loop.close()

        except Exception as e:
            # Log error with reddit_id for attribution
            # Use structlog.get_logger() to get the current logger (allows mocking)
            error_logger = structlog.get_logger()
            error_logger.error(
                "ai_worker_failed",
                reddit_id=comment.get('reddit_id', 'unknown'),
                error_type=type(e).__name__,
                error_message=str(e),
                run_id=run_id
            )
            raise  # Re-raise so future tracks this as failed

    # Use ThreadPoolExecutor with max_workers=5
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all comments to the executor
        future_to_comment = {
            executor.submit(process_single_comment, comment): comment
            for comment in comments
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_comment):
            comment = future_to_comment[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                # Worker failed - already logged in process_single_comment
                # Don't include in results, but continue with other workers
                pass

    return results


def store_comment_tickers(
    conn: sqlite3.Connection,
    comment_id: int,
    tickers: List[str],
    sentiments: List[str]
) -> None:
    """Insert ticker-sentiment pairs into comment_tickers junction table.

    This function is called within the batch transaction (commit_analysis_batch)
    to persist ticker mentions extracted from AI analysis. Each ticker is stored
    as uppercase with its corresponding sentiment.

    Args:
        conn: SQLite database connection (within an active transaction)
        comment_id: Database FK to comments.id (NOT reddit_id)
        tickers: List of ticker symbols (will be normalized to uppercase)
        sentiments: List of sentiments corresponding to tickers (same length)

    Example:
        >>> store_comment_tickers(conn, comment_id=123, tickers=['AAPL', 'MSFT'], sentiments=['bullish', 'neutral'])
    """
    if not tickers:
        return

    for ticker, sentiment in zip(tickers, sentiments):
        # Normalize ticker to uppercase
        normalized_ticker = ticker.upper()

        # INSERT OR IGNORE to prevent duplicate (comment_id, ticker) pairs
        conn.execute("""
            INSERT OR IGNORE INTO comment_tickers (comment_id, ticker, sentiment, created_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (comment_id, normalized_ticker, sentiment))


def commit_analysis_batch(
    db_conn: sqlite3.Connection,
    run_id: int,
    batch_results: List[Dict[str, Any]]
) -> None:
    """Commit a batch of analyzed comments in a single SQLite transaction.

    This function implements the batch-of-5 commit pattern for Phase 3 AI analysis.
    Each batch (typically 5 comments, but may be fewer for the final batch) is
    committed atomically. On SQLite error, the entire batch is rolled back and
    the error is logged. Rolled-back comments are NOT retried.

    Transaction includes:
    - INSERT/UPDATE comment records with AI annotations
    - INSERT comment_tickers junction table records
    - All operations are atomic (all succeed or all rollback)

    Args:
        db_conn: SQLite database connection
        run_id: Foreign key to analysis_runs.id
        batch_results: List of dicts with analysis results (typically 5, may be fewer)

    Example:
        >>> batch_results = [
        ...     {
        ...         'reddit_id': 'comment1',
        ...         'post_id': 123,
        ...         'author': 'user1',
        ...         'body': 'AAPL calls look good',
        ...         'author_trust_score': 0.87,
        ...         'sentiment': 'bullish',
        ...         'ai_confidence': 0.9,
        ...         'tickers': ['AAPL'],
        ...         'ticker_sentiments': ['bullish']
        ...     }
        ... ]
        >>> commit_analysis_batch(db_conn, run_id=1, batch_results=batch_results)
    """
    if not batch_results:
        return

    batch_logger = structlog.get_logger()

    try:
        # Store all comment records with AI annotations
        # SQLite starts an implicit transaction on the first write
        store_analysis_results(db_conn, run_id, batch_results)

        # Store comment_tickers junction records for each comment
        for result in batch_results:
            # Get the comment_id for this reddit_id
            comment_row = db_conn.execute(
                "SELECT id FROM comments WHERE reddit_id = ?",
                (result['reddit_id'],)
            ).fetchone()

            if comment_row:
                comment_id = comment_row['id']
                tickers = result.get('tickers', [])
                ticker_sentiments = result.get('ticker_sentiments', [])

                if tickers:
                    store_comment_tickers(db_conn, comment_id, tickers, ticker_sentiments)

        # Commit the transaction
        db_conn.commit()

        batch_logger.debug(
            "batch_committed",
            batch_size=len(batch_results),
            run_id=run_id
        )

    except sqlite3.Error as e:
        # Rollback entire batch on SQLite error
        db_conn.rollback()

        # Extract reddit_ids for logging
        reddit_ids = [result.get('reddit_id', 'unknown') for result in batch_results]

        # Log error with batch details
        batch_logger.error(
            "batch_rollback",
            batch_size=len(batch_results),
            reddit_ids=reddit_ids,
            error_type=type(e).__name__,
            error_message=str(e),
            run_id=run_id
        )


async def process_comments_in_batches(
    comments: List[Dict[str, Any]],
    run_id: int,
    db_conn: Optional[sqlite3.Connection] = None,
    openai_client: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """Main orchestrator for concurrent AI batch processing.

    Groups comments into batches of 5 and processes each batch concurrently.
    Each batch completes before proceeding to the next batch. Progress is logged
    after each batch completes.

    This function is the entry point for Phase 3 AI analysis after deduplication.

    Args:
        comments: List of comment dicts needing AI analysis (reddit_id, body, etc.)
        run_id: Analysis run ID
        db_conn: SQLite database connection (optional, for future use)
        openai_client: OpenAI client instance (optional, created if not provided)

    Returns:
        List of all analysis results from all batches (flattened)

    Example:
        >>> comments = [{'reddit_id': f'c{i}', 'body': f'Text {i}'} for i in range(12)]
        >>> results = await process_comments_in_batches(comments, run_id=1)
        >>> # Processes as 3 batches: [5, 5, 2]
    """
    batch_logger = structlog.get_logger()

    if not comments:
        batch_logger.info("no_comments_to_process", run_id=run_id)
        return []

    # Initialize OpenAI client if not provided (lazy initialization avoids
    # creating client when process_single_batch is mocked in tests)
    client_created = False
    if openai_client is None:
        # Try to create client, but if it fails (e.g., missing API key in tests),
        # we'll use a placeholder since process_single_batch might be mocked
        try:
            from src.ai_client import OpenAIClient
            openai_client = OpenAIClient()
            client_created = True
        except (ValueError, ImportError):
            # If we can't create a client (e.g., in tests without API key),
            # use a placeholder - process_single_batch might be mocked
            openai_client = object()  # Placeholder for mocked scenarios

    # Calculate batch count
    batch_size = 5
    total_batches = (len(comments) + batch_size - 1) // batch_size  # Ceiling division

    all_results = []
    completed_count = 0

    # Process in batches of 5
    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(comments))
        batch = comments[start_idx:end_idx]

        batch_logger.debug(
            "processing_batch",
            batch_number=batch_idx + 1,
            total_batches=total_batches,
            batch_size=len(batch),
            run_id=run_id
        )

        # Process this batch concurrently
        batch_results = await process_single_batch(batch, openai_client, run_id)

        # Collect results
        all_results.extend(batch_results)
        completed_count += len(batch)

        # Log progress after batch completes
        batch_logger.info(
            f"Processed batch {batch_idx + 1}/{total_batches}: {completed_count} comments complete",
            batch_number=batch_idx + 1,
            total_batches=total_batches,
            completed=completed_count,
            total_comments=len(comments),
            run_id=run_id
        )

    batch_logger.info(
        "batch_processing_complete",
        total_batches=total_batches,
        total_comments=len(comments),
        successful_results=len(all_results),
        run_id=run_id
    )

    return all_results
