#!/usr/bin/env python3
"""Prompt tuning workbench for WSB comment analysis.

Analyze individual comments with configurable parameters to experiment
with different prompts, temperatures, and market context settings.

Usage:
    python scripts/tune_prompt.py REDDIT_ID [OPTIONS]
    python scripts/tune_prompt.py o50n9bi --dry-run
    python scripts/tune_prompt.py o50n9bi --temperature 0.7 --no-market-context
    python scripts/tune_prompt.py o50n9bi --runs 5
    python scripts/tune_prompt.py o50n9bi --compare "temp=0.3" "temp=0.7,no-market-context"
    python scripts/tune_prompt.py --list-flips --db data/wsb_pre_update.db --db2 data/wsb.db

Requires env var: OPENAI_API_KEY (not needed for --dry-run or --list-flips)
"""

import argparse
import json
import os
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone

# Add project root to path for src imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_dotenv():
    """Load .env file into os.environ if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

from src.prompts import SYSTEM_PROMPT, build_user_prompt
from src.ai_parser import parse_ai_response, normalize_tickers
from src.market_context import fetch_market_context, should_include_context, format_market_context


# Defaults
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 500

# GPT-4o-mini pricing (per 1M tokens)
COST_PER_1M_INPUT = 0.15
COST_PER_1M_OUTPUT = 0.60


DEFAULT_LOG_PATH = "data/tuning-results.jsonl"


def append_log(log_path, entry):
    """Append a JSON line to the log file."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def build_log_entry(reddit_id, config, parsed, usage, mode, label=None, tag=None):
    """Build a structured log entry for one analysis run."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reddit_id": reddit_id,
        "config": {
            "model": config["model"],
            "temperature": config["temperature"],
            "max_tokens": config["max_tokens"],
            "market_context": config["market_context"],
            "system_prompt_file": config.get("system_prompt_file"),
        },
        "result": {
            "sentiment": parsed["sentiment"],
            "confidence": parsed["confidence"],
            "tickers": list(zip(parsed["tickers"], parsed["ticker_sentiments"])),
            "sarcasm_detected": parsed["sarcasm_detected"],
            "has_reasoning": parsed["has_reasoning"],
            "reasoning_summary": parsed.get("reasoning_summary"),
        },
        "usage": usage,
        "mode": mode,
        "label": label,
        "tag": tag,
    }


def load_comment(db_path, reddit_id):
    """Load a comment with its post context from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    row = conn.execute("""
        SELECT c.reddit_id, c.body, c.author, c.author_trust_score,
               c.parent_chain, c.sentiment, c.ai_confidence,
               c.sarcasm_detected, c.has_reasoning, c.reasoning_summary,
               p.title AS post_title, p.image_analysis
        FROM comments c
        JOIN reddit_posts p ON c.post_id = p.id
        WHERE c.reddit_id = ?
    """, (reddit_id,)).fetchone()

    conn.close()

    if row is None:
        print(f"Error: Comment '{reddit_id}' not found in {db_path}")
        sys.exit(1)

    return dict(row)


def get_market_context_string(args):
    """Resolve market context based on CLI args."""
    if args.no_market_context:
        return None
    if args.market_context:
        return args.market_context

    # Fetch live market context with gate check
    try:
        data = fetch_market_context()
        if data and should_include_context(data):
            return format_market_context(data)
    except Exception:
        pass
    return None


def build_prompts(comment, market_context_str, system_prompt_override=None):
    """Build the system and user prompts for a comment."""
    sys_prompt = system_prompt_override or SYSTEM_PROMPT
    user_prompt = build_user_prompt(
        post_title=comment['post_title'],
        image_description=comment['image_analysis'],
        parent_chain_formatted=comment['parent_chain'] or '',
        author=comment['author'],
        author_trust=comment['author_trust_score'] or 0.5,
        comment_body=comment['body'],
        market_context=market_context_str,
    )
    return sys_prompt, user_prompt


def call_openai(system_prompt, user_prompt, model, temperature, max_tokens):
    """Make a direct OpenAI API call with configurable parameters."""
    import openai

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }
    return content, usage


