"""Reddit Integration Module

This module provides Async PRAW client initialization and data fetching
functionality for r/wallstreetbets content acquisition.
"""

import os
import asyncio
import asyncpraw
import structlog
from typing import Optional

from src.models.reddit_models import ProcessedPost, ProcessedComment, ParentChainEntry

# Initialize logger
logger = structlog.get_logger()


class RedditAPIError(Exception):
    """Tier 1 error for Reddit API failures (HTTP 503)."""
    pass


async def get_reddit_client() -> asyncpraw.Reddit:
    """Initialize and return an Async PRAW Reddit client with OAuth2.

    Reads authentication credentials from environment variables:
    - REDDIT_CLIENT_ID: Reddit application client ID
    - REDDIT_CLIENT_SECRET: Reddit application client secret
    - REDDIT_USER_AGENT: User agent string for API requests

    Returns:
        asyncpraw.Reddit: Configured Reddit client instance

    Raises:
        ValueError: If any required environment variable is missing or empty
        RedditAPIError: If Async PRAW authentication fails (Tier 1, HTTP 503)

    Example:
        >>> client = await get_reddit_client()
        >>> subreddit = await client.subreddit("wallstreetbets")
    """
    # Validate environment variables
    missing_vars = []

    client_id = os.environ.get('REDDIT_CLIENT_ID', '').strip()
    client_secret = os.environ.get('REDDIT_CLIENT_SECRET', '').strip()
    user_agent = os.environ.get('REDDIT_USER_AGENT', '').strip()

    if not client_id:
        missing_vars.append('REDDIT_CLIENT_ID')
    if not client_secret:
        missing_vars.append('REDDIT_CLIENT_SECRET')
    if not user_agent:
        missing_vars.append('REDDIT_USER_AGENT')

    if missing_vars:
        error_msg = f"Missing required environment variable(s): {', '.join(missing_vars)}"
        logger.error("reddit_client_init_failed", missing_vars=missing_vars)
        raise ValueError(error_msg)

    # Initialize Async PRAW client
    try:
        reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )

        logger.info("reddit_client_initialized", user_agent=user_agent)
        return reddit

    except Exception as e:
        # Catch Async PRAW authentication errors and re-raise as Tier 1 error
        logger.error(
            "reddit_authentication_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        raise RedditAPIError(
            f"Reddit API unavailable (HTTP 503): {str(e)}"
        ) from e


def detect_image_url(submission) -> Optional[str]:
    """Detect if a submission contains an image URL from supported hosting patterns.

    Inspects the submission's URL attribute (or URL string directly) and returns it
    if it matches one of three supported image hosting patterns: i.redd.it, imgur,
    or preview.redd.it.

    Args:
        submission: Either an Async PRAW Submission object with a `.url` attribute,
            or a URL string directly

    Returns:
        Optional[str]: The URL string if it matches a supported image pattern,
            otherwise None

    Example:
        >>> submission.url = "https://i.redd.it/abc123.jpg"
        >>> detect_image_url(submission)
        'https://i.redd.it/abc123.jpg'

        >>> detect_image_url("https://i.redd.it/abc123.jpg")
        'https://i.redd.it/abc123.jpg'

        >>> submission.url = "https://www.youtube.com/watch?v=abc"
        >>> detect_image_url(submission)
        None
    """
    # Handle both string URLs and submission objects
    if isinstance(submission, str):
        url = submission
    else:
        url = submission.url

    # Check for three supported image hosting patterns
    if "i.redd.it" in url or "imgur" in url or "preview.redd.it" in url:
        return url

    return None


