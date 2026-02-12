#!/usr/bin/env python3
"""Stage 2: Score comments by financial relevance and select top N per post.

Reads fetched data from Stage 1, scores each comment using financial keyword
matching, author trust lookups, and engagement metrics, then selects the
top N comments per post.

Usage:
    python scripts/pipeline/score.py [-i data/pipeline/fetched.json] [--top-n 50] [-o data/pipeline/scored.json]

No API keys required. Uses the local database for author trust scores if available.
"""

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def _load_dotenv():
    """Load .env file into os.environ if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

from src.models.reddit_models import ProcessedPost, ProcessedComment, ParentChainEntry
from src.scoring import (
    score_financial_keywords,
    lookup_author_trust_scores,
    normalize_engagement_scores,
    score_and_select_comments,
)


def reconstruct_posts(data: dict) -> list[ProcessedPost]:
    """Reconstruct ProcessedPost objects from JSON data."""
    posts = []
    for pd in data["posts"]:
        comments = []
        for cd in pd.get("comments", []):
            parent_chain = [
                ParentChainEntry(**entry)
                for entry in cd.get("parent_chain", [])
            ]
            comments.append(ProcessedComment(
                reddit_id=cd["reddit_id"],
                post_id=cd["post_id"],
                author=cd["author"],
                body=cd["body"],
                score=cd["score"],
                depth=cd["depth"],
                created_utc=cd["created_utc"],
                priority_score=cd.get("priority_score", 0.0),
                financial_score=cd.get("financial_score", 0.0),
                author_trust_score=cd.get("author_trust_score", 0.0),
                parent_chain=parent_chain,
            ))
        posts.append(ProcessedPost(
            reddit_id=pd["reddit_id"],
            title=pd["title"],
            selftext=pd["selftext"],
            upvotes=pd["upvotes"],
            total_comments=pd["total_comments"],
            image_urls=pd.get("image_urls", []),
            image_analysis=pd.get("image_analysis"),
            comments=comments,
        ))
    return posts


def get_db_connection() -> sqlite3.Connection | None:
    """Try to open the database for author trust lookups. Returns None if unavailable."""
    db_path = os.environ.get("DB_PATH", "./data/wsb.db")
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Stage 2: Score comments by financial relevance"
    )
    parser.add_argument("-i", "--input", default="data/pipeline/fetched.json", help="Input JSON from fetch stage (default: data/pipeline/fetched.json)")
    parser.add_argument("--top-n", type=int, default=50, help="Top comments to keep per post (default: 50)")
    parser.add_argument("-o", "--output", default="data/pipeline/scored.json", help="Output JSON path (default: data/pipeline/scored.json)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        print("Run fetch.py first to create it.")
        sys.exit(1)

    with open(args.input) as f:
        data = json.load(f)

    posts = reconstruct_posts(data)
    original_count = sum(len(p.comments) for p in posts)

    print(f"Loaded {len(posts)} posts with {original_count} comments from {args.input}")

    # Author trust lookup
    conn = get_db_connection()
    if conn:
        all_authors = list({c.author for p in posts for c in p.comments})
        trust_map = lookup_author_trust_scores(conn, all_authors)
        print(f"  Looked up trust scores for {len(all_authors)} unique authors")
        conn.close()
    else:
        print("  Database not found — using default trust score (0.5) for all authors")
        trust_map = {}

    # Score each comment
    for post in posts:
        for comment in post.comments:
            # Financial keyword score
            comment.financial_score = score_financial_keywords(comment.body)

            # Author trust
            comment.author_trust_score = trust_map.get(comment.author, 0.5)

            # Engagement proxy: score / (depth + 1)
            comment._engagement = comment.score / (comment.depth + 1)

        # Normalize engagement across this post's comments
        if post.comments:
            comment_dicts = [{"engagement": c._engagement} for c in post.comments]
            normalized = normalize_engagement_scores(comment_dicts)
            for comment, norm in zip(post.comments, normalized):
                comment.engagement_normalized = norm["engagement_normalized"]

    # Select top N per post
    posts = score_and_select_comments(posts, top_n=args.top_n)
    retained_count = sum(len(p.comments) for p in posts)

    # Serialize
    output_data = {
        "metadata": {
            **data["metadata"],
            "scored_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "original_comments": original_count,
            "retained_comments": retained_count,
            "top_n": args.top_n,
        },
        "posts": [asdict(post) for post in posts],
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"\nScored {original_count} comments, kept {retained_count} (top {args.top_n}/post)")
    print(f"  Output: {args.output}")


if __name__ == "__main__":
    main()