def run_analysis(comment, config):
    """Run a single analysis with the given config. Returns parsed result + usage."""
    sys_prompt, user_prompt = build_prompts(
        comment, config['market_context'], config.get('system_prompt')
    )

    raw_content, usage = call_openai(
        sys_prompt, user_prompt,
        config['model'], config['temperature'], config['max_tokens']
    )

    parsed = parse_ai_response(raw_content)
    tickers, ticker_sentiments = normalize_tickers(
        parsed['tickers'], parsed['ticker_sentiments']
    )
    parsed['tickers'] = tickers
    parsed['ticker_sentiments'] = ticker_sentiments

    return parsed, usage


def format_comment_header(comment):
    """Format the comment info block."""
    trust = comment['author_trust_score'] or 0.5
    body = comment['body'].replace('\n', ' ')
    if len(body) > 200:
        body = body[:200] + "..."

    lines = [
        "=== COMMENT ===",
        f"reddit_id: {comment['reddit_id']}",
        f"Author: {comment['author']} (trust: {trust:.2f})",
        f"Post: \"{comment['post_title']}\"",
        f"Body: \"{body}\"",
    ]

    # Show existing analysis if present
    if comment.get('sentiment'):
        lines.append(f"Current DB: {comment['sentiment']} @ {comment['ai_confidence']} "
                      f"| sarcasm={bool(comment['sarcasm_detected'])} "
                      f"| reasoning={bool(comment['has_reasoning'])}")

    return "\n".join(lines)


def format_config(config):
    """Format the config block."""
    lines = [
        "=== CONFIG ===",
        f"Model: {config['model']} | Temp: {config['temperature']} | Max Tokens: {config['max_tokens']}",
    ]
    if config['market_context']:
        # Show first line of market context
        ctx_line = config['market_context'].split('\n')[0]
        lines.append(f"Market Context: {ctx_line}")
    else:
        lines.append("Market Context: disabled")
    return "\n".join(lines)


def format_result(parsed, usage):
    """Format a single analysis result."""
    tickers_str = ", ".join(
        f"{t}({s})" for t, s in zip(parsed['tickers'], parsed['ticker_sentiments'])
    ) or "none"

    cost = (usage['prompt_tokens'] * COST_PER_1M_INPUT +
            usage['completion_tokens'] * COST_PER_1M_OUTPUT) / 1_000_000

    lines = [
        "=== RESULT ===",
        f"Sentiment: {parsed['sentiment']} (confidence: {parsed['confidence']})",
        f"Tickers: {tickers_str}",
        f"Sarcasm: {'yes' if parsed['sarcasm_detected'] else 'no'} "
        f"| Reasoning: {'yes' if parsed['has_reasoning'] else 'no'}",
    ]
    if parsed.get('reasoning_summary'):
        summary = parsed['reasoning_summary']
        if len(summary) > 120:
            summary = summary[:120] + "..."
        lines.append(f"Summary: \"{summary}\"")
    lines.append(f"Tokens: {usage['prompt_tokens']} prompt / "
                 f"{usage['completion_tokens']} completion (${cost:.4f})")
    return "\n".join(lines)


def parse_config_string(config_str, base_market_context):
    """Parse a config string like 'temp=0.7,no-market-context' into a config dict."""
    config = {
        'model': DEFAULT_MODEL,
        'temperature': DEFAULT_TEMPERATURE,
        'max_tokens': DEFAULT_MAX_TOKENS,
        'market_context': base_market_context,
        'system_prompt': None,
    }

    for part in config_str.split(','):
        part = part.strip()
        if part == 'no-market-context':
            config['market_context'] = None
        elif '=' in part:
            key, _, value = part.partition('=')
            key = key.strip()
            value = value.strip()
            if key == 'temp':
                config['temperature'] = float(value)
            elif key == 'max-tokens':
                config['max_tokens'] = int(value)
            elif key == 'model':
                config['model'] = value
            elif key == 'system-prompt':
                with open(value) as f:
                    config['system_prompt'] = f.read()
            elif key == 'market-context':
                config['market_context'] = value.strip('"').strip("'")

    return config