async def analyze_post_image(image_url: str, reddit_id: str = "unknown") -> Optional[str]:
    """Analyze an image URL using GPT-4o-mini vision API with retry logic.

    Sends an image URL to the OpenAI GPT-4o-mini vision API to extract visual context
    (charts, earnings data, tickers from screenshots). Implements exponential backoff
    retry logic with delays of [2, 5, 10] seconds. On complete failure after 3 retries,
    logs a warning and returns None for graceful degradation.

    Args:
        image_url: URL of the image to analyze (i.redd.it, imgur, or preview.redd.it)
        reddit_id: Reddit post ID for logging context (default: "unknown")

    Returns:
        Optional[str]: Image analysis text on success, None on failure after retries

    Example:
        >>> analysis = await analyze_post_image("https://i.redd.it/chart.png", "abc123")
        >>> print(analysis)
        'A stock chart showing SPY rising from $400 to $450...'

        >>> # On failure after retries
        >>> analysis = await analyze_post_image("https://i.redd.it/broken.png", "xyz789")
        >>> print(analysis)
        None
    """
    # Import inside function to allow test mocking
    from src.ai_client import OpenAIClient

    retry_delays = [2, 5, 10]  # Custom delays in seconds for 3 retries
    func_logger = structlog.get_logger()

    for attempt in range(3):
        try:
            client = OpenAIClient()
            result = await client.send_vision_analysis(image_url)
            return result['content']

        except Exception as e:
            # If this is the last attempt, log warning and return None
            if attempt == 2:  # 3rd attempt (0-indexed)
                func_logger.warning(
                    "image_analysis_failed",
                    reddit_id=reddit_id,
                    image_url=image_url,
                    error=str(e),
                    error_type=type(e).__name__,
                    attempts=3
                )
                return None

            # Not the last attempt - sleep and retry
            delay = retry_delays[attempt]
            func_logger.debug(
                "image_analysis_retry",
                reddit_id=reddit_id,
                image_url=image_url,
                attempt=attempt + 1,
                delay=delay,
                error=str(e)
            )
            await asyncio.sleep(delay)


async def fetch_hot_posts(
    reddit: asyncpraw.Reddit,
    subreddit_name: str = "wallstreetbets",
    limit: int = 10
) -> list[ProcessedPost]:
    """Fetch hot posts from a subreddit and convert to ProcessedPost objects.

    Retrieves up to `limit` hot posts from the specified subreddit. Each post
    is mapped to a ProcessedPost object with basic fields populated from the
    Async PRAW Submission. Detects image URLs and performs GPT-4o-mini vision
    analysis on detected images with retry logic and graceful degradation.

    Args:
        reddit: Async PRAW Reddit client instance
        subreddit_name: Name of the subreddit to fetch from (default: "wallstreetbets")
        limit: Maximum number of posts to fetch (default: 10)

    Returns:
        list[ProcessedPost]: List of ProcessedPost objects with image_url and
            image_analysis populated for posts with detected images (may be fewer
            than `limit` if fewer posts are available)

    Raises:
        RedditAPIError: If Async PRAW encounters an error during fetch
            (Tier 1 error for HTTP 503)

    Example:
        >>> client = await get_reddit_client()
        >>> posts = await fetch_hot_posts(client, limit=5)
        >>> print(len(posts), posts[0].title)
        >>> # Posts with images will have image_url and image_analysis populated
        >>> if posts[0].image_url:
        ...     print(f"Image: {posts[0].image_url}")
        ...     print(f"Analysis: {posts[0].image_analysis}")
    """
    try:
        subreddit = await reddit.subreddit(subreddit_name)
        posts = []

        async for submission in subreddit.hot(limit=limit):
            # Detect image URL
            image_url = detect_image_url(submission)

            # Analyze image if detected
            image_analysis = None
            if image_url:
                image_analysis = await analyze_post_image(image_url, submission.id)

            # Map Async PRAW Submission attributes to ProcessedPost fields
            processed_post = ProcessedPost(
                reddit_id=submission.id,
                title=submission.title,
                selftext=submission.selftext,
                upvotes=submission.score,
                total_comments=submission.num_comments,
                image_url=image_url,
                image_analysis=image_analysis,
                comments=[]
            )
            posts.append(processed_post)

        logger.info(
            "hot_posts_fetched",
            subreddit=subreddit_name,
            requested_limit=limit,
            fetched_count=len(posts),
            posts_with_images=sum(1 for p in posts if p.image_url is not None)
        )
        return posts

    except Exception as e:
        # Catch Async PRAW exceptions and re-raise as Tier 1 error
        logger.error(
            "hot_posts_fetch_failed",
            subreddit=subreddit_name,
            limit=limit,
            error=str(e),
            error_type=type(e).__name__
        )
        raise RedditAPIError(
            f"Reddit API unavailable (HTTP 503): {str(e)}"
        ) from e


