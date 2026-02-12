"""Reddit data models for WSB Analysis Tool.

This module defines the data structures used throughout the Reddit data pipeline
(Phase 2: Acquisition & Prioritization) and AI analysis pipeline (Phase 3: AI Analysis).

Data Models:
    ProcessedPost — 8 fields representing a Reddit post with metadata
    ProcessedComment — 11 fields representing a Reddit comment with scoring annotations
    ParentChainEntry — 4 fields representing a single parent comment in the chain

These models use dataclasses for simplicity and are designed to map cleanly to
database schema while preserving the data flow from Reddit API through scoring
to storage.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ParentChainEntry:
    """A single parent comment in the chain leading to the current comment.

    Parent chains are ordered with immediate parent first, root last.

    Attributes:
        id: Reddit ID of the parent comment
        body: Text content of the parent comment
        depth: Nesting depth (0 = top-level)
        author: Username of the parent comment author
    """
    id: str
    body: str
    depth: int
    author: str


@dataclass
class ProcessedComment:
    """A Reddit comment with all metadata and scoring annotations.

    This model represents a comment at various stages of the pipeline:
    - After fetching: reddit_id, post_id, author, body, score, depth, created_utc populated
    - After scoring (Phase 2): priority_score, financial_score, author_trust_score populated
    - After AI analysis (Phase 3): Additional fields added by AI parser (not in this model)

    The author_trust_score is set during Phase 2 (story-002-005) via a single lookup
    from the authors table. This value is a point-in-time snapshot and should be
    persisted to the comments table during Phase 3 without re-querying.

    Attributes:
        reddit_id: Unique Reddit comment ID (maps to comments.reddit_id)
        post_id: Reddit ID of the parent post (NOT the DB foreign key)
        author: Username of the comment author
        body: Full text content of the comment
        score: Reddit score (upvotes - downvotes)
        depth: Nesting level (0 = top-level reply to post)
        created_utc: Unix timestamp of comment creation
        priority_score: Combined prioritization score (0.0-1.0+)
        financial_score: Financial keyword density score
        author_trust_score: Author trust snapshot from authors.trust_score (Phase 2 lookup)
        parent_chain: List of parent comments for context (immediate parent first)
    """
    reddit_id: str
    post_id: str
    author: str
    body: str
    score: int
    depth: int
    created_utc: int
    priority_score: float = 0.0
    financial_score: float = 0.0
    author_trust_score: float = 0.0
    parent_chain: List[ParentChainEntry] = field(default_factory=list)


@dataclass
class ProcessedPost:
    """A Reddit post with metadata and associated comments.

    Attributes:
        reddit_id: Unique Reddit post ID (maps to reddit_posts.reddit_id)
        title: Post title
        selftext: Post body text (empty for image/link posts)
        upvotes: Reddit upvote count
        total_comments: Total comment count from Reddit API
        image_url: URL of detected image (i.redd.it, imgur, preview.redd.it)
        image_analysis: GPT-4o-mini vision analysis text (if image detected)
        comments: List of ProcessedComment objects (top N after prioritization)
    """
    reddit_id: str
    title: str
    selftext: str
    upvotes: int
    total_comments: int
    image_url: Optional[str] = None
    image_analysis: Optional[str] = None
    comments: List[ProcessedComment] = field(default_factory=list)
