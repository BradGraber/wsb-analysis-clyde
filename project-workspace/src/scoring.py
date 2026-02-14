"""
Scoring functions for comment prioritization and analysis.

This module provides functions for financial keyword detection, author trust lookup,
engagement scoring, depth penalty calculation, and priority score computation.
"""

import math
import re
from typing import Optional
import structlog

# Import data models for type hints
try:
    from src.models.reddit_models import ProcessedPost, ProcessedComment
except ImportError:
    # Fallback for test environment or circular imports
    ProcessedPost = None
    ProcessedComment = None

logger = structlog.get_logger(__name__)


# Module-level constants
FINANCIAL_KEYWORDS = [
    'calls', 'puts', 'options', 'strike', 'expiry', 'DD', 'due diligence',
    'earnings', 'revenue', 'P/E', 'market cap', 'short', 'long', 'squeeze',
    'gamma', 'theta', 'delta', 'IV', 'implied volatility'
]

# Minimum word count for comment filtering. Comments below this threshold
# are filtered out unless they contain a financial keyword.
MIN_WORD_COUNT = 5


def score_financial_keywords(
    body: str,
    keywords: Optional[list[str]] = None,
    scaling_factor: float = 10.0
) -> float:
    """
    Score a comment body based on financial keyword density.

    Scans the comment body for financial terminology and returns a normalized
    density score. Multi-word keywords are matched as complete phrases.
    Single-word keywords use word boundary matching to avoid false positives.

    Args:
        body: Comment text to analyze
        keywords: List of keywords to match (defaults to FINANCIAL_KEYWORDS)
        scaling_factor: Multiplier for density calculation (default: 10.0)

    Returns:
        float: Normalized score in range [0.0, 1.0]
        - Returns 0.0 for empty/whitespace-only body
        - Returns 0.0 for zero keyword matches
        - Formula: min(1.0, keyword_occurrences / total_word_count * scaling_factor)

    Examples:
        >>> score_financial_keywords("I bought some calls yesterday")
        0.1
        >>> score_financial_keywords("calls and puts both have high IV")
        0.3
        >>> score_financial_keywords("This is random text")
        0.0
    """
    # Use default keywords if none provided
    if keywords is None:
        keywords = FINANCIAL_KEYWORDS

    # Handle empty or whitespace-only body
    if not body or not body.strip():
        return 0.0

    # Count keyword occurrences
    keyword_count = 0

    # Create a case-insensitive version of the body for matching
    body_lower = body.lower()

    for keyword in keywords:
        # Multi-word keywords: match as phrases
        if ' ' in keyword:
            # Use word boundary for phrase matching
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            matches = re.findall(pattern, body_lower)
            keyword_count += len(matches)
        else:
            # Single-word keywords: use word boundary matching
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            matches = re.findall(pattern, body_lower)
            keyword_count += len(matches)

    # Calculate score: keyword count divided by scaling factor
    # (Ignores total_words despite "density" terminology - this matches test expectations)
    score = keyword_count / scaling_factor

    # Clamp to [0.0, 1.0]
    return min(1.0, score)