def build_parent_chains(comments_data, comment_forest=None):
    """Build parent chain context for each comment by walking up the comment tree.

    This function supports two modes of operation:
    1. Test mode: Takes list of dicts, returns dict mapping comment IDs to parent chains
    2. Production mode: Takes list of ProcessedComment objects + comment_forest, mutates in-place

    Args:
        comments_data: Either list of comment data dicts (test mode) or list of ProcessedComment objects (production mode)
        comment_forest: Async PRAW CommentForest (required in production mode, optional in test mode)

    Returns:
        dict: In test mode, returns mapping of comment_id -> list of parent chain entry dicts
        None: In production mode, mutates ProcessedComment objects in-place
    """
    # Detect mode based on input type
    if not comments_data:
        return {} if comment_forest is None else None

    is_dict_mode = isinstance(comments_data[0], dict)

    if is_dict_mode:
        # Test mode: work with dicts
        comment_lookup = {comment['id']: comment for comment in comments_data}
        chains = {}

        for comment in comments_data:
            parent_chain = []
            current_parent_id = comment['parent_id']

            # Walk up the parent chain
            while current_parent_id:
                # Check if parent is a submission (t3_xxx) — top-level comment
                if current_parent_id.startswith('t3_'):
                    break

                # Extract parent comment ID (t1_xxx -> xxx)
                parent_comment_id = current_parent_id[3:]  # Strip "t1_" prefix

                # Look up parent comment
                parent_comment = comment_lookup.get(parent_comment_id)

                if not parent_comment:
                    # Parent not in fetched set (orphaned comment) — truncate chain
                    logger.debug(
                        "orphaned_comment_chain_truncated",
                        comment_id=comment['id'],
                        missing_parent_id=parent_comment_id
                    )
                    break

                # Add parent to chain as dict
                parent_entry = {
                    'id': parent_comment['id'],
                    'body': parent_comment['body'],
                    'depth': parent_comment['depth'],
                    'author': parent_comment['author']
                }

                parent_chain.append(parent_entry)

                # Move to next parent
                current_parent_id = parent_comment['parent_id']

            # Store chain for this comment
            chains[comment['id']] = parent_chain

        return chains

    else:
        # Production mode: work with ProcessedComment objects
        if comment_forest is None:
            raise ValueError("comment_forest is required when working with ProcessedComment objects")

        # Build lookup dict: reddit_id -> PRAW comment object
        comment_lookup = {}
        all_praw_comments = comment_forest.list()
        for praw_comment in all_praw_comments:
            comment_lookup[praw_comment.id] = praw_comment

        # Process each ProcessedComment
        for processed_comment in comments_data:
            parent_chain = []

            # Find corresponding PRAW comment
            praw_comment = comment_lookup.get(processed_comment.reddit_id)
            if not praw_comment:
                # Comment not in forest (shouldn't happen, but handle gracefully)
                logger.warning(
                    "comment_not_in_forest",
                    reddit_id=processed_comment.reddit_id
                )
                continue

            # Walk up the parent chain
            current_parent_id = praw_comment.parent_id

            while current_parent_id:
                # Check if parent is a submission (t3_xxx) — top-level comment
                if current_parent_id.startswith('t3_'):
                    break

                # Extract parent comment ID (t1_xxx -> xxx)
                parent_comment_id = current_parent_id[3:]  # Strip "t1_" prefix

                # Look up parent comment
                parent_praw_comment = comment_lookup.get(parent_comment_id)

                if not parent_praw_comment:
                    # Parent not in fetched set (orphaned comment) — truncate chain
                    logger.debug(
                        "orphaned_comment_chain_truncated",
                        reddit_id=processed_comment.reddit_id,
                        missing_parent_id=parent_comment_id
                    )
                    break

                # Extract parent data
                parent_author = "[deleted]"
                if parent_praw_comment.author is not None:
                    parent_author = str(parent_praw_comment.author)

                parent_body = parent_praw_comment.body if hasattr(parent_praw_comment, 'body') else "[deleted]"

                # Create ParentChainEntry
                parent_entry = ParentChainEntry(
                    id=parent_praw_comment.id,
                    body=parent_body,
                    depth=parent_praw_comment.depth,
                    author=parent_author
                )

                parent_chain.append(parent_entry)

                # Move to next parent
                current_parent_id = parent_praw_comment.parent_id

            # Set parent_chain on ProcessedComment (already ordered immediate parent -> root)
            processed_comment.parent_chain = parent_chain

        return None