def cmd_single(args):
    """Run a single analysis and display results."""
    comment = load_comment(args.db, args.reddit_id)
    market_ctx = get_market_context_string(args)

    config = {
        'model': args.model,
        'temperature': args.temperature,
        'max_tokens': args.max_tokens,
        'market_context': market_ctx,
        'system_prompt': None,
    }
    if args.system_prompt:
        with open(args.system_prompt) as f:
            config['system_prompt'] = f.read()
        config['system_prompt_file'] = args.system_prompt

    print(format_comment_header(comment))
    print()
    print(format_config(config))
    print()

    if args.dry_run:
        sys_prompt, user_prompt = build_prompts(
            comment, market_ctx, config.get('system_prompt')
        )
        print("=== SYSTEM PROMPT ===")
        print(sys_prompt)
        print()
        print("=== USER PROMPT ===")
        print(user_prompt)
        return

    parsed, usage = run_analysis(comment, config)
    print(format_result(parsed, usage))

    if not args.no_log:
        entry = build_log_entry(args.reddit_id, config, parsed, usage,
                                mode="single", tag=args.tag)
        append_log(args.log, entry)


def cmd_multi_run(args):
    """Run the same config N times and show consistency stats."""
    comment = load_comment(args.db, args.reddit_id)
    market_ctx = get_market_context_string(args)

    config = {
        'model': args.model,
        'temperature': args.temperature,
        'max_tokens': args.max_tokens,
        'market_context': market_ctx,
        'system_prompt': None,
    }
    if args.system_prompt:
        with open(args.system_prompt) as f:
            config['system_prompt'] = f.read()
        config['system_prompt_file'] = args.system_prompt

    print(format_comment_header(comment))
    print()
    print(format_config(config))
    print()
    print(f"=== {args.runs} RUNS ===")

    sentiments = []
    confidences = []
    total_cost = 0.0

    for i in range(args.runs):
        parsed, usage = run_analysis(comment, config)
        tickers_str = ", ".join(
            f"{t}({s})" for t, s in zip(parsed['tickers'], parsed['ticker_sentiments'])
        ) or "none"

        cost = (usage['prompt_tokens'] * COST_PER_1M_INPUT +
                usage['completion_tokens'] * COST_PER_1M_OUTPUT) / 1_000_000
        total_cost += cost

        sentiments.append(parsed['sentiment'])
        confidences.append(parsed['confidence'])

        if not args.no_log:
            entry = build_log_entry(args.reddit_id, config, parsed, usage,
                                    mode="multi", label=f"run-{i+1}", tag=args.tag)
            append_log(args.log, entry)

        print(f"Run {i+1}: {parsed['sentiment']:<8} @ {parsed['confidence']:<4} "
              f"| tickers: {tickers_str}")

    print()
    counts = Counter(sentiments)
    total = len(sentiments)
    consensus_parts = [f"{s} {c}/{total} ({c*100//total}%)" for s, c in counts.most_common()]
    print(f"Consensus: {' | '.join(consensus_parts)}")

    if len(confidences) > 1:
        print(f"Confidence: mean={statistics.mean(confidences):.2f}, "
              f"std={statistics.stdev(confidences):.2f}")
    else:
        print(f"Confidence: {confidences[0]:.2f}")

    print(f"Total cost: ${total_cost:.4f}")


def cmd_compare(args):
    """Compare two configs side-by-side on the same comment."""
    comment = load_comment(args.db, args.reddit_id)
    base_market_ctx = get_market_context_string(args)

    configs = []
    for cs in args.compare:
        configs.append(parse_config_string(cs, base_market_ctx))

    print(format_comment_header(comment))
    print()

    results = []
    for i, (cs, config) in enumerate(zip(args.compare, configs)):
        label = chr(65 + i)  # A, B, C...
        parsed, usage = run_analysis(comment, config)
        results.append((label, cs, config, parsed, usage))

        if not args.no_log:
            entry = build_log_entry(args.reddit_id, config, parsed, usage,
                                    mode="compare", label=label, tag=args.tag)
            append_log(args.log, entry)

    # Print side-by-side
    for label, cs, config, parsed, usage in results:
        tickers_str = ", ".join(
            f"{t}({s})" for t, s in zip(parsed['tickers'], parsed['ticker_sentiments'])
        ) or "none"

        cost = (usage['prompt_tokens'] * COST_PER_1M_INPUT +
                usage['completion_tokens'] * COST_PER_1M_OUTPUT) / 1_000_000

        print(f"=== CONFIG {label}: {cs} ===")
        print(f"Sentiment: {parsed['sentiment']} @ {parsed['confidence']}")
        print(f"Tickers: {tickers_str}")
        print(f"Sarcasm: {'yes' if parsed['sarcasm_detected'] else 'no'} "
              f"| Reasoning: {'yes' if parsed['has_reasoning'] else 'no'}")
        if parsed.get('reasoning_summary'):
            summary = parsed['reasoning_summary']
            if len(summary) > 120:
                summary = summary[:120] + "..."
            print(f"Summary: \"{summary}\"")
        print(f"Tokens: {usage['prompt_tokens']}+{usage['completion_tokens']} (${cost:.4f})")
        print()