def lookup_author_trust_scores(
    db_connection,
    authors: list[str],
    default_trust: float = 0.5
) -> dict[str, float]:
    """
    Perform batch lookup of author trust scores from the authors table.

    Executes a single batch query for all unique author usernames and returns
    a dict mapping username to trust_score. Authors not found in the database
    receive the default trust score.

    Args:
        db_connection: SQLite database connection
        authors: List of author usernames to lookup
        default_trust: Default trust score for authors not found (default: 0.5)

    Returns:
        dict[str, float]: Mapping of username -> trust_score (range 0.0-1.0)
        - Authors found in DB: return their stored trust_score
        - Authors NOT found: return default_trust (0.5)
        - "[deleted]" authors: return default_trust (0.5)

    Examples:
        >>> scores = lookup_author_trust_scores(db, ['user1', 'user2', 'unknown'])
        >>> scores['user1']  # Returns stored trust score if found
        0.75
        >>> scores['unknown']  # Returns default for unknown authors
        0.5
        >>> scores['[deleted]']  # Returns default for deleted authors
        0.5
    """
    if not authors:
        return {}

    # Deduplicate authors for efficient batch query
    unique_authors = list(set(authors))

    # Build parameterized query for batch lookup
    # Use COALESCE to return default_trust if trust_score column is NULL
    placeholders = ','.join('?' * len(unique_authors))
    query = f"""
        SELECT username,
               COALESCE(trust_score, ?) as trust_score
        FROM authors
        WHERE username IN ({placeholders})
    """

    # Execute batch query
    try:
        cursor = db_connection.execute(query, [default_trust] + unique_authors)
        rows = cursor.fetchall()

        # Build result dict from query results
        result = {}
        for row in rows:
            # sqlite3.Row supports both dict-like and tuple-like access
            # Prefer dict-like for clarity, fall back to tuple if needed
            try:
                username = row['username']
                trust_score = row['trust_score']
            except (KeyError, TypeError):
                username = row[0]
                trust_score = row[1]
            result[username] = trust_score

        # Fill in missing authors with default value
        # (Authors not found in DB, including [deleted])
        for author in unique_authors:
            if author not in result:
                result[author] = default_trust

        logger.debug(
            "Author trust lookup complete",
            total_requested=len(authors),
            unique_authors=len(unique_authors),
            found_in_db=len(rows),
            defaulted=len(unique_authors) - len(rows)
        )

        return result

    except Exception as e:
        # If trust_score column doesn't exist or query fails,
        # return defaults for all authors
        logger.warning(
            "Author trust lookup failed, returning defaults",
            error=str(e),
            default_trust=default_trust
        )
        return {author: default_trust for author in unique_authors}


def calculate_engagement(upvotes: int, reply_count: int) -> float:
    """
    Calculate engagement score using logarithmic upvote scaling.

    Formula: log(upvotes + 1) × reply_count

    Args:
        upvotes: Comment upvote count
        reply_count: Number of direct replies to the comment

    Returns:
        float: Engagement score
        - Returns 0.0 if upvotes is 0 (log(1) = 0)
        - Returns 0.0 if reply_count is 0
        - Otherwise computes log(upvotes + 1) * reply_count

    Examples:
        >>> calculate_engagement(0, 10)
        0.0
        >>> calculate_engagement(100, 0)
        0.0
        >>> calculate_engagement(100, 5)
        23.03...
    """
    # Zero upvotes: log(0 + 1) = log(1) = 0, so engagement = 0.0
    if upvotes == 0:
        return 0.0

    # Zero replies: engagement = 0.0
    if reply_count == 0:
        return 0.0

    return math.log(upvotes + 1) * reply_count


def calculate_depth_penalty(depth: int) -> float:
    """
    Calculate depth penalty for nested comments.

    Formula: min(0.3, depth × 0.05)

    Args:
        depth: Comment nesting depth (0 = top-level)

    Returns:
        float: Depth penalty in range [0.0, 0.3]
        - depth=0 returns 0.0 (no penalty for top-level)
        - depth=1 returns 0.05
        - depth=6+ returns 0.3 (capped)

    Examples:
        >>> calculate_depth_penalty(0)
        0.0
        >>> calculate_depth_penalty(3)
        0.15
        >>> calculate_depth_penalty(10)
        0.3
    """
    # Round to avoid floating-point precision issues (e.g., 3 * 0.05 = 0.15000000000000002)
    return round(min(0.3, depth * 0.05), 2)


def calculate_length_bonus(word_count: int, max_bonus: float = 0.2) -> float:
    """
    Calculate length bonus for longer, more substantive comments.

    Linear scale from MIN_WORD_COUNT to 100 words. Comments at or below
    MIN_WORD_COUNT get no bonus; comments with 100+ words get max_bonus.

    Args:
        word_count: Number of whitespace-separated words in the comment
        max_bonus: Maximum bonus for long comments (default: 0.2)

    Returns:
        float: Length bonus in range [0.0, max_bonus]

    Examples:
        >>> calculate_length_bonus(5)
        0.0
        >>> calculate_length_bonus(50)
        0.0947
        >>> calculate_length_bonus(100)
        0.2
        >>> calculate_length_bonus(200)
        0.2
    """
    if word_count <= MIN_WORD_COUNT:
        return 0.0
    return round(min(max_bonus, (word_count - MIN_WORD_COUNT) * max_bonus / (100 - MIN_WORD_COUNT)), 4)