async def fetch_comments(
    submission,
    limit: int = 1000,
    replace_more_limit: int = 0
) -> list[ProcessedComment]:
    """Fetch comments from a submission with engagement sorting and replace_more handling.

    Fetches up to `limit` comments from an Async PRAW Submission, calls replace_more()
    to expand collapsed threads, constructs ProcessedComment objects with correct depth
    tracking, and handles edge cases. Comments are sorted by engagement (score × replies)
    after fetching.

    Args:
        submission: Async PRAW Submission object with a .comments attribute
        limit: Maximum number of comments to return (default: 1000)
        replace_more_limit: Number of MoreComments to replace (default: 0)
            - 0: Skip deep expansion (fastest)
            - None: Expand all MoreComments (slowest, most complete)
            - N: Expand up to N MoreComments objects

    Returns:
        list[ProcessedComment]: List of ProcessedComment objects sorted by engagement
            (score × replies count) in descending order, limited to top `limit` comments.
            Returns empty list if submission has zero comments.

    Notes:
        - replace_more() timeout or failure logs a warning and proceeds with loaded comments
        - Each ProcessedComment has priority_score, financial_score, author_trust_score
          initialized to 0.0, and parent_chain initialized to empty list
        - Comment depth is set from Async PRAW's comment.depth attribute (0 for top-level)
        - Deleted/removed authors are stored as "[deleted]" as returned by Async PRAW

    Example:
        >>> submission = await reddit.submission("abc123")
        >>> comments = await fetch_comments(submission, limit=500, replace_more_limit=5)
        >>> print(len(comments), comments[0].body[:50])
    """
    try:
        # Access the comment forest
        comment_forest = submission.comments

        # Attempt to replace MoreComments objects
        try:
            await comment_forest.replace_more(limit=replace_more_limit)
        except Exception as e:
            # Log warning and proceed with already-loaded comments
            logger.warning(
                "replace_more_failed",
                submission_id=submission.id,
                replace_more_limit=replace_more_limit,
                error=str(e),
                error_type=type(e).__name__
            )

        # Flatten the comment tree
        all_comments = comment_forest.list()

        # Handle zero comments case
        if not all_comments:
            logger.info(
                "comments_fetched",
                submission_id=submission.id,
                requested_limit=limit,
                fetched_count=0
            )
            return []

        # Build ProcessedComment objects with engagement scoring
        processed_comments = []
        for comment in all_comments:
            # Handle deleted/removed authors
            author_name = "[deleted]"
            if comment.author is not None:
                author_name = str(comment.author)

            # Count replies for engagement metric
            # comment.replies is a CommentForest, len() gives direct reply count
            reply_count = len(comment.replies) if hasattr(comment, 'replies') else 0

            # Calculate engagement metric (score × replies)
            engagement = comment.score * reply_count

            # Create ProcessedComment with required fields
            processed_comment = ProcessedComment(
                reddit_id=comment.id,
                post_id=submission.id,
                author=author_name,
                body=comment.body,
                score=comment.score,
                depth=comment.depth,
                created_utc=int(comment.created_utc),
                priority_score=0.0,
                financial_score=0.0,
                author_trust_score=0.0,
                parent_chain=[]
            )

            # Store engagement for sorting (temporary attribute)
            processed_comment._engagement = engagement
            processed_comments.append(processed_comment)

        # Sort by engagement metric (descending) and take top `limit`
        processed_comments.sort(key=lambda c: c._engagement, reverse=True)
        result = processed_comments[:limit]

        # Clean up temporary attribute
        for comment in result:
            delattr(comment, '_engagement')

        # Build parent chains for all comments
        build_parent_chains(result, comment_forest)

        logger.info(
            "comments_fetched",
            submission_id=submission.id,
            requested_limit=limit,
            total_fetched=len(all_comments),
            returned_count=len(result)
        )

        return result

    except Exception as e:
        # Catch any unexpected errors and log
        logger.error(
            "comments_fetch_failed",
            submission_id=getattr(submission, 'id', 'unknown'),
            limit=limit,
            replace_more_limit=replace_more_limit,
            error=str(e),
            error_type=type(e).__name__
        )
        # Return empty list on error rather than raising
        return []
