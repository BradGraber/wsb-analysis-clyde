#!/usr/bin/env python3
"""Stage 4: Run AI sentiment analysis on comments via OpenAI GPT-4o-mini.

Reads comment data from Stage 3, deduplicates against existing annotations,
estimates costs, and processes new comments through GPT-4o-mini for sentiment
analysis and ticker extraction.

Usage:
    python scripts/pipeline/analyze.py [-i data/pipeline/to_analyze.json] [--db-path ./data/wsb.db] [--yes]

Requires env var: OPENAI_API_KEY
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time

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

from src.ai_dedup import partition_for_analysis
from src.ai_batch import process_comments_in_batches, commit_analysis_batch
from src.market_context import fetch_market_context, format_market_context, should_include_context
from src.tuning import get_or_create_prompt_config, get_default_prompt_config
from src.prompts import SYSTEM_PROMPT


# GPT-4o-mini pricing (per 1M tokens)
COST_PER_1M_INPUT = 0.15
COST_PER_1M_OUTPUT = 0.60
AVG_PROMPT_TOKENS = 550
AVG_COMPLETION_TOKENS = 100


def estimate_cost(comment_count: int) -> float:
    """Estimate OpenAI API cost for analyzing comments."""
    input_cost = (comment_count * AVG_PROMPT_TOKENS * COST_PER_1M_INPUT) / 1_000_000
    output_cost = (comment_count * AVG_COMPLETION_TOKENS * COST_PER_1M_OUTPUT) / 1_000_000
    return input_cost + output_cost


def open_db(db_path: str) -> sqlite3.Connection:
    """Open the database connection."""
    if not os.path.exists(db_path):
        print(f"Error: Database not found: {db_path}")
        print("Run store.py first to create it.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


async def run_analysis(input_path: str, db_path: str, skip_confirm: bool):
    """Run AI sentiment analysis on comments."""
    with open(input_path) as f:
        data = json.load(f)

    run_id = data["metadata"]["run_id"]
    comments = data["comments"]
    print(f"Loaded {len(comments)} comments for run #{run_id}")

    conn = open_db(db_path)

    # Deduplication
    print("Checking for already-analyzed comments...")
    skip_list, analyze_list = partition_for_analysis(conn, comments, run_id)

    print(f"  Already analyzed: {len(skip_list)} (will reuse)")
    print(f"  New to analyze:   {len(analyze_list)}")

    if not analyze_list:
        print("\nAll comments already analyzed. Nothing to do.")
        conn.close()
        return

    # Cost estimate
    cost = estimate_cost(len(analyze_list))
    print(f"\nEstimated cost: ${cost:.4f} for {len(analyze_list)} comments")
    print(f"  (~${estimate_cost(1) * 1000:.2f} per 1000 comments)")

    if not skip_confirm:
        response = input("\nProceed with analysis? [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            conn.close()
            return

    # Look up or create the default prompt config for tracking
    prompt_config_id = None
    try:
        default_config = get_default_prompt_config(conn)
        if default_config:
            prompt_config_id = default_config["id"]
        else:
            prompt_config_id = get_or_create_prompt_config(
                conn, name="default", system_prompt=SYSTEM_PROMPT,
                response_format="json_object", is_default=True,
            )
        print(f"  Prompt config: #{prompt_config_id}")
    except Exception as e:
        print(f"  Warning: Could not resolve prompt config ({e}) — continuing without tracking")

    # Fetch market context for reactive/predictive differentiation
    market_context_str = None
    print("\nFetching market index data...")
    try:
        market_data = fetch_market_context()
        if market_data and should_include_context(market_data):
            market_context_str = format_market_context(market_data)
            print(f"  {market_context_str}")
        elif market_data:
            today = market_data["today"]
            moves = ", ".join(f"{t}: {p:+.2f}%" for t, p in today.items())
            print(f"  Flat day ({moves}) — market context not included")
        else:
            print("  Could not fetch market data — proceeding without context")
    except Exception as e:
        print(f"  Market context fetch failed ({e}) — proceeding without context")

    # Run AI analysis
    print(f"\nProcessing {len(analyze_list)} comments in batches of 5...")
    start_time = time.time()

    results = await process_comments_in_batches(analyze_list, run_id,
                                                market_context=market_context_str)

    elapsed = time.time() - start_time
    successful = len(results)
    failed = len(analyze_list) - successful

    print(f"\nAI analysis complete in {elapsed:.1f}s")
    print(f"  Successful: {successful}")
    if failed:
        print(f"  Failed/skipped: {failed}")

    # Store results in batches
    if results:
        print("Storing results to database...")
        # results from process_comments_in_batches are (comment, result) tuples
        # Merge into dicts for commit_analysis_batch
        merged_results = []
        for comment_dict, ai_result in results:
            merged = {
                "reddit_id": comment_dict.get("reddit_id"),
                "post_id": comment_dict.get("post_db_id"),  # DB FK from store.py
                "author": comment_dict.get("author", "unknown"),
                "body": comment_dict.get("body", ""),
                "author_trust_score": comment_dict.get("author_trust_score", 0.5),
                "score": comment_dict.get("score", 0),
                "depth": comment_dict.get("depth", 0),
                "created_utc": comment_dict.get("created_utc", 0),
                "prioritization_score": comment_dict.get("prioritization_score", 0.0),
                "sentiment": ai_result.get("sentiment"),
                "sarcasm_detected": ai_result.get("sarcasm_detected", False),
                "has_reasoning": ai_result.get("has_reasoning", False),
                "reasoning_summary": ai_result.get("reasoning_summary"),
                "ai_confidence": ai_result.get("confidence"),
                "tickers": ai_result.get("tickers", []),
                "ticker_sentiments": ai_result.get("ticker_sentiments", []),
            }
            merged_results.append(merged)

        # Commit in batches of 5
        batch_size = 5
        for i in range(0, len(merged_results), batch_size):
            batch = merged_results[i:i + batch_size]
            commit_analysis_batch(conn, run_id, batch, prompt_config_id)

    # Update analysis run status
    conn.execute(
        "UPDATE analysis_runs SET status = ?, completed_at = datetime('now') WHERE id = ?",
        ("complete", run_id)
    )
    conn.commit()
    conn.close()

    # Summary
    tickers_found = set()
    sentiments = {"bullish": 0, "bearish": 0, "neutral": 0}
    for _, ai_result in results:
        for t in ai_result.get("tickers", []):
            tickers_found.add(t)
        s = ai_result.get("sentiment", "neutral")
        if s in sentiments:
            sentiments[s] += 1

    print(f"\nRun #{run_id} complete:")
    print(f"  Comments analyzed: {successful}")
    print(f"  Unique tickers: {len(tickers_found)}")
    if tickers_found:
        print(f"    {', '.join(sorted(tickers_found)[:20])}")
    print(f"  Sentiment breakdown: {sentiments['bullish']} bullish, {sentiments['bearish']} bearish, {sentiments['neutral']} neutral")


def main():
    parser = argparse.ArgumentParser(
        description="Stage 4: Run AI sentiment analysis on comments"
    )
    parser.add_argument("-i", "--input", default="data/pipeline/to_analyze.json", help="Input JSON from store stage (default: data/pipeline/to_analyze.json)")
    parser.add_argument("--db-path", default=None, help="SQLite database path (default: $DB_PATH or ./data/wsb.db)")
    parser.add_argument("--yes", action="store_true", help="Skip cost confirmation prompt")
    args = parser.parse_args()

    db_path = args.db_path or os.environ.get("DB_PATH", "./data/wsb.db")

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
        print("Set it in your .env file or export it in your shell.")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        print("Run store.py first to create it.")
        sys.exit(1)

    asyncio.run(run_analysis(args.input, db_path, args.yes))


if __name__ == "__main__":
    main()