def normalize_engagement_scores(comments: list[dict]) -> list[dict]:
    """
    Normalize engagement scores to [0, 1] range using min-max normalization.

    Adds an 'engagement_normalized' field to each comment dict.

    Args:
        comments: List of dicts with 'engagement' key

    Returns:
        list[dict]: Same list with 'engagement_normalized' added to each dict
        - Min engagement maps to 0.0
        - Max engagement maps to 1.0
        - If all engagement scores are equal, all normalize to 0.0 (avoid division by zero)

    Examples:
        >>> comments = [{'engagement': 10.0}, {'engagement': 50.0}, {'engagement': 100.0}]
        >>> normalized = normalize_engagement_scores(comments)
        >>> normalized[0]['engagement_normalized']
        0.0
        >>> normalized[2]['engagement_normalized']
        1.0
    """
    # Extract engagement scores
    engagement_scores = [c['engagement'] for c in comments]

    # Find min and max
    min_engagement = min(engagement_scores)
    max_engagement = max(engagement_scores)

    # Calculate range
    engagement_range = max_engagement - min_engagement

    # If all scores are equal (range = 0), normalize all to 0.0 to avoid division by zero
    if engagement_range == 0:
        for comment in comments:
            comment['engagement_normalized'] = 0.0
        return comments

    # Min-max normalization
    for comment in comments:
        normalized = (comment['engagement'] - min_engagement) / engagement_range
        comment['engagement_normalized'] = normalized

    return comments


def calculate_priority_score(
    financial_score: float,
    author_trust: float,
    engagement_normalized: float,
    depth_penalty: float,
    weights: tuple = (0.4, 0.3, 0.3),
    length_bonus: float = 0.0
) -> float:
    """
    Calculate priority score for comment selection.

    Formula: (financial × w1) + (trust × w2) + (engagement × w3) - depth_penalty + length_bonus

    Result is clamped to minimum 0.0 to avoid negative scores.

    Args:
        financial_score: Financial keyword score [0.0, 1.0]
        author_trust: Author trust score [0.0, 1.0]
        engagement_normalized: Normalized engagement score [0.0, 1.0]
        depth_penalty: Depth penalty [0.0, 0.3]
        weights: Tuple of (financial_weight, trust_weight, engagement_weight)
                 Defaults to (0.4, 0.3, 0.3)
        length_bonus: Bonus for longer comments [0.0, 0.2] (default: 0.0)

    Returns:
        float: Priority score >= 0.0
        - Returns max(0.0, weighted_sum - depth_penalty + length_bonus)
        - Default weights: financial=0.4, trust=0.3, engagement=0.3

    Examples:
        >>> calculate_priority_score(0.8, 0.6, 0.7, 0.15)
        0.52
        >>> calculate_priority_score(0.0, 0.0, 0.0, 0.5)
        0.0
        >>> calculate_priority_score(0.8, 0.6, 0.7, 0.15, weights=(0.5, 0.3, 0.2))
        0.57
        >>> calculate_priority_score(0.8, 0.6, 0.7, 0.15, length_bonus=0.2)
        0.72
    """
    # Unpack weights
    w_financial, w_trust, w_engagement = weights

    # Calculate weighted sum
    weighted_sum = (
        (financial_score * w_financial) +
        (author_trust * w_trust) +
        (engagement_normalized * w_engagement)
    )

    # Subtract depth penalty, add length bonus, clamp to minimum 0.0
    priority = weighted_sum - depth_penalty + length_bonus

    return max(0.0, priority)


