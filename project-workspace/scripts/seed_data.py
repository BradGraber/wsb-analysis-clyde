#!/usr/bin/env python3
"""
WSB Analysis Tool - Development Seed Data Script
Generates realistic mock data for frontend development.
Idempotent: safe to run multiple times (uses INSERT OR IGNORE).
"""

import sqlite3
import os
import random
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

# Default database path (configurable via DB_PATH env var)
DEFAULT_DB_PATH = "./data/wsb.db"


def get_db_path():
    """Get database path from environment or use default."""
    return os.environ.get("DB_PATH", DEFAULT_DB_PATH)


def connect_db(db_path):
    """Connect to SQLite database with foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def seed_authors(conn):
    """Create 5+ authors with varied trust scores."""
    authors_data = [
        ("DeepValueHunter", "2025-11-15 10:00:00", 150, 95, 0.82, 0.68, 4520, 2, "2026-02-08 14:30:00"),
        ("OptionsYOLO", "2025-12-01 08:00:00", 220, 120, 0.75, 0.55, 6800, 8, "2026-02-09 16:45:00"),
        ("TechStockBull", "2026-01-05 12:00:00", 85, 70, 0.88, 0.72, 2100, 0, "2026-02-09 11:20:00"),
        ("DiamondHandsDan", "2025-10-20 09:00:00", 310, 180, 0.70, 0.62, 9500, 12, "2026-02-07 18:00:00"),
        ("QuietAnalyst", "2026-01-20 15:00:00", 42, 38, 0.92, None, 850, 0, "2026-02-09 09:15:00"),
        ("MemeStonkKing", "2025-11-28 11:00:00", 180, 85, 0.65, 0.48, 7200, 20, "2026-02-08 13:00:00"),
    ]

    cursor = conn.cursor()
    for username, first_seen, total, high_q, avg_conv, avg_acc, upvotes, flagged, last_active in authors_data:
        cursor.execute("""
            INSERT OR IGNORE INTO authors
            (username, first_seen, total_comments, high_quality_comments, avg_conviction_score,
             avg_sentiment_accuracy, total_upvotes, flagged_comments, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, first_seen, total, high_q, avg_conv, avg_acc, upvotes, flagged, last_active))

    conn.commit()
    return len(authors_data)


