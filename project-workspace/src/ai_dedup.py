"""
AI deduplication logic for comment analysis.

Provides functions to check for existing AI annotations before making API calls,
allowing reuse of stored annotations and updating analysis_run_id for deduped comments.
"""

import structlog
from typing import Optional


def check_dedup_batch(db_conn, reddit_ids: list[str]) -> dict[str, Optional[dict]]:
    """
    Batch query comments table for reddit_ids to check for existing AI annotations.

    Args:
        db_conn: SQLite database connection
        reddit_ids: List of reddit_id strings to check

    Returns:
        Dictionary mapping reddit_id to annotation data or None:
        - reddit_id -> dict with annotation fields if comment exists with non-null sentiment
        - reddit_id -> None if comment doesn't exist OR exists with null sentiment

    Annotation dict fields (when present):
        - sentiment: str
        - sarcasm_detected: bool
        - has_reasoning: bool
        - ai_confidence: float
        - reasoning_summary: Optional[str]
        - author_trust_score: float
    """
    # Handle empty input
    if not reddit_ids:
        return {}

    # Build placeholders for IN clause
    placeholders = ','.join('?' * len(reddit_ids))

    # Single batch query for all reddit_ids
    query = f"""
        SELECT
            reddit_id,
            sentiment,
            sarcasm_detected,
            has_reasoning,
            ai_confidence,
            reasoning_summary,
            author_trust_score
        FROM comments
        WHERE reddit_id IN ({placeholders})
    """

    cursor = db_conn.execute(query, reddit_ids)
    rows = cursor.fetchall()

    # Build result dict
    result = {}

    # For each row, check if it has AI annotations (sentiment is not null)
    for row in rows:
        reddit_id = row['reddit_id']

        # If sentiment is null, treat as if no annotations exist
        if row['sentiment'] is None:
            result[reddit_id] = None
        else:
            # Comment has annotations - return them
            result[reddit_id] = {
                'sentiment': row['sentiment'],
                'sarcasm_detected': row['sarcasm_detected'],
                'has_reasoning': row['has_reasoning'],
                'ai_confidence': row['ai_confidence'],
                'reasoning_summary': row['reasoning_summary'],
                'author_trust_score': row['author_trust_score']
            }

    # For reddit_ids not in the result, they don't exist in DB - map to None
    for reddit_id in reddit_ids:
        if reddit_id not in result:
            result[reddit_id] = None

    return result


def partition_for_analysis(db_conn, comments: list[dict], analysis_run_id: int) -> tuple[list[dict], list[dict]]:
    """
    Partition comments into those that can skip AI analysis (existing annotations)
    and those that need AI analysis (new or missing annotations).

    For deduplicated comments, updates their analysis_run_id to the current run
    and attaches their existing annotations for downstream use.

    Args:
        db_conn: SQLite database connection
        comments: List of comment dicts with at least 'reddit_id' field
        analysis_run_id: Current analysis run ID

    Returns:
        Tuple of (skip_list, analyze_list):
        - skip_list: Comments with existing AI annotations (can reuse), with annotations attached
        - analyze_list: Comments needing AI analysis (new or null annotations)
    """
    logger = structlog.get_logger()

    if not comments:
        return [], []

    # Extract reddit_ids
    reddit_ids = [c['reddit_id'] for c in comments]

    # Batch query for existing annotations
    annotations_map = check_dedup_batch(db_conn, reddit_ids)

    skip = []
    analyze = []

    for comment in comments:
        reddit_id = comment['reddit_id']
        annotations = annotations_map.get(reddit_id)

        if annotations is not None:
            # Has existing annotations - skip AI analysis
            # Attach annotations to the comment for downstream use
            enriched_comment = comment.copy()
            enriched_comment['annotations'] = annotations
            skip.append(enriched_comment)
        else:
            # Either doesn't exist or has null annotations - needs AI analysis
            analyze.append(comment)

    # Update analysis_run_id for deduplicated comments
    if skip:
        skip_ids = [c['reddit_id'] for c in skip]
        placeholders = ','.join('?' * len(skip_ids))
        update_query = f"""
            UPDATE comments
            SET analysis_run_id = ?
            WHERE reddit_id IN ({placeholders})
        """
        db_conn.execute(update_query, [analysis_run_id] + skip_ids)
        db_conn.commit()

    # Log deduplication stats
    logger.info(
        "Deduplicated {n} comments, {m} new comments for AI analysis",
        deduplicated=len(skip),
        new=len(analyze),
        total=len(comments),
        n=len(skip),
        m=len(analyze)
    )

    return skip, analyze