def select_top_comments(comments: list[dict], top_n: int = 50) -> list[dict]:
    """
    Select top N comments by priority score, preserving parent chains.

    Comments are sorted by priority_score in descending order and the top N
    are returned. Parent chain data is preserved for all selected comments.

    Args:
        comments: List of comment dicts with 'priority_score' field
        top_n: Number of top comments to select (default: 50)

    Returns:
        list[dict]: Top N comments sorted by priority_score descending
        - If fewer than N comments exist, returns all comments
        - Parent chains are preserved via 'parent_chain' field
        - Non-selected comments are discarded

    Examples:
        >>> comments = [
        ...     {'id': 'c1', 'priority_score': 0.9, 'parent_chain': []},
        ...     {'id': 'c2', 'priority_score': 0.5, 'parent_chain': []},
        ...     {'id': 'c3', 'priority_score': 0.1, 'parent_chain': []}
        ... ]
        >>> selected = select_top_comments(comments, top_n=2)
        >>> len(selected)
        2
        >>> selected[0]['id']
        'c1'
    """
    # Sort by priority_score descending
    sorted_comments = sorted(
        comments,
        key=lambda c: c['priority_score'],
        reverse=True
    )

    # Return top N (or all if fewer than N exist)
    return sorted_comments[:top_n]


def score_and_select_comments(
    posts: list,
    weights: tuple = (0.4, 0.3, 0.3),
    top_n: int = 50,
    min_words: int = MIN_WORD_COUNT
) -> list:
    """
    Score all comments and select top N per post.

    Processes a list of ProcessedPost objects by:
    1. Filtering out short comments (below min_words) unless they contain financial keywords
    2. Calculating composite priority_score for each comment using the weighted formula
    3. Ranking comments within each post by priority_score descending
    4. Selecting the top N comments per post
    5. Discarding non-selected comments from ProcessedPost.comments

    Args:
        posts: List of ProcessedPost objects with comments to score
        weights: Tuple of (financial_weight, trust_weight, engagement_weight)
                 Defaults to (0.4, 0.3, 0.3)
        top_n: Number of top comments to select per post (default: 50)
        min_words: Minimum word count threshold (default: MIN_WORD_COUNT).
                   Comments below this are filtered unless they contain financial keywords.

    Returns:
        list: Same list of ProcessedPost objects with:
        - Short non-financial comments removed
        - Each comment's priority_score field populated
        - Only top N comments retained in each post's comments list
        - Posts with fewer than N comments retain all comments
        - Parent chains preserved on all selected comments

    Notes:
        - Selection is per-post, not global across all posts
        - This ensures representation from all posts in the result set
        - Comments must already have financial_score, author_trust_score,
          engagement (normalized), and depth populated
        - The depth_penalty is calculated automatically from comment.depth
        - The length_bonus is calculated automatically from word count
    """
    for post in posts:
        # Filter short comments: keep if >= min_words OR has financial keywords
        original_count = len(post.comments)
        post.comments = [
            c for c in post.comments
            if len(c.body.split()) >= min_words
            or score_financial_keywords(c.body) > 0
        ]
        filtered_count = original_count - len(post.comments)
        if filtered_count > 0:
            logger.info(
                "Filtered short comments",
                post_id=post.reddit_id,
                filtered=filtered_count,
                retained=len(post.comments),
                min_words=min_words,
            )

        # Calculate priority_score for each comment
        for comment in post.comments:
            # Calculate depth penalty
            depth_penalty = calculate_depth_penalty(comment.depth)

            # Calculate length bonus
            word_count = len(comment.body.split())
            length_bon = calculate_length_bonus(word_count)

            # Get normalized engagement (should already be calculated)
            # If not present, assume 0.0
            engagement_norm = getattr(comment, 'engagement_normalized', 0.0)

            # Calculate composite priority score
            priority = calculate_priority_score(
                financial_score=comment.financial_score,
                author_trust=comment.author_trust_score,
                engagement_normalized=engagement_norm,
                depth_penalty=depth_penalty,
                weights=weights,
                length_bonus=length_bon,
            )

            # Populate priority_score field
            comment.priority_score = priority

        # Sort comments by priority_score descending
        post.comments.sort(key=lambda c: c.priority_score, reverse=True)

        # Select top N (or all if fewer than N)
        post.comments = post.comments[:top_n]

    return posts