def seed_analysis_runs(conn):
    """Create 3 analysis runs: completed, failed, running."""
    runs_data = [
        # Completed run from 2 days ago
        ("completed", 7, "7b. Evaluation Periods", 10, 10,
         (datetime.now() - timedelta(days=2, hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
         (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
         None, 12, 8, 3, '[]'),
        # Failed run from yesterday
        ("failed", 3, "3. Analysis", 485, 1000,
         (datetime.now() - timedelta(days=1, hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
         (datetime.now() - timedelta(days=1, hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
         "OpenAI API rate limit exceeded", 0, 0, 0, '["openai_rate_limit"]'),
        # Running (in progress)
        ("running", 5, "5. Position Management", 8, 12,
         (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"),
         None, None, 10, 7, 0, '["market_hours_skipped"]'),
    ]

    cursor = conn.cursor()
    for status, phase, label, curr, total, started, completed, error, signals, positions, exits, warnings in runs_data:
        cursor.execute("""
            INSERT OR IGNORE INTO analysis_runs
            (status, current_phase, current_phase_label, progress_current, progress_total,
             started_at, completed_at, error_message, signals_created, positions_opened, exits_triggered, warnings)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (status, phase, label, curr, total, started, completed, error, signals, positions, exits, warnings))

    conn.commit()
    # Return the IDs we just created
    cursor.execute("SELECT id FROM analysis_runs ORDER BY id")
    return [row[0] for row in cursor.fetchall()]


def seed_reddit_posts(conn):
    """Create 5+ reddit posts."""
    posts_data = [
        ("abc123xyz", "NVDA earnings thread - what are your plays?",
         "NVDA reports after hours tomorrow. Share your positions and predictions.",
         2850, 450, None, None, (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")),
        ("def456uvw", "GME is back baby! 🚀🚀🚀",
         "Volume is insane today. Someone knows something.",
         5200, 820, None, None, (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")),
        ("ghi789rst", "TSLA call holders, how we feeling?",
         "Holding 10x $250c 2/14. Down 30% but Elon tweet incoming I can feel it.",
         1200, 380, None, None, (datetime.now() - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")),
        ("jkl012opq", "AMD crushing Intel, time to load up?",
         "Market share gains across the board. This could run to $200.",
         980, 210, None, None, (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")),
        ("mno345lmn", "Daily Discussion Thread",
         "What are your moves tomorrow?",
         4500, 1200, None, None, (datetime.now() - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")),
    ]

    cursor = conn.cursor()
    for reddit_id, title, selftext, upvotes, comments, img_url, img_analysis, fetched in posts_data:
        cursor.execute("""
            INSERT OR IGNORE INTO reddit_posts
            (reddit_id, title, selftext, upvotes, total_comments, image_urls, image_analysis, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (reddit_id, title, selftext, upvotes, comments, img_url, img_analysis, fetched))

    conn.commit()
    cursor.execute("SELECT id FROM reddit_posts ORDER BY id")
    return [row[0] for row in cursor.fetchall()]


def seed_signals(conn):
    """Create 12+ signals with varied tickers and types."""
    today = date.today()
    signals_data = [
        # Quality signals
        (today - timedelta(days=3), "NVDA", "quality", 0.85, "bullish", 0.82, 8, True, False, 2, 4, False),
        (today - timedelta(days=2), "AAPL", "quality", 0.78, "bullish", 0.75, 5, True, False, 1, 3, True),
        (today - timedelta(days=2), "GME", "quality", 0.72, "bullish", 0.68, 12, True, True, 0, 8, True),
        (today - timedelta(days=1), "TSLA", "quality", 0.65, "bullish", 0.62, 6, True, False, 5, 4, True),
        (today - timedelta(days=1), "AMD", "quality", 0.88, "bullish", 0.85, 7, True, False, 3, 5, False),
        (today, "PLTR", "quality", 0.70, "bullish", 0.68, 4, True, False, 8, 2, False),
        # Consensus signals
        (today - timedelta(days=3), "NVDA", "consensus", 0.82, "bullish", 0.78, 35, False, False, 2, 12, False),
        (today - timedelta(days=2), "GME", "consensus", 0.75, "bullish", 0.72, 48, False, True, 0, 18, True),
        (today - timedelta(days=1), "SOFI", "consensus", 0.68, "bullish", 0.65, 32, False, False, 15, 10, True),
        (today - timedelta(days=1), "AMC", "consensus", 0.62, "bullish", 0.58, 40, False, False, 8, 14, False),
        (today, "NVDA", "consensus", 0.80, "bullish", 0.77, 42, False, False, 2, 15, False),
        (today, "AAPL", "consensus", 0.55, "bearish", 0.52, 30, False, False, 1, 9, False),
    ]

    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for signal_date, ticker, sig_type, sentiment_score, prediction, confidence, \
        comment_count, has_reasoning, is_emergence, prior_mentions, users, pos_opened in signals_data:
        cursor.execute("""
            INSERT OR IGNORE INTO signals
            (signal_date, created_at, updated_at, ticker, signal_type, sentiment_score, prediction,
             confidence, comment_count, has_reasoning, is_emergence, prior_7d_mentions,
             distinct_users, position_opened)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (signal_date.strftime("%Y-%m-%d"), now, now, ticker, sig_type, sentiment_score,
              prediction, confidence, comment_count, has_reasoning, is_emergence,
              prior_mentions, users, pos_opened))

    conn.commit()
    cursor.execute("SELECT id, ticker, signal_type FROM signals ORDER BY id")
    return cursor.fetchall()


def seed_positions(conn, signal_ids):
    """Create 10+ positions: mix of open/closed, stock/option, across portfolios."""
    cursor = conn.cursor()

    # Get portfolio IDs
    cursor.execute("SELECT id, instrument_type, signal_type FROM portfolios ORDER BY id")
    portfolios = cursor.fetchall()

    if not portfolios:
        print("WARNING: No portfolios found. Run schema.sql and seed.sql first.")
        return 0

    today = date.today()
    positions_data = [
        # Stocks Quality Portfolio - Mix of open and closed
        (portfolios[0][0], signal_ids[0][0], "NVDA", "stock", "quality", "long", 0.82, 5000.0,
         today - timedelta(days=3), 485.50, "closed", 10, 0, 485.50, 534.05, 534.05, False, None,
         None, None, None, None, None, None, None, None,
         today - timedelta(days=1), "take_profit", 2, 10.0),

        (portfolios[0][0], signal_ids[1][0], "AAPL", "stock", "quality", "long", 0.75, 4000.0,
         today - timedelta(days=2), 188.20, "open", 21, 21, 169.38, 193.61, 195.40, False, None,
         None, None, None, None, None, None, None, None,
         None, None, None, None),

        (portfolios[0][0], signal_ids[4][0], "AMD", "stock", "quality", "long", 0.85, 5500.0,
         today - timedelta(days=1), 142.80, "open", 38, 38, 128.52, 164.22, 148.50, True, None,
         None, None, None, None, None, None, None, None,
         None, None, None, None),

        # Stocks Consensus Portfolio
        (portfolios[1][0], signal_ids[7][0], "GME", "stock", "consensus", "long", 0.72, 3500.0,
         today - timedelta(days=2), 24.80, "closed", 141, 0, 22.32, 27.28, 27.28, False, None,
         None, None, None, None, None, None, None, None,
         today - timedelta(days=1), "stop_loss", 1, -10.0),

        (portfolios[1][0], signal_ids[8][0], "SOFI", "stock", "consensus", "long", 0.65, 4200.0,
         today - timedelta(days=1), 12.50, "open", 336, 336, 11.25, 14.38, 13.20, False, None,
         None, None, None, None, None, None, None, None,
         None, None, None, None),

        # Options Quality Portfolio
        (portfolios[2][0], signal_ids[1][0], "AAPL", "option", "quality", "long", 0.75, 2000.0,
         today - timedelta(days=2), 8.50, "open", None, None, None, None, None, None, None,
         "call", 195.0, today + timedelta(days=12), 2, 2, 850.0, 1100.0, 188.20,
         None, None, None, None),

        (portfolios[2][0], signal_ids[3][0], "TSLA", "option", "quality", "long", 0.62, 2000.0,
         today - timedelta(days=1), 6.20, "closed", None, None, None, None, None, None, None,
         "call", 255.0, today + timedelta(days=13), 3, 0, 620.0, 1240.0, 248.30,
         today, "take_profit", 1, 100.0),

        (portfolios[2][0], signal_ids[4][0], "AMD", "option", "quality", "long", 0.85, 2000.0,
         today - timedelta(days=1), 4.80, "open", None, None, None, None, None, None, None,
         "call", 150.0, today + timedelta(days=14), 4, 4, 480.0, 680.0, 142.80,
         None, None, None, None),

        # Options Consensus Portfolio
        (portfolios[3][0], signal_ids[7][0], "GME", "option", "consensus", "long", 0.72, 2000.0,
         today - timedelta(days=2), 3.50, "closed", None, None, None, None, None, None, None,
         "call", 26.0, today + timedelta(days=11), 5, 0, 350.0, 350.0, 24.80,
         today - timedelta(days=1), "stop_loss", 1, -50.0),

        (portfolios[3][0], signal_ids[8][0], "SOFI", "option", "consensus", "long", 0.65, 2000.0,
         today - timedelta(days=1), 1.20, "open", None, None, None, None, None, None, None,
         "call", 13.5, today + timedelta(days=15), 16, 16, 120.0, 180.0, 12.50,
         None, None, None, None),
    ]

    count = 0
    for pos_data in positions_data:
        (port_id, sig_id, ticker, inst_type, sig_type, direction, confidence, pos_size,
         entry_date, entry_price, status, shares, shares_rem, stop_loss, take_profit, peak_price,
         trailing_active, time_ext, opt_type, strike, expiration, contracts, contracts_rem,
         premium_paid, peak_premium, underlying_entry, exit_date, exit_reason, hold_days, ret_pct) = pos_data

        cursor.execute("""
            INSERT OR IGNORE INTO positions
            (portfolio_id, signal_id, ticker, instrument_type, signal_type, direction, confidence,
             position_size, entry_date, entry_price, status, shares, shares_remaining,
             stop_loss_price, take_profit_price, peak_price, trailing_stop_active, time_extension,
             option_type, strike_price, expiration_date, contracts, contracts_remaining,
             premium_paid, peak_premium, underlying_price_at_entry, exit_date, exit_reason, hold_days, realized_return_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (port_id, sig_id, ticker, inst_type, sig_type, direction, confidence, pos_size,
              entry_date.strftime("%Y-%m-%d"), entry_price, status, shares, shares_rem, stop_loss,
              take_profit, peak_price, trailing_active, time_ext, opt_type, strike,
              expiration.strftime("%Y-%m-%d") if expiration else None, contracts, contracts_rem,
              premium_paid, peak_premium, underlying_entry,
              exit_date.strftime("%Y-%m-%d") if exit_date else None, exit_reason, hold_days, ret_pct))
        count += 1

    conn.commit()
    cursor.execute("SELECT id, status FROM positions WHERE status = 'closed' ORDER BY id")
    return cursor.fetchall()


def seed_position_exits(conn, closed_positions):
    """Create position_exits for closed positions with 4+ exit reason types."""
    exits_data = [
        # Position 1: NVDA stock - take_profit (partial exit 50%)
        (closed_positions[0][0], date.today() - timedelta(days=1), 534.05, "take_profit", 0.50, 5, None, 242.75),
        # Position 1: NVDA stock - trailing_stop (remaining 50%)
        (closed_positions[0][0], date.today() - timedelta(days=1), 534.05, "trailing_stop", 0.50, 5, None, 242.75),

        # Position 2: GME stock - stop_loss (full 100%)
        (closed_positions[1][0], date.today() - timedelta(days=1), 22.32, "stop_loss", 1.0, 141, None, -350.00),

        # Position 3: TSLA option - take_profit (partial 50%)
        (closed_positions[2][0], date.today(), 12.40, "take_profit", 0.50, None, 2, 620.00),
        # Position 3: TSLA option - trailing_stop (remaining 50%)
        (closed_positions[2][0], date.today(), 11.80, "trailing_stop", 0.50, None, 1, 560.00),

        # Position 4: GME option - manual_close (full 100%)
        (closed_positions[3][0], date.today() - timedelta(days=1), 1.75, "manual_close", 1.0, None, 5, -875.00),
    ]

    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for pos_id, exit_date, exit_price, exit_reason, qty_pct, shares_exit, contracts_exit, pnl in exits_data:
        cursor.execute("""
            INSERT OR IGNORE INTO position_exits
            (position_id, exit_date, exit_price, exit_reason, quantity_pct, shares_exited,
             contracts_exited, realized_pnl, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (pos_id, exit_date.strftime("%Y-%m-%d"), exit_price, exit_reason, qty_pct,
              shares_exit, contracts_exit, pnl, now))

    conn.commit()
    return len(exits_data)


def seed_comments(conn, run_ids, post_ids):
    """Create 10+ comments with AI annotation fields."""
    if not run_ids or not post_ids:
        print("WARNING: No analysis runs or posts found.")
        return []

    # Use first completed run
    run_id = run_ids[0]
    today = datetime.now()

    comments_data = [
        (run_id, post_ids[0], "com001nvda", "DeepValueHunter",
         "NVDA calls are the move. $500c 2/14 looking juicy. Data center demand is insane.",
         (today - timedelta(days=2, hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
         145, None, 0, 0.85, "bullish", False, True,
         "Strong conviction based on data center demand fundamentals", 0.82, 0.82),

        (run_id, post_ids[0], "com002nvda", "OptionsYOLO",
         "I'm all in on NVDA. This is going to 600 by end of month. 🚀🚀🚀",
         (today - timedelta(days=2, hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
         89, None, 0, 0.78, "bullish", False, False, None, 0.72, 0.75),

        (run_id, post_ids[1], "com003gme", "DiamondHandsDan",
         "GME volume is crazy. Someone knows something. Loading up on shares.",
         (today - timedelta(days=1, hours=12)).strftime("%Y-%m-%d %H:%M:%S"),
         210, None, 0, 0.92, "bullish", False, True,
         "Unusual volume spike suggests institutional accumulation", 0.88, 0.70),

        (run_id, post_ids[1], "com004gme", "MemeStonkKing",
         "GME to the moon! Buy buy buy! Diamond hands! 💎🙌",
         (today - timedelta(days=1, hours=11)).strftime("%Y-%m-%d %H:%M:%S"),
         95, None, 0, 0.65, "bullish", False, False, None, 0.55, 0.65),

        (run_id, post_ids[2], "com005tsla", "TechStockBull",
         "TSLA $250 calls expiring Friday. Elon's tweet will save us, right? Right??",
         (today - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
         45, None, 0, 0.42, "bullish", True, False, None, 0.35, 0.88),

        (run_id, post_ids[2], "com006tsla", "QuietAnalyst",
         "TSLA fundamentals support a move to $280. Q4 deliveries exceeded expectations.",
         (today - timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S"),
         120, None, 0, 0.88, "bullish", False, True,
         "Q4 delivery numbers and margin expansion provide upside catalyst", 0.85, 0.92),

        (run_id, post_ids[3], "com007amd", "DeepValueHunter",
         "AMD taking Intel's lunch money. Market share gains across data center and consumer. $180 PT.",
         (today - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
         165, None, 0, 0.90, "bullish", False, True,
         "Market share gains in data center and consumer segments support upside", 0.88, 0.82),

        (run_id, post_ids[3], "com008amd", "TechStockBull",
         "AMD chips in every new AI server. This is just getting started.",
         (today - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"),
         78, None, 0, 0.82, "bullish", False, True,
         "AI server adoption accelerating, AMD positioned to benefit", 0.80, 0.88),

        (run_id, post_ids[4], "com009aapl", "OptionsYOLO",
         "AAPL $195c printing tomorrow. Vision Pro launch is priced in? Nah.",
         (today - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S"),
         52, None, 0, 0.68, "bullish", False, False, None, 0.65, 0.75),

        (run_id, post_ids[4], "com010sofi", "QuietAnalyst",
         "SOFI has real potential here. Banking charter + student loan restart = revenue growth.",
         (today - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
         92, None, 0, 0.78, "bullish", False, True,
         "Banking charter and student loan restart provide fundamental catalysts", 0.75, 0.92),
    ]

    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for comment_data in comments_data:
        (run_id, post_id, reddit_id, author, body, created, score, parent_id, depth,
         prior_score, sentiment, sarcasm, has_reasoning, reasoning, ai_conf, trust_score) = comment_data

        cursor.execute("""
            INSERT OR IGNORE INTO comments
            (analysis_run_id, post_id, reddit_id, author, body, created_utc, score,
             parent_comment_id, depth, prioritization_score, sentiment, sarcasm_detected,
             has_reasoning, reasoning_summary, ai_confidence, author_trust_score, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, post_id, reddit_id, author, body, created, score, parent_id, depth,
              prior_score, sentiment, sarcasm, has_reasoning, reasoning, ai_conf, trust_score, now))

    conn.commit()
    cursor.execute("SELECT id, reddit_id FROM comments ORDER BY id")
    return cursor.fetchall()


def seed_signal_comments(conn, signal_ids, comment_ids):
    """Create signal_comments junction records."""
    if not signal_ids or not comment_ids:
        return 0

    # Map comments to signals by ticker
    comment_ticker_map = {
        "com001nvda": "NVDA",
        "com002nvda": "NVDA",
        "com003gme": "GME",
        "com004gme": "GME",
        "com005tsla": "TSLA",
        "com006tsla": "TSLA",
        "com007amd": "AMD",
        "com008amd": "AMD",
        "com009aapl": "AAPL",
        "com010sofi": "SOFI",
    }

    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0

    for comment_id, reddit_id in comment_ids:
        ticker = comment_ticker_map.get(reddit_id)
        if not ticker:
            continue

        # Find matching signals for this ticker (both quality and consensus)
        for signal_id, sig_ticker, sig_type in signal_ids:
            if sig_ticker == ticker:
                cursor.execute("""
                    INSERT OR IGNORE INTO signal_comments
                    (signal_id, comment_id, created_at)
                    VALUES (?, ?, ?)
                """, (signal_id, comment_id, now))
                count += 1

    conn.commit()
    return count


def seed_comment_tickers(conn, comment_ids):
    """Create comment_tickers junction records."""
    if not comment_ids:
        return 0

    comment_ticker_map = {
        "com001nvda": [("NVDA", "bullish")],
        "com002nvda": [("NVDA", "bullish")],
        "com003gme": [("GME", "bullish")],
        "com004gme": [("GME", "bullish")],
        "com005tsla": [("TSLA", "bullish")],
        "com006tsla": [("TSLA", "bullish")],
        "com007amd": [("AMD", "bullish"), ("INTC", "bearish")],
        "com008amd": [("AMD", "bullish")],
        "com009aapl": [("AAPL", "bullish")],
        "com010sofi": [("SOFI", "bullish")],
    }

    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0

    for comment_id, reddit_id in comment_ids:
        tickers_data = comment_ticker_map.get(reddit_id, [])
        for ticker, sentiment in tickers_data:
            cursor.execute("""
                INSERT OR IGNORE INTO comment_tickers
                (comment_id, ticker, sentiment, created_at)
                VALUES (?, ?, ?, ?)
            """, (comment_id, ticker, sentiment, now))
            count += 1

    conn.commit()
    return count


def seed_evaluation_periods(conn):
    """Create 1 evaluation period per portfolio (mix of active/completed)."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, instrument_type, signal_type FROM portfolios ORDER BY id")
    portfolios = cursor.fetchall()

    if not portfolios:
        return 0

    today = date.today()
    period_start = today - timedelta(days=15)
    period_end = today + timedelta(days=15)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    periods_data = [
        # Stocks Quality - active
        (portfolios[0][0], period_start, period_end, "stock", "quality", "active",
         None, None, None, None, 0, 0, 0, None, None, 100000.0),
        # Stocks Consensus - active
        (portfolios[1][0], period_start, period_end, "stock", "consensus", "active",
         None, None, None, None, 0, 0, 0, None, None, 100000.0),
        # Options Quality - active
        (portfolios[2][0], period_start, period_end, "option", "quality", "active",
         None, None, None, None, 0, 0, 0, None, None, 100000.0),
        # Options Consensus - completed
        (portfolios[3][0], today - timedelta(days=45), today - timedelta(days=15),
         "option", "consensus", "completed", 2.5, 3.2, -0.7, False,
         5, 3, 2, 1.25, 60.0, 100000.0),
    ]

    count = 0
    for period_data in periods_data:
        (port_id, start, end, inst_type, sig_type, status, port_ret, sp_ret, rel_perf,
         beat_bench, total_pos, win_pos, lose_pos, avg_ret, accuracy, val_start) = period_data

        cursor.execute("""
            INSERT OR IGNORE INTO evaluation_periods
            (portfolio_id, period_start, period_end, instrument_type, signal_type, status,
             portfolio_return_pct, sp500_return_pct, relative_performance, beat_benchmark,
             total_positions_closed, winning_positions, losing_positions, avg_return_pct,
             signal_accuracy_pct, value_at_period_start, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (port_id, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), inst_type, sig_type,
              status, port_ret, sp_ret, rel_perf, beat_bench, total_pos, win_pos, lose_pos,
              avg_ret, accuracy, val_start, now))
        count += 1

    conn.commit()
    return count


def seed_price_history(conn):
    """Create 14+ days of price history per ticker for sparklines."""
    tickers_data = {
        "AAPL": 188.20,
        "GME": 24.80,
        "TSLA": 248.30,
        "NVDA": 485.50,
        "AMD": 142.80,
        "PLTR": 28.40,
        "SOFI": 12.50,
        "AMC": 8.60,
    }

    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0

    for ticker, base_price in tickers_data.items():
        for i in range(14, -1, -1):  # 15 days of history (14 days ago to today)
            price_date = date.today() - timedelta(days=i)

            # Generate realistic daily variation
            daily_var = random.uniform(-0.03, 0.03)  # +/- 3% daily
            close_price = base_price * (1 + daily_var * (14 - i) / 14)  # Trend toward base_price
            open_price = close_price * (1 + random.uniform(-0.01, 0.01))
            high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.02))
            low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.02))

            cursor.execute("""
                INSERT OR IGNORE INTO price_history
                (ticker, date, open, high, low, close, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ticker, price_date.strftime("%Y-%m-%d"),
                  round(open_price, 2), round(high_price, 2),
                  round(low_price, 2), round(close_price, 2), now))
            count += 1

    conn.commit()
    return count


def main():
    """Main execution function."""
    db_path = get_db_path()

    print(f"WSB Analysis Tool - Seed Data Script")
    print(f"Database: {db_path}")
    print("-" * 60)

    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = connect_db(db_path)

        # Seed all tables
        print("Seeding authors...", end=" ")
        author_count = seed_authors(conn)
        print(f"{author_count} authors created")

        print("Seeding analysis runs...", end=" ")
        run_ids = seed_analysis_runs(conn)
        print(f"{len(run_ids)} runs created")

        print("Seeding reddit posts...", end=" ")
        post_ids = seed_reddit_posts(conn)
        print(f"{len(post_ids)} posts created")

        print("Seeding signals...", end=" ")
        signal_ids = seed_signals(conn)
        print(f"{len(signal_ids)} signals created")

        print("Seeding positions...", end=" ")
        closed_positions = seed_positions(conn, signal_ids)
        print(f"{closed_positions} positions created")

        print("Seeding position exits...", end=" ")
        exit_count = seed_position_exits(conn, closed_positions)
        print(f"{exit_count} exits created")

        print("Seeding comments...", end=" ")
        comment_ids = seed_comments(conn, run_ids, post_ids)
        print(f"{len(comment_ids)} comments created")

        print("Seeding signal_comments junctions...", end=" ")
        sig_com_count = seed_signal_comments(conn, signal_ids, comment_ids)
        print(f"{sig_com_count} links created")

        print("Seeding comment_tickers junctions...", end=" ")
        com_tick_count = seed_comment_tickers(conn, comment_ids)
        print(f"{com_tick_count} links created")

        print("Seeding evaluation periods...", end=" ")
        eval_count = seed_evaluation_periods(conn)
        print(f"{eval_count} periods created")

        print("Seeding price history...", end=" ")
        price_count = seed_price_history(conn)
        print(f"{price_count} price records created")

        conn.close()

        print("-" * 60)
        print("Seed data creation complete!")
        print("\nSummary:")
        print(f"  Authors: {author_count}")
        print(f"  Analysis Runs: {len(run_ids)}")
        print(f"  Reddit Posts: {len(post_ids)}")
        print(f"  Signals: {len(signal_ids)}")
        print(f"  Positions: {len(closed_positions)}")
        print(f"  Position Exits: {exit_count}")
        print(f"  Comments: {len(comment_ids)}")
        print(f"  Signal-Comment Links: {sig_com_count}")
        print(f"  Comment-Ticker Links: {com_tick_count}")
        print(f"  Evaluation Periods: {eval_count}")
        print(f"  Price History Records: {price_count}")

        return 0

    except sqlite3.Error as e:
        print(f"\nERROR: Database error: {e}")
        return 1
    except Exception as e:
        print(f"\nERROR: Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
