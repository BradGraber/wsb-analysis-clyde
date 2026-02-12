#!/usr/bin/env python3
"""Stage 1: Fetch hot posts and comments from r/wallstreetbets.

Connects to Reddit via Async PRAW, fetches hot posts, expands comments,
and writes the results to a JSON file for the scoring stage.

Usage:
    python scripts/pipeline/fetch.py [--limit 10] [--comments 1000] [--skip-images] [-o data/pipeline/fetched.json]

Requires env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
Also requires OPENAI_API_KEY unless --skip-images is set.
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone

# Add project root to path so src.* imports work
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


def check_env_vars(skip_images: bool) -> list[str]:
    """Check required environment variables and return list of missing ones."""
    required = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    if not skip_images:
        required.append("OPENAI_API_KEY")
    return [v for v in required if not os.environ.get(v)]


async def run_fetch(limit: int, comments: int, skip_images: bool, output: str):
    """Fetch posts and comments from Reddit."""
    from src.reddit import get_reddit_client, fetch_hot_posts, fetch_comments

    # Patch out image analysis if --skip-images
    if skip_images:
        import src.reddit as reddit_module
        original_analyze = reddit_module.analyze_post_images

        async def _noop_analyze(image_urls, reddit_id="unknown"):
            return None

        reddit_module.analyze_post_images = _noop_analyze

    try:
        print(f"Connecting to Reddit...")
        reddit = await get_reddit_client()

        print(f"Fetching {limit} hot posts from r/wallstreetbets...")
        posts = await fetch_hot_posts(reddit, subreddit_name="wallstreetbets", limit=limit)
        print(f"  Got {len(posts)} posts")

        total_comments = 0
        for i, post in enumerate(posts, 1):
            print(f"  [{i}/{len(posts)}] Fetching comments for: {post.title[:60]}...")
            submission = await reddit.submission(post.reddit_id)
            post_comments = await fetch_comments(submission, limit=comments)
            post.comments = post_comments
            total_comments += len(post_comments)
            print(f"    {len(post_comments)} comments fetched")

        await reddit.close()

        # Serialize
        images_found = sum(len(p.image_urls) for p in posts)
        images_analyzed = sum(len(p.image_urls) for p in posts if p.image_analysis)

        output_data = {
            "metadata": {
                "subreddit": "wallstreetbets",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "post_count": len(posts),
                "total_comments": total_comments,
                "images_found": images_found,
                "images_analyzed": images_analyzed,
                "skip_images": skip_images,
            },
            "posts": [asdict(post) for post in posts],
        }

        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)

        print(f"\nFetched {len(posts)} posts, {total_comments} comments")
        if not skip_images:
            print(f"  Images found: {images_found}, analyzed: {images_analyzed}")
        print(f"  Output: {output}")

    finally:
        if skip_images:
            import src.reddit as reddit_module
            reddit_module.analyze_post_images = original_analyze


def main():
    parser = argparse.ArgumentParser(
        description="Stage 1: Fetch hot posts and comments from r/wallstreetbets"
    )
    parser.add_argument("--limit", type=int, default=10, help="Number of hot posts to fetch (default: 10)")
    parser.add_argument("--comments", type=int, default=1000, help="Max comments per post (default: 1000)")
    parser.add_argument("--skip-images", action="store_true", help="Skip GPT-4o-mini image analysis (avoids OpenAI cost)")
    parser.add_argument("-o", "--output", default="data/pipeline/fetched.json", help="Output JSON path (default: data/pipeline/fetched.json)")
    args = parser.parse_args()

    missing = check_env_vars(args.skip_images)
    if missing:
        print(f"Error: Missing environment variables: {', '.join(missing)}")
        print("Set them in your .env file or export them in your shell.")
        sys.exit(1)

    asyncio.run(run_fetch(args.limit, args.comments, args.skip_images, args.output))


if __name__ == "__main__":
    main()