def cmd_list_flips(args):
    """List sentiment flips between two databases."""
    if not args.db2:
        print("Error: --db2 required for --list-flips")
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("ATTACH DATABASE ? AS new_db", (args.db2,))

    rows = conn.execute("""
        SELECT
            o.reddit_id,
            REPLACE(SUBSTR(o.body, 1, 80), char(10), ' ') AS body_preview,
            o.sentiment AS old_sentiment,
            n.sentiment AS new_sentiment,
            o.ai_confidence AS old_confidence,
            n.ai_confidence AS new_confidence,
            ROUND(n.ai_confidence - o.ai_confidence, 2) AS conf_delta
        FROM main.comments o
        JOIN new_db.comments n ON o.reddit_id = n.reddit_id
        WHERE o.sentiment IS NOT NULL
          AND n.sentiment IS NOT NULL
          AND o.sentiment <> n.sentiment
        ORDER BY ABS(n.ai_confidence - o.ai_confidence) DESC
    """).fetchall()

    conn.close()

    if not rows:
        print("No sentiment flips found between the two databases.")
        return

    print(f"Sentiment flips: {len(rows)} comments (sorted by confidence delta)\n")
    print(f"{'reddit_id':<12} {'old->new':<20} {'Δconf':>6}  body")
    print("-" * 100)
    for row in rows:
        flip = f"{row['old_sentiment']}->{row['new_sentiment']}"
        delta = f"{row['conf_delta']:+.1f}" if row['conf_delta'] else " 0.0"
        print(f"{row['reddit_id']:<12} {flip:<20} {delta:>6}  {row['body_preview']}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prompt tuning workbench for WSB comment analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Config strings for --compare (comma-separated key=value pairs):
  temp=0.7                  Set temperature
  max-tokens=800            Set max tokens
  model=gpt-4o              Use different model
  no-market-context         Disable market context
  market-context="..."      Custom market context string
  system-prompt=file.txt    Load system prompt from file

Examples:
  %(prog)s o50n9bi --dry-run
  %(prog)s o50n9bi --temperature 0.7 --no-market-context
  %(prog)s o50n9bi --runs 5
  %(prog)s o50n9bi --compare "temp=0.3" "temp=0.7,no-market-context"
  %(prog)s --list-flips --db data/wsb_pre_update.db --db2 data/wsb.db
        """)

    parser.add_argument("reddit_id", nargs="?", help="Reddit comment ID to analyze")
    parser.add_argument("--db", default="data/wsb.db", help="Database path (default: data/wsb.db)")
    parser.add_argument("--db2", help="Second database for --list-flips comparison")

    # Analysis options
    parser.add_argument("--dry-run", action="store_true", help="Show prompt without calling API")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--no-market-context", action="store_true", help="Disable market context")
    parser.add_argument("--market-context", help="Custom market context string")
    parser.add_argument("--system-prompt", help="Path to custom system prompt file")

    # Logging
    parser.add_argument("--log", default=DEFAULT_LOG_PATH,
                        help=f"Log file path (default: {DEFAULT_LOG_PATH})")
    parser.add_argument("--no-log", action="store_true", help="Disable auto-logging")
    parser.add_argument("--tag", help="Label for this experiment (e.g. 'market-context-bias')")

    # Modes
    parser.add_argument("--runs", type=int, help="Run N times and show consistency stats")
    parser.add_argument("--compare", nargs="+", metavar="CONFIG",
                        help="Compare configs side-by-side (e.g. 'temp=0.3' 'temp=0.7,no-market-context')")
    parser.add_argument("--list-flips", action="store_true",
                        help="List sentiment flips between --db and --db2")
    parser.add_argument("--verbose", action="store_true", help="Show full prompts")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.list_flips:
        cmd_list_flips(args)
        return

    if not args.reddit_id:
        print("Error: reddit_id required (or use --list-flips)")
        sys.exit(1)

    if args.compare:
        cmd_compare(args)
    elif args.runs and args.runs > 1:
        cmd_multi_run(args)
    else:
        cmd_single(args)


if __name__ == "__main__":
    main()
