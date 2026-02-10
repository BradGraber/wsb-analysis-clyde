# Product Requirements Document
## WSB Analysis Tool

**Version:** 3.6 (Plato ART Round 1 Amendments)
**Date:** 2026-02-07
**Status:** Implementation Ready
**ART Workflow ID:** art-wsb-analysis-20260116
**Consolidation:** Merges PRD v2.4 + 37 Phase 1 amendments + 28 Phase 2 decisions + 43 Phase 3b re-validation amendments + 34 Phase 3c second re-validation amendments + 15 Plato ART Round 1 amendments into single authoritative document

---

## Executive Summary

A personal analytical tool that processes WallStreetBets subreddit comments to identify emerging market trends and sentiment patterns, creating actionable trading data for individual swing trading decisions.

**Core hypotheses under test:**
1. **Quality signals** — Substantive arguments by multiple users predict market movement
2. **Consensus signals** — High volume of aligned sentiment predicts market movement

**Success metric:** Either signal type beats the S&P 500 by 10% over 30-day evaluation periods.

**This is explicitly an experiment** — the project tests whether these hypotheses are valid, not assumes them.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Stakeholder Analysis](#2-stakeholder-analysis)
3. [System Architecture](#3-system-architecture)
   - 3.1 [System Overview](#31-system-overview)
   - 3.2 [FastAPI Backend Architecture](#32-fastapi-backend-architecture)
   - 3.3 [Data Model Architecture](#33-data-model-architecture)
   - 3.4 [REST API Design](#34-rest-api-design)
   - 3.5 [Vue Dashboard Architecture](#35-vue-dashboard-architecture)
   - 3.6 [Integration Patterns](#36-integration-patterns)
4. [Functional Requirements](#4-functional-requirements)
5. [Non-Functional Requirements](#5-non-functional-requirements)
6. [Technical Stack](#6-technical-stack)
7. [Success Criteria](#7-success-criteria)
8. [Constraints and Assumptions](#8-constraints-and-assumptions)
9. [Out of Scope](#9-out-of-scope)
10. [Traceability](#10-traceability)
11. [Appendix A: FastAPI Reddit Integration Capabilities](#appendix-a-fastapi-reddit-integration-capabilities)
12. [Appendix B: SQLite Schema](#appendix-b-sqlite-schema)
13. [Appendix C: REST API Contract](#appendix-c-rest-api-contract)
14. [Appendix D: Internal Data Format](#appendix-d-internal-data-format)
15. [Appendix E: AI Analysis Specification](#appendix-e-ai-analysis-specification)
16. [Appendix F: Author Trust Calculation](#appendix-f-author-trust-calculation)

---

## 1. Project Overview

### 1.1 Problem Statement

Individual traders lack the capacity to systematically process the volume of WSB commentary at scale. The problem involves:
- Overwhelming volume of unstructured social commentary
- Difficulty extracting signal from noise (sarcasm, memes)
- Gap between available tools and WSB's unique predictive signals

### 1.2 Solution

An end-to-end pipeline that:
1. Acquires prioritized WSB comments (FastAPI with PRAW)
2. Analyzes sentiment using AI that understands WSB communication style
3. Detects trading signals via Quality (substantive reasoning) and Consensus (volume alignment) methods
4. Presents actionable signals via web dashboard
5. Validates predictions against actual market performance

### 1.3 Project Characteristics

| Attribute | Value |
|-----------|-------|
| Size | Small |
| Criticality | Low (experimental) |
| Complexity | Medium |
| Scope | Narrow (WSB only) |
| Users | Single user |
| Trading Style | Swing trading (3-10 days) |

---

## 2. Stakeholder Analysis

### 2.1 Primary User

**Role:** Individual trader (project originator)
**Goals:**
- Identify market trends that predict performance
- Make money trading on WSB-derived insights
- Eliminate manual data sorting

**Consumption Pattern:**
- On-demand usage, <3 times daily
- Desktop-focused analysis sessions
- No mobile or alerting requirements

---

## 3. System Architecture

### 3.1 System Overview

The WSB Analysis Tool uses a **three-tier architecture** consisting of a FastAPI backend (data acquisition and processing), SQLite database (persistent storage), and Vue.js dashboard (visualization and user interaction). The backend orchestrates all external API calls and business logic, while the frontend provides on-demand visualization of processed signals and portfolio state.

```
┌─────────────────┐     ┌─────────────────────────────────┐     ┌─────────────────┐
│                 │     │                                 │     │                 │
│  Vue Dashboard  │────▶│    FastAPI Backend              │◀───▶│     SQLite      │
│  (Visualization)│ REST│    (Reddit + AI + Analysis)     │ SQL │   (Storage)     │
│                 │     │                                 │     │                 │
└─────────────────┘     └─────────────────────────────────┘     └─────────────────┘
                                        │
                        ┌───────────────┼───────────────┬──────────────────┐
                        │               │               │                  │
                   Reddit API      OpenAI API      Schwab API        yfinance API
                   (PRAW)         GPT-4o-mini    (real-time prices   (historical
                                  (+ vision)      + options)          + benchmark)
```

**External Dependencies:**
- **Reddit API** (via PRAW): Source of WSB posts and comments
- **OpenAI API** (GPT-4o-mini): Sentiment analysis, sarcasm detection, image analysis
- **Schwab API** (access confirmed): Primary source for real-time stock quotes, intraday price data, options chains with greeks, and options premiums. Requires OAuth 2.0 authentication.
- **yfinance API**: Historical stock price data for S&P 500 benchmark comparison (evaluation periods), historical price lookbacks, and price sparkline data. Not used for real-time monitoring or options data.

**Architecture Characteristics:**
- **Stateless backend**: No session caching; each request is independent
- **On-demand execution**: User triggers analysis manually (~3x daily)
- **Single-user design**: No authentication or multi-tenancy
- **Local-first deployment**: All components run locally (Phase 1)

---

### 3.2 FastAPI Backend Architecture

The FastAPI backend is the system's core processing engine, responsible for data acquisition, AI-powered analysis, signal detection, and paper trading position management. This section describes the backend's internal architecture and request processing flow.

#### 3.2.1 Subsystem Responsibilities

The backend is organized into eight major subsystems, each with clear responsibilities and dependencies:

| Subsystem | Responsibility | Key Dependencies |
|-----------|----------------|------------------|
| **Reddit Acquisition** | Authenticate via PRAW OAuth2, fetch top 10 "hot" posts from r/wallstreetbets, retrieve up to 1000 comments per post, build parent chain context for threaded discussions | PRAW library, Reddit API |
| **Image Analysis** | Detect post images (i.redd.it, imgur, preview.redd.it), analyze via GPT-4o-mini vision API to extract charts/data/tickers, provide visual context for comment analysis | OpenAI vision API |
| **Comment Prioritization** | Score comments using financial keyword density, author historical trust score, engagement metrics (upvotes, replies), thread depth penalty; select top 50 comments per post (~500 total) | SQLite (authors table) |
| **AI Sentiment Analysis** | Analyze each comment individually via GPT-4o-mini, extract tickers mentioned, detect sarcasm and reasoning presence, classify sentiment (bullish/bearish/neutral), assign confidence score | OpenAI GPT-4o-mini API |
| **Signal Detection** | Group comments by ticker and calendar day, calculate Quality signal metrics (users with reasoning + alignment), calculate Consensus signal metrics (volume + user count + alignment), check thresholds from system_config, compute signal confidence, detect emergence (cold → hot tickers), upsert signals to database | SQLite (signals, system_config, comments tables) |
| **Position Management** | Evaluate signals meeting threshold, check portfolio position limits (max 10/portfolio), calculate confidence-weighted position sizes, open positions in 2 portfolios (stock + option) per signal, implement replacement logic when at capacity, track position lifecycle | SQLite (portfolios, positions tables) |
| **Price Monitoring** | Fetch real-time stock quotes and intraday high/low via Schwab API, fetch current options premiums and greeks via Schwab API, check exit conditions against both current price and intraday range since last check, execute exits and update position records | Schwab API (primary), yfinance API (historical/benchmark only) |
| **Author Trust Tracker** | Update historical author metrics after each analysis run (total_comments, high_quality_comments, total_upvotes, avg_conviction_score), update after position outcomes are known (avg_sentiment_accuracy), maintain first_seen and last_active timestamps | SQLite (authors table) |

#### 3.2.2 Request Flow: POST /analyze

The `/analyze` endpoint orchestrates the entire analysis pipeline, from data acquisition through position monitoring. Processing occurs in seven sequential phases:

**Phase 1: Acquisition**
1. Authenticate with Reddit using PRAW OAuth2 credentials (environment variables)
2. Fetch top 10 "hot" posts from r/wallstreetbets subreddit
3. For each post:
   - Check for image attachment (i.redd.it, imgur, preview.redd.it)
   - If image present: analyze synchronously via GPT-4o-mini vision API
   - Extract visual context (charts, earnings data, tickers from screenshots)
   - Store image URL and analysis text in reddit_posts table
4. Fetch top 1000 comments per post, sorted by engagement (score × replies)
5. Build parent chain arrays for threaded comment context
6. Store posts and comment metadata in database

**Phase 2: Prioritization**
1. For each of the ~10,000 comments fetched:
   - Calculate financial_score: keyword density (calls, puts, options, strike, expiry, DD, etc.)
   - Lookup author_trust_score from authors table (0-1 based on historical accuracy)
   - Calculate engagement_score: log(upvotes + 1) × reply_count
   - Apply depth_penalty: reduce score for deeply nested comments (focus on top-level)
   - Compute composite priority_score = (financial_score × 0.4) + (author_trust × 0.3) + (engagement × 0.3) - depth_penalty
2. Rank all comments by priority_score descending
3. Select top 50 comments per post (~500 comments total for AI analysis)
4. Attach parent chain context to each selected comment

**Phase 3: Analysis**
1. Check comment deduplication:
   - Query database for existing comment by `reddit_id`
   - If exists: skip AI call, reuse stored annotations (sentiment, sarcasm, reasoning, confidence, tickers); UPDATE comment's `analysis_run_id` to current run (ensures Phase 4 signal detection includes this comment). **Note:** Deduplicated comments retain their original `author_trust_score` snapshot from first analysis. This is acceptable: trust scores change slowly, and re-lookup would add complexity for negligible accuracy gain.
   - If new: proceed to AI analysis
2. For each new comment:
   - Build AI prompt with: post title, image analysis (if present), parent chain, comment body, author trust score
   - Call OpenAI GPT-4o-mini with 5 concurrent requests (asyncio/ThreadPoolExecutor), processing comments in batches of 5
   - Parse JSON response: tickers array, ticker_sentiments array, sentiment, sarcasm_detected flag, has_reasoning flag, confidence score, reasoning_summary
   - Lookup author's current trust score from authors table; set `author_trust_score` on the comment record (point-in-time snapshot for Phase 4 signal confidence calculation)
   - Store comment and annotations in comments table (commit each batch of 5 comments in a single transaction for cost protection on retry (max loss on crash: 5 comments' API cost))
   - For each entry in AI response ticker_sentiments array: INSERT INTO comment_tickers (comment_id, ticker, sentiment) using per-ticker sentiment direction
3. Handle errors: retry malformed JSON once; skip comment if retry fails; log and continue

**Phase 3.5: Prediction Creation**
1. For each unique ticker in comment_tickers from current analysis run (batched):
   - Fetch Schwab options chain for ticker (one call per unique ticker)
2. For each comment_ticker with this ticker:
   - INSERT OR IGNORE INTO predictions (UNIQUE(comment_id, ticker) handles dedup):
     - option_type = 'call' if sentiment == 'bullish' else 'put'
     - Select strike using same logic as Phase 5 position opening:
       - Filter expirations: 14 ≤ DTE ≤ 21, prefer closest to 17
       - Target delta: +0.30 (calls) or -0.30 (puts), tolerance [0.15, 0.50]
     - Record contract_symbol, strike_price, expiration_date
     - Fetch entry_premium from option quote
     - contracts = max(1, floor(2000 / (entry_premium × 100)))
     - contracts_remaining = contracts
     - status = 'tracking', entry_date = today
   - If no valid strike: status = 'expired', append `prediction_strike_unavailable` warning
   - If Schwab unavailable: status = 'expired', append `schwab_prediction_unavailable` warning
3. COMMIT per ticker batch

**Phase 4: Signal Detection**
1. Group all comments (new + existing from deduplication) by ticker using comment_tickers table:
   SELECT ct.ticker, c.* FROM comment_tickers ct JOIN comments c ON c.id = ct.comment_id WHERE c.analysis_run_id = current_run_id GROUP BY ct.ticker
2. Further group by signal_date (current UTC calendar day)
3. For each ticker on this date:
   - **Quality Signal Calculation:**
     - Count distinct users with comments where: has_reasoning=true AND sarcasm_detected=false AND ai_confidence ≥ quality_min_confidence (default 0.6) (quality filters from `comments` table)
     - Check directional alignment using `comment_tickers.sentiment` (per-ticker sentiment): all qualifying comments' per-ticker sentiment for this ticker must be bullish OR all bearish
     - Fire signal if: distinct_users ≥ quality_min_users (default 2) AND alignment achieved
   - **Consensus Signal Calculation:**
     - Count total comments mentioning ticker, using `comment_tickers.sentiment` to exclude neutral per-ticker sentiment
     - Count distinct users contributing comments
     - Calculate directional alignment percentage using `comment_tickers.sentiment`: bullish_count / (bullish_count + bearish_count) for this ticker
     - Fire signal if: comment_count ≥ consensus_min_comments (default 30) AND distinct_users ≥ consensus_min_users (default 8) AND alignment ≥ consensus_min_alignment (default 0.7)
   - **Confidence Calculation** (for fired signals):
     - volume_score = min(1.0, actual_count / (threshold × 3))
     - alignment_score = (actual_alignment - min_alignment) / (1.0 - min_alignment)
     - For Quality signals, set alignment_score = 1.0 (unanimity requirement means alignment is maximal by definition; formula only applies to Consensus signals)
     - avg_ai_confidence = mean of contributing comments' ai_confidence values
     - avg_author_trust = mean of contributing comments' author_trust_score values
     - signal_confidence = (volume_score × 0.25) + (alignment_score × 0.25) + (avg_ai_confidence × 0.30) + (avg_author_trust × 0.20)
   - **Emergence Detection** (if system has ≥7 days of history):
     - Query prior 7 days: count mentions of this ticker
     - If prior_mentions < 3 AND current_mentions ≥ 13 AND current_distinct_users ≥ 8: flag is_emergence = true
     - If system has <7 days history: set is_emergence = NULL (warmup period)
4. Upsert signals to database:
   - Unique constraint on (ticker, signal_type, signal_date) prevents duplicates
   - First run: creates signal with created_at timestamp
   - Subsequent runs same day: updates signal with new data, updates updated_at timestamp
   - This "daily rollup" model prevents duplicate positions from multiple analysis runs per day
   - Link contributing comments: INSERT INTO signal_comments (signal_id, comment_id) for each comment meeting signal criteria

**Phase 5: Position Management**
1. Check market hours: if outside 9:30 AM - 4:00 PM ET, skip position opens entirely. Log warning: "Signal detected outside market hours; position not opened. Re-run during market hours to act on signals." Signals are still recorded.
2. Identify signals newly meeting threshold (signal.confidence ≥ 0.5 AND signal.position_opened = false)
3. For each qualified signal:
   - Determine target portfolios: 2 portfolios per signal based on signal_type
     - Quality signal → stocks_quality AND options_quality
     - Consensus signal → stocks_consensus AND options_consensus
   - **Stocks long-only rule (Phase 1):** If signal direction is bearish, skip stock portfolio (no short positions). Options portfolio still opens puts. Log: "Bearish signal: stock position skipped (long-only Phase 1), options position opened."
   - For each target portfolio (not skipped):
     - Fetch real-time quote from Schwab API for entry pricing (last trade price for stocks, mark price for options)
     - Check current position count: query positions WHERE portfolio_id = X AND status = 'open'
     - If count < 10 (position limit):
       - Calculate position size using confidence-weighted formula (see FR-023)
       - **Cash guard:** If `cash_available < position_size`: skip position for this portfolio; log warning "Insufficient cash in {portfolio_name}: need ${position_size}, have ${cash_available}"; continue to next portfolio
       - Calculate stop_loss_price and take_profit_price at position creation:
         - **Stocks:** `stop_loss_price = entry_price × (1 + stock_stop_loss_pct)`, `take_profit_price = entry_price × (1 + stock_take_profit_pct)`
         - **Options:** stop_loss and take_profit are premium-percentage-based; monitor against `premium_change_pct` thresholds (no price-level fields needed; use `entry_price` as premium baseline)
       - Create position record with entry_date, entry_price, stop_loss_price, take_profit_price, status='open'
       - Deduct position_size from portfolio.cash_available
     - If count = 10 (at limit):
       - Find lowest-confidence open position in this portfolio
       - If new_signal.confidence > lowest.confidence + 0.1:
         - Check safeguard: if lowest position has unrealized_gain > +5%, skip replacement (protect winners); log warning
         - Else: **Replacement flow (close-then-open):**
           1. Fetch current price for the existing position (Schwab API)
           2. INSERT INTO position_exits: exit_reason='replaced', exit_price=current_price, quantity_pct=1.0, shares_exited/contracts_exited=remaining quantity, realized_pnl calculated
           3. UPDATE existing position: status='closed', exit_date=today, exit_reason='replaced', shares_remaining=0/contracts_remaining=0, hold_days=(today - entry_date).days, realized_return_pct=SUM(exits.realized_pnl)/position_size
           4. UPDATE portfolio: cash_available += exit_proceeds (proceeds-only, same formula as Phase 6)
           5. Open new position using standard flow above (calculate size, cash guard, create record, deduct cash)
       - Else: reject new signal (insufficient confidence advantage)
   - Set signal.position_opened = true (when at least one position is opened for this signal)
   - **Known limitation (Phase 1):** `position_opened` is signal-level, not per-portfolio. If a bullish signal opens a stock position but options fails (Schwab down, no valid strike), `position_opened = true` permanently prevents retry for the options portfolio. Bearish signals are unaffected (stock portfolio explicitly skipped). Acceptable for Phase 1; Phase 2 may add per-portfolio tracking if options coverage loss is significant.
   - **Note:** `skip_reason` is not stored on the signals table. The API computes it dynamically per-portfolio when GET /signals is called with `portfolio_id`. **Reliability caveat:** Only `bearish_long_only` is reliably computable at query time (static policy rule). Transient skip reasons (`no_valid_strike`, `portfolio_full`, `safeguard_blocked`) cannot be reconstructed because the state that caused the skip may have changed since the signal was evaluated. For these cases, the API returns generic `"not eligible"` with no further detail. Phase 2 may add a `skip_log` table if granular skip tracking proves valuable.
4. Update portfolio values:
   - current_value = cash_available + SUM(current_price * shares_remaining for open stock positions) + SUM(current_premium * contracts_remaining * 100 for open option positions)
   - On position open: cash_available -= position_cost (current_value unchanged; cash converted to position at market price)
   - On position close: cash_available += exit_proceeds; position removed from SUM; recalculate current_value
   - On partial exit: cash_available += partial_proceeds; remaining position stays in SUM with reduced quantity; recalculate current_value

**Phase 6: Price Monitoring** (automatic at end of /analyze)
1. Derive `last_check_time`:
   - **First-ever run** (no prior completed analysis_runs): set `last_check_time` = current run's `started_at` (only today's data is relevant)
   - **Subsequent runs**: use the most recent completed analysis run's `started_at` timestamp
2. Determine price data strategy:
   - If last_check_time is within current trading day: use 5-min intraday candles from Schwab API
   - If last_check_time is from previous trading day(s): first fetch daily OHLC from yfinance for gap days to check exit triggers using daily high/low, then use 5-min candles for today only
3. Query all open positions (status='open') across all 4 portfolios
4. For each **stock position**:
   - Fetch real-time quote from Schwab API for current price
   - Fetch intraday candles (5-min) from Schwab API since last_check_time (or daily OHLC from yfinance for gap days)
   - Derive: `period_high` = max of intraday highs since last check, `period_low` = min of intraday lows since last check
   - When the aggregate period_high or period_low breaches any exit trigger, iterate individual candles chronologically to determine correct exit ordering (FR-031 authoritative). If no trigger breached, skip candle iteration.
   - Calculate hold_days using calendar days: hold_days = (current_date - entry_date).days
   - Check exit conditions in priority order using period_high/period_low to catch breaches:
     - **Stop-loss**: If period_low ≤ stop_loss_price → close 100%, exit_price=stop_loss_price (simulated fill at trigger level). If stop_loss_price == entry_price (breakeven promotion was active): exit_reason='breakeven_stop'; otherwise: exit_reason='stop_loss'
     - **Take-profit** (first trigger): If period_high ≥ take_profit_price AND shares_remaining = shares → close 50% (shares_exited = floor(shares_remaining × 0.5)), set trailing_stop_active=true, exit_reason='take_profit', exit_price=take_profit_price (simulated fill)
     - **Trailing stop**: If trailing_stop_active AND period_low ≤ peak_price × 0.93 → close remainder (shares_exited = shares_remaining), exit_reason='trailing_stop', exit_price=peak_price × 0.93 (simulated fill)
     - **Breakeven stop**: If current_price ≥ entry_price × 1.05 AND hold_days ≥ 5 AND shares_remaining = shares → raise stop_loss_price to entry_price
     - **Time stop**: If hold_days ≥ 5 AND current_gain < +5% → close 100% (shares_exited = shares_remaining), exit_reason='time_stop', exit_price=current_price
     - **Extended time stop**: If hold_days ≥ 7 AND current_gain +5-15% AND shares_remaining = shares → close 100% (shares_exited = shares_remaining), exit_reason='time_stop', exit_price=current_price
     - **Max time stop**: If hold_days ≥ 10 → close 100%, exit_reason='time_stop', exit_price=current_price
   - Update peak_price = max(peak_price, period_high) for trailing stop tracking
   - **Note:** Bracket exits (stop-loss, take-profit, trailing stop) use period_high/period_low to catch any intraday breach — simulating real broker orders that trigger on price touch. Time-based conditions (breakeven promotion, time stops) use current_price to evaluate position health at check time, avoiding action on fleeting intraday wicks.
5. For each **options position**:
   - Fetch current option premium from Schwab API (mark price)
   - Fetch underlying stock price from Schwab API
   - Calculate hold_days using calendar days
   - Check exit conditions in priority order:
     - **Expiration protection**: If DTE ≤ 2 → close 100%, exit_reason='expiration', exit_price=current_premium
     - **Stop-loss**: If premium_change_pct ≤ -0.50 → close 100%, exit_reason='stop_loss', exit_price=entry_price × 0.50 (simulated fill at trigger level). Where `premium_change_pct = (current_premium - entry_price) / entry_price`
     - **Take-profit** (first trigger): If premium_change_pct ≥ +1.00 AND contracts_remaining = contracts → close 50% of contracts (contracts_exited = floor(contracts_remaining × 0.5)), set trailing_stop_active=true, exit_reason='take_profit', exit_price=entry_price × 2.00 (simulated fill)
     - **Trailing stop**: If trailing_stop_active AND current_premium ≤ peak_premium × 0.70 → close remaining contracts (contracts_exited = contracts_remaining), exit_reason='trailing_stop', exit_price=peak_premium × 0.70 (simulated fill)
     - **Time stop**: If hold_days ≥ 10 → close 100%, exit_reason='time_stop', exit_price=current_premium
   - Update peak_premium = max(peak_premium, current_premium)
6. For each exit triggered:
   - INSERT INTO position_exits (position_id, exit_date, exit_price, exit_reason, quantity_pct, shares_exited, contracts_exited, realized_pnl)
     - For stock exits: populate shares_exited (contracts_exited = NULL)
     - For options exits: populate contracts_exited (shares_exited = NULL)
   - UPDATE positions: for stocks SET shares_remaining = shares_remaining - shares_exited; for options SET contracts_remaining = contracts_remaining - contracts_exited
   - UPDATE portfolios: proceeds-only cash formula (realized_pnl stays in position_exits for reporting, does not touch cash_available):
     - For stock exits: `cash_available += exit_price × shares_exited`
     - For options exits: `cash_available += exit_price × contracts_exited × 100`
   - If position fully closed (shares_remaining = 0 or contracts_remaining = 0):
     - Set positions.status = 'closed', positions.exit_date = exit_date
     - Set positions.hold_days = exit_date - entry_date
     - Calculate positions.realized_return_pct = SUM(position_exits.realized_pnl) / position_size
   - Recalculate portfolio current_value
   - Formula: current_value = cash_available + SUM(current_price * shares_remaining for open stocks) + SUM(current_premium * contracts_remaining * 100 for open options)
7. After fetching prices for each monitored ticker: UPSERT INTO price_history (ticker, date, open, high, low, close, fetched_at) using today's OHLC data. Use `INSERT OR REPLACE` keyed on UNIQUE(ticker, date) constraint to avoid duplicates across multiple /analyze runs per day.
   **Prediction Monitoring** (after processing real positions):
   - Handle expired-past-expiration: For each prediction WHERE status = 'tracking' AND expiration_date < today: INSERT prediction_exits (exit_reason='expiration', quantity_pct=1.0, contracts_exited=contracts_remaining). Calculate simulated_return_pct, set status='resolved'.
   - Monitor active predictions: For each prediction WHERE status = 'tracking', batch by ticker (one Schwab options chain call per unique ticker, reuse cached data from real position monitoring):
     - Fetch current premium for contract_symbol
     - UPDATE prediction SET current_premium, peak_premium = MAX(peak_premium, current_premium)
     - INSERT prediction_outcomes (day_offset, premium, underlying_price)
     - Run shared exit evaluation (MonitoredInstrument interface):
       a. EXPIRATION PROTECTION: If DTE ≤ 2 → close all contracts_remaining (exit_reason='expiration')
       b. STOP-LOSS: If premium_change_pct ≤ -option_stop_loss_pct → close all (exit_reason='stop_loss')
       c. TAKE-PROFIT (first trigger): If contracts_remaining = contracts AND premium_change_pct ≥ option_take_profit_pct → close 50% (exit_reason='take_profit'), SET trailing_stop_active = TRUE
       d. TRAILING STOP: If trailing_stop_active AND current_premium ≤ peak_premium × (1 - option_trailing_stop_pct) → close remainder (exit_reason='trailing_stop')
       e. TIME STOP: If hold_days ≥ option_time_stop_days → close all remaining (exit_reason='time_stop')
     - INSERT prediction_exits for each triggered exit. Decrement contracts_remaining.
     - If contracts_remaining = 0: simulated_return_pct = SUM(prediction_exits.simulated_pnl) / (entry_premium × contracts × 100). UPDATE prediction SET status='resolved', resolved_at=NOW().
   - **Note:** Predictions do NOT update portfolio cash. Real positions have priority access to Schwab API. Predictions share ticker-batched data.
8. If Schwab API unavailable for a ticker: retry with exponential backoff (1s, 2s, 4s, max 15s), up to 3 attempts. If all fail: log warning, skip monitoring for affected ticker (retry on next /analyze run)

**Warnings Event Catalog:**

Non-fatal degradation events are appended to `analysis_runs.warnings` (JSON array) throughout the pipeline. Each warning is a JSON object with `{type, message, timestamp, context}`.

| Warning Type | Pipeline Phase | Trigger | Example Context |
|---|---|---|---|
| `schwab_stock_unavailable` | Phase 6 | Schwab stock quote/candle fetch fails after retries | `{"ticker": "NVDA", "attempts": 3}` |
| `schwab_options_unavailable` | Phase 6 | Schwab options premium fetch fails after retries | `{"ticker": "NVDA", "position_id": 7}` |
| `image_analysis_failed` | Phase 1 | GPT-4o-mini vision fails after 3 retries | `{"post_id": 42, "image_url": "..."}` |
| `market_hours_skipped` | Phase 5 | Signal detected outside 9:30-16:00 ET | `{"signals_affected": 3}` |
| `insufficient_cash` | Phase 5 | Cash guard blocks position open | `{"portfolio": "stocks_quality", "needed": 5000, "available": 3200}` |
| `schwab_prediction_unavailable` | Phase 3.5 | Schwab options chain fetch fails for prediction creation | `{"ticker": "NVDA", "attempts": 3}` |
| `prediction_strike_unavailable` | Phase 3.5 | No valid strike in DTE/delta range for ticker prediction | `{"ticker": "MEME", "expirations_checked": 4}` |

**Write mechanism:** At each warning site in the pipeline, append a warning object to the in-memory warnings list for the current run. On run completion (or failure), serialize the list as JSON and UPDATE `analysis_runs.warnings`. If the list is empty, leave `warnings` as NULL (not empty array).

**Phase 7: Post-Analysis Updates**

*7a. Author Trust Update:*
1. For each unique author in current analysis run:
   - Increment total_comments by number of comments in this run
   - Increment high_quality_comments by count where has_reasoning=true
   - Increment total_upvotes by sum of comment scores
   - Recalculate avg_conviction_score (based on comment length, reasoning presence, confidence)
   - Update last_active timestamp
2. Recalculate avg_sentiment_accuracy from resolved predictions — simulated options positions evaluated by Phase 6 exit monitoring:
   - After prediction resolution: read blended simulated_return_pct from prediction_exits
   - Determine is_correct (return > 0), apply HITL override if present (correct/incorrect/excluded)
   - Update author's accuracy via EMA: (1 - accuracy_ema_weight) × old + accuracy_ema_weight × new
   - Excluded predictions do not affect accuracy. Accuracy data available within ~2-4 weeks (vs 30-60 days)

*7b. Evaluation Period Management:*
All 4 portfolios share a single 30-day window. Phase 7b manages 4 rows (one per portfolio) in lockstep:
1. Query evaluation_periods for any active period (status = 'active')
2. If no active period exists (first ever run): CREATE 4 evaluation_periods rows (one per portfolio) with period_start = today, period_end = today + 30 days, status = 'active', instrument_type and signal_type from portfolio, value_at_period_start = portfolio.current_value
3. If active period exists and period_end < today: SET status = 'completed' on all 4 rows, calculate final metrics per portfolio (portfolio_return_pct, sp500_return_pct, relative_performance, beat_benchmark, total_positions_closed, winning_positions, losing_positions, avg_return_pct, signal_accuracy_pct); CREATE 4 new rows with period_start = previous period_end, period_end = period_start + 30 days, status = 'active', value_at_period_start = portfolio.current_value
   Note: "closed position" = status='closed' (fully exited, shares_remaining=0 or contracts_remaining=0). Partially exited positions excluded from period metrics until fully closed. realized_total_pnl per position = SUM(position_exits.realized_pnl) for that position.
4. If active period exists and period_end >= today: no action needed (period still running)

#### 3.2.3 State Management

The backend uses a **stateless architecture** with clear separation between ephemeral and persistent state:

| State Type | Storage Location | Lifetime | Purpose |
|------------|------------------|----------|---------|
| **Request-scoped** | Python objects (ProcessedPost, ProcessedComment) in memory | Single /analyze call | Temporary data structures during processing pipeline |
| **Session-scoped** | N/A (not implemented) | N/A | No session state; each API call is independent |
| **Persistent** | SQLite database | Permanent | All signals, positions, comments, author history, portfolio state |

**Key Implications:**
- No in-memory caching between requests; all data fetched from SQLite on each call
- No need for cache invalidation logic or distributed state synchronization
- Backend can be restarted without state loss (all state in database)
- Simplifies deployment: no Redis, no sticky sessions, no session stores

**Request-Scoped Data Flow:**
```
Reddit API → ProcessedPost objects → ProcessedComment objects → SQLite
                                   ↓
                         (discarded after insert)
```

#### 3.2.4 Error Handling Strategy

The backend implements graceful degradation where possible, failing fast only when continuation would produce incorrect results:

| Failure Scenario | Detection | Response | User Impact |
|------------------|-----------|----------|-------------|
| **Reddit API outage** | PRAW raises exception during post fetch | Log error with details, return HTTP 503 Service Unavailable | Analysis run fails; user sees error message, retries manually later |
| **Image analysis failure** | OpenAI vision API timeout/error | Retry 3 times with exponential backoff (2s, 5s, 10s delays); if all fail: log warning, set image_analysis=NULL, continue | Comment analysis proceeds without image context (acceptable; images are supplementary) |
| **OpenAI rate limit (429)** | OpenAI API returns 429 status | Exponential backoff (1s, 2s, 4s, 8s, max 30s), retry request | Analysis slows but completes; user experiences longer wait |
| **Malformed AI JSON** | json.loads() raises exception | Retry same comment once; if retry fails: log error, skip comment, continue | Single comment lost; signal detection uses remaining comments |
| **yfinance data unavailable** | yfinance returns empty data or raises exception | Log warning with ticker and date, skip position monitoring for affected ticker | Exit conditions not checked this run; will retry on next /analyze (acceptable for swing trading 5-10 day horizons) |
| **Schwab API unavailable (stocks)** | HTTP error or timeout fetching stock quote or intraday candles | Retry with exponential backoff (1s, 2s, 4s, max 15s), up to 3 attempts; if all fail: log warning, skip monitoring for affected ticker | Exit conditions not checked this run for affected tickers; will retry on next /analyze run |
| **Schwab API unavailable (options)** | HTTP error or timeout fetching options premium or greeks | Same retry strategy as stocks; if all fail: log warning, skip options monitoring for affected position | Options exit conditions not checked this run; retry on next run |
| **Schwab auth token expired** | 401 response from Schwab API | Proactively refresh access token using stored refresh token; if refresh token also expired (7+ days inactive): log error with re-auth instructions, fall back to yfinance for stocks, skip options | User may need to re-run CLI setup script if inactive >7 days |
| **SQLite write failure** | sqlite3 raises exception | Rollback transaction, log full error trace, return HTTP 500 Internal Server Error | Analysis results lost; user sees error, reruns /analyze |
| **Comment deduplication miss** | Duplicate reddit_id inserted (unique constraint violation) | Catch exception, skip insert, continue (comment already analyzed) | No impact; prevents redundant AI calls (cost savings) |

**Error Handling Philosophy:**
- **Fail fast on data integrity issues**: SQLite transaction failures abort entire run
- **Graceful degradation on external APIs**: Continue with partial data when safe
- **Retry with backoff on transient errors**: Rate limits, timeouts
- **Log verbosely for debugging**: This is an experimental tool; detailed logs aid iteration

#### 3.2.5 Key Design Decisions

This section documents critical architectural decisions and the alternatives considered:

| Decision | Rationale | Alternative Rejected | Trade-off |
|----------|-----------|---------------------|-----------|
| **Synchronous image analysis** | Ensures image context is available before comment analysis begins; simplifies prompt construction; acceptable latency for swing trading use case (not latency-sensitive) | Asynchronous parallel processing: analyze image and comments simultaneously, merge results later | Rejected: Adds complexity (merge logic, race conditions); marginal performance gain (~10-15 seconds) not worth it for experimental tool |
| **Individual AI calls (1 comment/call)** | Maximizes accuracy by preventing cross-contamination between comments; each comment gets full context (post image, author trust, parent chain) without interference; simplifies error attribution and retry logic; cost difference negligible (~$0.25/month extra vs batching 5 comments) | Batch 5-10 comments per API call to reduce costs | Rejected: This is an experiment testing hypothesis accuracy; saving $3/year not worth risking signal quality degradation from confused AI responses |
| **Daily signal rollup (per ticker/type/day)** | Prevents duplicate positions when user runs /analyze multiple times per day; enables signal refinement (more data improves confidence calculation); matches trading cadence (positions open once per day max) | Per-run signal creation: new signal entity for each /analyze call | Rejected: Would create duplicate positions if user runs analysis 3x daily; clutters database with redundant signal records |
| **Automatic position monitoring in /analyze** | Ensures exit conditions checked immediately after fetching latest prices; eliminates manual step (user doesn't need to remember to call /monitor separately); matches on-demand usage pattern | Separate manual /positions/monitor endpoint that user must call explicitly | Hybrid approach: Both automatic (in /analyze) and manual (/monitor endpoint) available; automatic is primary, manual is fallback for debugging |
| **Stateless API design** | Simplifies deployment (no Redis, no session stores); eliminates cache invalidation bugs; enables horizontal scaling if needed in Phase 2; reduces operational complexity | Stateful API with session caching of Reddit data, AI responses, price data | Rejected: Premature optimization; single-user tool doesn't need caching; SQLite fast enough for local queries; adds complexity for minimal gain |
| **SQLite for author trust scores** | Fast local lookups during prioritization (no network round-trip); embedded database simplifies deployment; sufficient performance for single-user scale (<10k authors tracked) | External cache (Redis) for author trust scores | Rejected: Over-engineering; SQLite index on username provides sub-millisecond lookups; adding Redis adds deployment dependency for no measurable benefit |

**See Also:**
- **Appendix A**: Full PRAW configuration details and Reddit API integration specifications
- **Appendix D**: Internal data structure definitions (ProcessedPost, ProcessedComment schemas)
- **Appendix E**: Complete AI prompt templates, response parsing logic, and error handling for OpenAI integration

---

### 3.3 Data Model Architecture

The SQLite database organizes data into five logical layers, each serving a distinct purpose in the analysis and trading pipeline.

#### 3.3.1 Database Layer Overview

| Layer | Tables | Purpose | Read/Write Pattern |
|-------|--------|---------|-------------------|
| **Configuration** | system_config | Stores signal detection thresholds, confidence calculation weights, exit strategy parameters, system phase (paper/real trading), emergence activation date | Read-heavy; writes only during threshold tuning or phase transitions |
| **Source Data** | reddit_posts, authors, comments, analysis_runs | Raw Reddit data with AI annotations; immutable historical record of what was said and how AI interpreted it; analysis_runs tracks each /analyze invocation with status and timing | Write during /analyze acquisition phase; read during signal detection and evidence drill-down |
| **Junction** | signal_comments, comment_tickers | Many-to-many relationships linking signals to their contributing comments, and comments to their extracted tickers | Write during signal detection (signal_comments) and AI analysis (comment_tickers); read during evidence drill-down |
| **Analytics** | signals | Aggregated daily signals per ticker/signal_type; represents actionable trading opportunities derived from comment analysis | Upsert during /analyze signal detection phase; read by position management and dashboard |
| **Trading** | portfolios, positions, position_exits, price_history | Paper trading simulation state; tracks 4 portfolios, open/closed positions, normalized exit events, daily price data for monitoring | Write during position open/close/exit; read during monitoring and dashboard display |
| **Predictions** | predictions, prediction_outcomes, prediction_exits | Simulated options predictions from comment_tickers; tracks lifecycle from creation through Phase 6 exit monitoring to resolution | Write during Phase 3.5 (prediction creation) and Phase 6 (monitoring/exits); read during Phase 7a (accuracy update) and dashboard |
| **Evaluation** | evaluation_periods | Performance tracking against S&P 500 benchmark; 30-day rolling window assessments | Write at period end; read for performance dashboard and hypothesis validation |

#### 3.3.2 Key Relationships

The following entity relationships define how data flows through the system:

```
analysis_runs (1) ──> (N) comments [each comment linked to the run that analyzed it]

reddit_posts (1) ──┬──> (N) comments
                   └──> (1) image_analysis

authors (1) ──> (N) comments [via author username]

comments (N) ──┬──> (N) signals [via signal_comments junction table]
               └──> (N) tickers [via comment_tickers junction table]

signals (1) ──┬──> (N) signal_comments ──> (N) comments [evidence chain]
              └──> (N) positions [one signal can trigger multiple positions across portfolios]

portfolios (1) ──> (N) positions [max 10 open positions per portfolio enforced by application]

positions (1) ──> (N) position_exits [normalized exit events: partial/full closes]

positions (N) ──> (1) ticker in price_history [for daily price tracking during monitoring]

evaluation_periods (N) ──> (1) portfolio [rolling 30-day performance windows]

predictions (1) ──> (N) prediction_outcomes [daily premium snapshots]

predictions (1) ──> (N) prediction_exits [simulated exit events]

comments (1) ──> (N) predictions [via comment_id FK, one prediction per comment_ticker]
```

**Data Flow Narrative:**
1. Analysis run created → Reddit posts and comments fetched and stored (linked to run)
2. Comments analyzed individually → AI annotations added, committed per-comment (sentiment, sarcasm, reasoning, tickers via comment_tickers)
3. Comments aggregated → signals created/upserted (grouped by ticker/signal_type/day), linked via signal_comments
4. Signals meeting threshold → positions opened in relevant portfolios (stocks long-only Phase 1)
5. Schwab intraday prices fetched → positions monitored for exit conditions (tiered gap handling with yfinance)
6. Exit conditions triggered → position_exits record each close event (partial or full)
7. Positions fully closed → evaluation_periods track cumulative performance

#### 3.3.3 Critical Constraints

These database constraints enforce business rules and prevent data integrity issues:

1. **Unique signal per day: `(ticker, signal_type, signal_date)`**
   - Prevents duplicate positions when /analyze runs multiple times per day
   - Enables "daily rollup" pattern: first run creates signal, subsequent runs refine it
   - SQLite unique constraint enforced at database level

2. **Comment deduplication: `reddit_id` UNIQUE**
   - Prevents redundant AI analysis when same comment appears in multiple "hot" posts
   - Cost savings: reuses stored annotations instead of re-calling OpenAI
   - SQLite unique constraint enforced at database level

3. **Foreign key enforcement: `PRAGMA foreign_keys = ON`**
   - Must be set on every SQLite connection (not default enabled)
   - Ensures referential integrity: can't create position without valid signal_id
   - Prevents orphaned records if cascade deletes are needed

4. **Portfolio position limits: 10 open positions per portfolio**
   - Application-enforced (not database constraint)
   - Checked in Phase 5 of /analyze request flow
   - Safeguard: never replace position with unrealized gain >+5%

5. **Portfolio isolation: `portfolio_id` separates 4 independent portfolios**
   - stocks_quality, stocks_consensus, options_quality, options_consensus
   - Each has separate capital ($100k), cash_available, position tracking
   - Enables independent performance analysis of signal types and instrument types

#### 3.3.4 Configuration-Driven Design

The system's behavior is controlled via the `system_config` table, enabling threshold tuning without code changes:

**Signal Detection Thresholds:**
- `quality_min_users` (default: 2): Minimum distinct users with reasoning for Quality signal
- `quality_min_confidence` (default: 0.6): Minimum AI confidence for comment to qualify
- `consensus_min_comments` (default: 30): Minimum comment volume for Consensus signal
- `consensus_min_users` (default: 8): Minimum distinct users for Consensus signal (anti-spam)
- `consensus_min_alignment` (default: 0.7): Minimum directional alignment percentage (70% bullish or bearish)

**Confidence Calculation Weights:**
- `confidence_weight_volume` (default: 0.25): Weight for volume above threshold
- `confidence_weight_alignment` (default: 0.25): Weight for directional alignment strength
- `confidence_weight_ai_confidence` (default: 0.30): Weight for average AI confidence of contributing comments
- `confidence_weight_author_trust` (default: 0.20): Weight for average author trust score

**Author Trust Calculation (see Appendix F):**
- `trust_weight_quality` (default: 0.40): Weight for quality_ratio in trust score
- `trust_weight_accuracy` (default: 0.50): Weight for accuracy_component in trust score
- `trust_weight_tenure` (default: 0.10): Weight for tenure_factor in trust score
- `trust_default_accuracy` (default: 0.50): Default accuracy for authors with no history
- `trust_tenure_saturation_days` (default: 30): Days until tenure reaches maximum
- `accuracy_ema_weight` (default: 0.30): Weight for new data in accuracy exponential moving average

**Stock Exit Strategy Thresholds:**
- `stock_stop_loss_pct` (default: -0.10): Stop-loss trigger at -10% from entry (FR-026)
- `stock_take_profit_pct` (default: 0.15): Take-profit trigger at +15% from entry (FR-027)
- `stock_trailing_stop_pct` (default: 0.07): Trailing stop at 7% from peak price (FR-028)
- `stock_breakeven_trigger_pct` (default: 0.05): Breakeven stop activates at +5% gain (FR-030)
- `stock_breakeven_min_days` (default: 5): Minimum days held before breakeven stop (FR-030)
- `stock_time_stop_base_days` (default: 5): Base time stop at 5 days if <+5% gain (FR-029)
- `stock_time_stop_base_min_gain` (default: 0.05): Gain threshold for base time stop (FR-029)
- `stock_time_stop_extended_days` (default: 7): Extended time stop for +5-15% gain (FR-029)
- `stock_time_stop_max_days` (default: 10): Maximum hold period regardless of gain (FR-029)
- `stock_take_profit_exit_pct` (default: 0.50): Percentage of position to close on take-profit (FR-027)

**Options Exit Strategy Thresholds:**
- `option_stop_loss_pct` (default: -0.50): Stop-loss trigger at -50% premium change (FR-041)
- `option_take_profit_pct` (default: 1.00): Take-profit trigger at +100% premium change (FR-042)
- `option_trailing_stop_pct` (default: 0.30): Trailing stop at 30% from peak premium (FR-043)
- `option_time_stop_days` (default: 10): Time stop at 10 days held (FR-045)
- `option_expiration_protection_dte` (default: 2): Close when days to expiration ≤ 2 (FR-044)
- `option_take_profit_exit_pct` (default: 0.50): Percentage of position to close on take-profit (FR-042)

**System State:**
- `system_start_date`: Date of first signal recorded; used to calculate emergence activation (start_date + 7 days)
- `phase`: Current phase ('paper_trading' or 'real_trading'); determines risk tolerance and position sizing

**Implementation Note:** All pseudocode in this document shows default values inline for readability. Implementation MUST read weights and thresholds from `system_config` at runtime to enable tuning without code changes. This applies to signal detection thresholds (Section 3.2.2 Phase 4), exit strategy parameters (Section 3.2.2 Phase 6), and author trust calculations (Appendix F).

**Design Rationale:**
During the experimental phase (first 90 days), threshold tuning is expected. By storing thresholds in the database:
- No code changes or redeployment required to adjust sensitivity
- Historical signals remain tied to thresholds active when created (via created_at timestamp)
- Enables A/B testing: run analysis with different thresholds, compare signal quality

#### 3.3.5 Schema Initialization

On first deployment, the database must be initialized with configuration and portfolio seed data:

**Required Initialization Steps:**
1. Enable foreign key constraints: `PRAGMA foreign_keys = ON;`
2. Enable WAL mode: `PRAGMA journal_mode = WAL;`
3. Insert 33 system_config entries: 5 signal detection thresholds + 8 confidence/trust weights + 2 system state + 16 exit strategy parameters (10 stock + 6 options)
4. Create 4 portfolios with $100k each (stocks_quality, stocks_consensus, options_quality, options_consensus)
5. Set system_start_date to current date for emergence activation countdown

**Emergence Activation Behavior:**
- **Days 1-7**: All signals have `is_emergence = NULL`; emergence detection disabled (insufficient historical baseline)
- **Day 8+**: Emergence detection active; compares current mentions to prior 7-day baseline
- Dashboard displays: "Emergence detection: Activates in N days" during warmup, then "Emergence detection: Active ✓"

**See Also:**
- **Appendix B**: Complete table schemas with all column definitions, data types, and full SQL initialization script

---

### 3.4 REST API Design

The FastAPI backend exposes a RESTful JSON API organized around resource-based endpoints. This section describes the API design philosophy and endpoint organization.

#### 3.4.1 API Design Philosophy

**Core Principles:**
- **On-demand execution**: User explicitly triggers analysis via POST /analyze; no background jobs, cron schedules, or automated polling
- **Stateless endpoints**: Each request is independent; no session tracking or cookies; authentication-free (local single-user deployment)
- **Standard envelope**: All successful responses use `{data: {...}, meta: {timestamp, version}}` structure; errors use `{error: {code, message}}`
- **Pagination by default**: List endpoints return first 50 items; support `limit` (max 100) and `offset` query parameters
- **Filter-friendly**: List endpoints accept filters via query params (e.g., `/signals?ticker=NVDA&signal_type=quality`)
- **Explicit relationships**: Evidence drill-down uses nested routes (e.g., `/signals/{id}/comments`) to make parent-child relationships clear

**Response Time Expectations:**
- **POST /analyze**: Returns immediately (HTTP 202 Accepted with `run_id`); pipeline runs in background thread (10-30 minutes)
- **GET /runs/{id}/status**: <100ms (database query for run status, current phase, progress)
- **GET /signals**: <100ms (database query with filters)
- **GET /portfolios**: <50ms (4 portfolio summary records)
- **GET /signals/history**: <200ms (historical confidence data for sparklines)
- **GET /prices/{ticker}**: 1-3 seconds (yfinance API call)

#### 3.4.2 Endpoint Organization

Endpoints are grouped into six functional categories:

| Category | Endpoints | Purpose | Primary User Action |
|----------|-----------|---------|---------------------|
| **Analysis** | POST /analyze<br>GET /runs<br>GET /runs/{id}/status | Trigger analysis pipeline (returns HTTP 202 with run_id; pipeline runs in background thread)<br>View analysis run history with timestamps<br>Poll run status: phase, progress percentage, phase label, error details | User clicks "Run Analysis" button → frontend polls for completion |
| **Signals** | GET /signals<br>GET /signals/{id}<br>GET /signals/{id}/comments<br>GET /signals/history | List detected signals with filters<br>Single signal detail<br>Evidence drill-down with AI annotations via signal_comments junction<br>Historical signal confidence data for sparklines | User explores which tickers are trending and why |
| **Portfolio** | GET /portfolios<br>GET /portfolios/{id} | List all 4 portfolios with summary stats<br>Single portfolio detail with allocation breakdown | User checks portfolio value, cash available, position count |
| **Positions** | GET /positions<br>GET /positions/{id}<br>POST /positions/{id}/close | List positions with filters (portfolio, status, ticker)<br>Single position with exit strategy state and position_exits history<br>Manual early exit (user discretion) | User views open trades, checks P/L, reviews exit history |
| **Validation** | GET /evaluation-periods<br>GET /prices/{ticker} | 30-day rolling performance vs S&P 500 benchmark<br>Price history for sparklines and validation | User assesses hypothesis validity, compares signal types |
| **System** | GET /status | System health: phase, emergence activation state, days until activation, open position count, last run timestamp, active run indicator | Dashboard startup check, debugging |

#### 3.4.3 Primary User Workflow

The typical user session follows this sequence:

```
1. User opens dashboard in browser
   ├─> Frontend: GET /portfolios (load 4 portfolio summaries)
   ├─> Frontend: GET /signals (load recent signals for default Stock/Quality view)
   ├─> Frontend: GET /status (check emergence activation state, active run indicator)
   └─> If active run detected: resume polling (page reload recovery)

2. User clicks "Run Analysis" button
   └─> Frontend: POST /analyze
       ├─> Backend returns HTTP 202 Accepted: {data: {run_id: "abc-123"}}
       ├─> If HTTP 409 Conflict: another run is already in progress
       └─> Frontend begins polling GET /runs/{run_id}/status every 10 seconds

3. Frontend displays 4-stage progress indicator during polling
   ├─> Stage 1: "Fetching Reddit data..." (Phases 1-2: acquisition + prioritization)
   ├─> Stage 2: "Analyzing comments..." (Phase 3: AI analysis, shows N/total progress)
   ├─> Stage 3: "Detecting signals..." (Phases 4-5: signal detection + position management)
   ├─> Stage 4: "Monitoring prices..." (Phase 6: intraday monitoring + exits)
   ├─> Current stage shown active, next stage shown dimmed/upcoming
   └─> On completion: show results summary overlay

4. User reviews results summary
   ├─> Summary shows: signals_created, positions_opened, exits_triggered, errors (if any)
   ├─> Frontend: GET /portfolios (refresh portfolio values)
   ├─> Frontend: GET /signals (refresh signal list)
   └─> Frontend: GET /positions?status=open (view active trades)

5. User drills into specific ticker
   └─> Frontend: GET /signals/{id}/comments (view annotated evidence via signal_comments)
       └─> Display: original comment text + AI overlay (sentiment, sarcasm, reasoning, confidence)

6. User clicks "Performance" sub-tab (within current portfolio)
   └─> Frontend: GET /evaluation-periods?portfolio_id=X (30-day windows vs S&P 500)
```

#### 3.4.4 API Design Decisions

| Decision | Rationale | Alternative Rejected |
|----------|-----------|---------------------|
| **POST /analyze returns immediately (async)** | Returns HTTP 202 with run_id; pipeline runs in background thread with isolated SQLite connection. Prevents browser timeout on 10-30 minute runs. Frontend polls GET /runs/{id}/status for progress. Single-run enforcement returns HTTP 409 if analysis already running. | Synchronous long-running request: browser/proxy timeouts at 10-30 minutes; no progress visibility; blocks user interaction |
| **Startup recovery for stale runs** | On FastAPI startup, query analysis_runs for any record with status='running'. Update to status='failed' with error_message='Process restart detected; previous run did not complete'. Background thread wrapped in try/except to catch all exceptions and update status='failed'. Prevents permanent HTTP 409 lockout after crash. | No recovery mechanism: stale 'running' record blocks all future /analyze calls until manual DB fix |
| **POST /analyze triggers monitoring automatically** | Ensures exit conditions checked immediately after fetching latest prices; matches user mental model ("run analysis" = "update everything"); eliminates manual step | Separate manual POST /positions/monitor: requires user to remember two steps; easy to forget monitoring |
| **No automatic polling/webhooks** | Matches on-demand usage pattern (<3x daily); reduces server load; user controls when to spend OpenAI API credits | Auto-polling every N hours: wastes credits during user downtime; doesn't match swing trading cadence |
| **Nested routes for evidence drill-down** | `/signals/{id}/comments` makes relationship explicit; RESTful hierarchy matches data model; clear that comments "belong to" signal | Flat route `/comments?signal_id=X`: less intuitive relationship; harder to discover via API exploration |
| **Standard JSON envelope with metadata** | Consistent response structure simplifies frontend parsing; `meta.timestamp` enables cache invalidation; `meta.version` supports API versioning in Phase 2 | Bare JSON responses: frontend must handle inconsistent structures; no metadata for debugging |
| **Pagination with limit/offset** | Prevents memory issues with large result sets (e.g., 1000+ historical signals); standard pattern familiar to developers | Cursor-based pagination: more complex implementation; not needed for single-user scale |

**Error Response Format:**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid ticker symbol: INVALID",
    "details": {
      "field": "ticker",
      "constraint": "Must be 1-5 uppercase letters"
    }
  }
}
```

**Common Error Codes:**
- `VALIDATION_ERROR`: Invalid input parameters
- `NOT_FOUND`: Resource doesn't exist (e.g., signal_id not in database)
- `ANALYSIS_ALREADY_RUNNING`: POST /analyze returns HTTP 409 Conflict when a run is already in progress
- `REDDIT_API_ERROR`: Reddit API unavailable or rate limited
- `OPENAI_API_ERROR`: OpenAI API error during analysis
- `SCHWAB_AUTH_ERROR`: Schwab OAuth token expired or invalid (see Section 3.6.2 for lifecycle)
- `DATABASE_ERROR`: SQLite transaction failure

**See Also:**
- **Appendix C**: Complete REST API contract with all endpoints, request/response schemas, query parameters, and pagination details

---

### 3.5 Vue Dashboard Architecture

The Vue.js dashboard provides a web-based interface for visualizing signals, managing portfolios, and exploring evidence. This section describes the dashboard's architecture and integration with the FastAPI backend.

#### 3.5.1 Dashboard Responsibilities

| Feature | Implementation | Backend Integration |
|---------|----------------|---------------------|
| **Display ranked signals** | Fetch signal list, sort by confidence descending, render as two-row signal cards: Row 1 (ticker, direction arrow, confidence badge, comment count, signal type pill — blue for Quality, purple for Consensus, mapped from `signal_type` field), Row 2 (dual sparklines, age label — format: "Today", "1d", "Nd", "2w+" computed from `signal_date`, emergence flag). **Age label:** Computed from UTC `signal_date` vs current UTC date. Since WSB activity peaks in US evening (ET), a signal created at 11 PM ET (next UTC day) may show "1d" when it's <1 calendar day old in ET. This ≤1 day discrepancy is acceptable for Phase 1. | GET /signals?signal_type=quality (filtered by active portfolio sub-tab) |
| **Show portfolio state** | Display 4 portfolio tabs with sub-tabs: Signals (default), Positions, and Performance within each tab. Stock/Quality (default), Stock/Consensus, Options/Quality, Options/Consensus. Show current_value, cash_available, open_position_count, P/L since inception. Include last_valued_at timestamp (derived from last analysis run). Display "Values as of [timestamp]" beneath portfolio values. "Refresh Prices" button fetches live prices for open positions and recomputes current_value on demand. | GET /portfolios, GET /portfolios/{id} |
| **Evidence drill-down** | Click ticker → modal displaying original comments with AI annotation overlay (sentiment badge, sarcasm flag, reasoning indicator, confidence score); original text always visible alongside interpretation. Comments linked via signal_comments junction table. Modal uses scrollable container; load all comments at once (no pagination). Performance acceptable for single-user local deployment. | GET /signals/{id}/comments |
| **Dual sparklines** | Two compact sparklines per signal card: (1) signal confidence history (7-14 days via GET /signals/history), (2) stock price trajectory (7-14 days via GET /prices/{ticker}). Adaptive rendering: ≤2 data points shows dot(s) instead of line; 3+ points renders full sparkline | GET /signals/history, GET /prices/{ticker}?days=14 |
| **Trigger analysis (async polling)** | "Run Analysis" button → POST /analyze returns run_id → frontend polls GET /runs/{id}/status every 10 seconds → 4-stage progress indicator (Fetching → Analyzing → Detecting → Monitoring) with current stage active and next stage dimmed → results summary overlay on completion. Page reload recovery: GET /status detects active run, resumes polling | POST /analyze, GET /runs/{id}/status |
| **Signal card position status** | Four visual states on signal cards in the Signals sub-tab indicating position outcome: (1) "Position Open" — green badge, position currently active, unrealized return % displayed (green if positive, red if negative; source: `position_summary.unrealized_return_pct`), (2) "Position Closed" — gray badge with realized return %, (3) "Below threshold" — subtle gray text, confidence < 0.5, (4) "Not eligible" — subtle gray text with tooltip explaining reason (bearish-long-only, portfolio-full, safeguard-blocked). Distinct from position monitoring indicators below. | GET /signals (position_opened flag + related position data) |
| **Position monitoring indicators** | Three primary states + one composable overlay for open positions in the Positions sub-tab: **Primary states** (mutually exclusive): (1) Active/Monitoring — default, price updating normally, (2) Near Exit — within 2% of any exit trigger (`nearest_exit_distance_pct <= 0.02`), amber highlight, (3) Partially Closed — position_exits exist, show remaining %. **Overlay** (composable with any primary state): Market Closed — outside 9:30-16:00 ET, greyed prices with "as of [last_run_completed_at]" label. | GET /positions |
| **Exit reason display labels** | Map internal `exit_reason` enum values to human-readable labels in the Positions sub-tab: `stop_loss` → "Stop Loss", `take_profit` → "Take Profit", `trailing_stop` → "Trailing Stop", `breakeven_stop` → "Breakeven Stop", `time_stop` → "Time Stop", `expiration` → "Expiration", `manual` → "Manual Close", `replaced` → "Replaced (new signal)". Display as badge on closed positions and in position_exits history. | GET /positions |
| **Manual position close** | "Close" button on each open position row in Positions sub-tab. Click opens inline popover: reason text field (required), quantity radio — "Full close" (default) / "Partial (50%)", "Confirm Close" button. On submit: disable button, show spinner, POST /positions/{id}/close. On success: toast "Position closed", refresh positions. On error: toast with error message. | POST /positions/{id}/close |
| **Options position display** | Options positions in the Positions sub-tab render differently from stocks: show DTE countdown ("5 DTE" decreasing daily from expiration_date), contracts/contracts_remaining instead of shares, premium_change_pct instead of price change, strike price and option_type (Call/Put). Signal cards in Options tabs show option_type in direction indicator. See Appendix C.3 for options position response example. | GET /positions |
| **Market hours indicator** | Header-level indicator showing market open/closed status. When closed: subtle banner "Market closed — prices as of [last close time]". Client-side calculation from Eastern Time | Client-side (no API call) |
| **Performance tracking** | Display 30-day evaluation periods in the Performance sub-tab within each portfolio: period dates, portfolio return %, S&P 500 return %, relative performance, win/loss record, average return, signal accuracy — scoped to the current portfolio. **Empty states:** (1) No periods exist: "Performance tracking begins after your first analysis run. Data will be available after the first 30-day evaluation period completes." (2) Active period only (no completed): show date range + progress indicator ("Day N of 30") with live running metrics (current portfolio return, S&P 500 return to date). (3) Completed period with zero positions: show period row with zeroes and note "No positions closed during this period." **Signals sub-tab empty states:** (1) No analysis runs yet: "No signals yet. Click 'Run Analysis' to fetch and analyze WSB comments." (2) No signals for this portfolio type: "No [Quality/Consensus] signals detected. Signals appear here when analysis identifies matching patterns." **Positions sub-tab empty states:** (1) No open positions: "No open positions. Positions are opened automatically when signals meet the confidence threshold (≥0.5)." | GET /evaluation-periods?portfolio_id=X |
| **Emergence countdown** | During Days 1-7: "Emergence detection: Activates in N days"; Day 8+: "Emergence detection: Active ✓"; calculated from system_start_date | GET /status |

#### 3.5.2 State Management

The dashboard uses **minimal client-side state** with no persistence between page loads:

| State Type | Implementation | Lifetime |
|------------|----------------|----------|
| **No persistent state** | Always loads Stock/Quality portfolio on page load; user preferences (tab selection, filters) reset on refresh | None |
| **Session-local only** | Active portfolio tab (Stock/Quality, Stock/Consensus, etc.) stored in component state; resets to Stock/Quality on page reload | Current browser session until reload |
| **No auto-refresh** | User manually clicks "Refresh" button to reload data; no polling or websockets | N/A |

**Rationale for Minimal State:**
- Simplifies implementation: no localStorage, no Vuex/Pinia store, no state synchronization
- Matches experimental nature: user doesn't need state persistence for exploratory analysis
- Avoids stale data: fresh data on each page load ensures dashboard reflects database state
- Default to Stock/Quality aligns with primary hypothesis (quality signals are "smart money" bet)

#### 3.5.3 Key UI Patterns

**1. Annotated Evidence Display:**
- **Challenge**: Show AI interpretation without obscuring original comment text
- **Solution**: Two-column layout or expandable overlay
  - Left/Top: Original Reddit comment (author, timestamp, upvotes, body text)
  - Right/Bottom: AI annotations (sentiment badge: 🟢 Bullish / 🔴 Bearish, sarcasm flag: ⚠️ if detected, reasoning indicator: 💡 if has_reasoning=true, confidence score: 0.0-1.0 with color gradient)
- **Interaction**: Click "Show Reasoning Summary" expands AI's reasoning_summary text

**2. Dual Sparkline Visualization:**
- **Format**: Two compact sparklines per signal card (~100px wide × 30px tall each), side by side in Row 2
- **Sparkline A (Signal Confidence)**: Daily confidence scores over past 7-14 days from GET /signals/history. Shows signal strength trajectory (rising momentum vs fading interest)
- **Sparkline B (Stock Price)**: Daily closing prices over past 7-14 days from GET /prices/{ticker}. Shows price movement correlation with signal strength
- **Adaptive Rendering**: ≤2 data points renders dot(s) instead of line chart (new signals have insufficient history); 3+ points renders full sparkline with smooth interpolation
- **Data Source**: yfinance for price sparklines (live fetch, not from price_history table); signals/history endpoint for confidence sparklines
- **Fetching Strategy**: GET /signals/history supports batch query (omit `ticker` param to get all tickers for given `signal_type`). GET /prices/{ticker} fetched lazily after signal list renders, max 5 concurrent requests to avoid cascading delays. Cache sparkline data in component state when switching portfolio tabs (avoid refetch). Show placeholder sparkline (empty gray line) while price data loads.

**3. Portfolio Tab Navigation with Sub-Tabs:**
- **Layout**: 4 primary tabs horizontal across top: Stock/Quality (default), Stock/Consensus, Options/Quality, Options/Consensus
- **Sub-tabs**: Each portfolio tab contains three sub-tabs: "Signals" (default), "Positions", and "Performance", placed directly below the primary tab bar
- **State**: Active tab and sub-tab highlight; content area updates to show filtered signals or positions for selected portfolio
- **Default**: Always loads Stock/Quality → Signals sub-tab on page open (no state persistence)

**4. Emergence Countdown Widget:**
- **Days 1-7**: Yellow banner at top: "⏳ Emergence detection: Activates in 5 days (minimum 7 days of data required)"
- **Day 8+**: Green banner: "✓ Emergence detection: Active"
- **Purpose**: Communicates to user that emergence flags are not yet reliable during warmup period

#### 3.5.4 Integration Points

The dashboard integrates with the FastAPI backend via HTTP requests:

| User Action | Frontend Behavior | Backend Endpoint | Response Handling |
|-------------|-------------------|------------------|-------------------|
| **Page load** | Show loading spinner, fetch initial data in parallel. Check for active analysis run (page reload recovery — see flow below) | GET /portfolios, GET /signals, GET /status | Render 4 portfolio tabs with sub-tabs (Signals, Positions, Performance), populate signal list for Stock/Quality → Signals, show emergence status, show market hours indicator. If active run detected: resume polling with progress indicator. Display "Last analysis: [relative time]" in dashboard header (from GET /status last_run_completed_at). Show "Analysis in progress..." if active run detected. |
| **Click "Run Analysis"** | Disable button, POST /analyze → receive run_id → begin polling every 10 seconds | POST /analyze (returns HTTP 202 immediately) | Show 4-stage progress indicator. On 409: show "Analysis already running" message. On completion: show results summary overlay (signals created, positions opened, exits triggered, errors if status='failed', warnings if any non-fatal degradation events) then auto-refresh data |
| **Switch portfolio tab** | Update active tab highlight, keep current sub-tab selection | No backend call (use cached /signals response, filter client-side); or optionally GET /signals?signal_type=X | Re-render signal list or positions list for selected portfolio |
| **Switch sub-tab** | Toggle between "Signals", "Positions", and "Performance" within current portfolio tab | No backend call if data cached; otherwise GET /positions?portfolio_id=X or GET /evaluation-periods?portfolio_id=X | Re-render content area with signals, positions, or performance view |
| **Click ticker for drill-down** | Open modal, show loading spinner | GET /signals/{id}/comments | Render comment cards with annotations via signal_comments junction; modal title shows ticker + signal type + confidence |
| **Click "Refresh"** | Re-fetch portfolios and signals | GET /portfolios, GET /signals | Update UI with latest data; show toast: "Data refreshed" |
| **Hover over sparkline** | Show tooltip with date and value (confidence or price depending on sparkline) | No backend call (data already in /signals/history and /prices responses) | Display tooltip positioned near cursor |

**Page Reload Recovery Flow:**
1. On page load, GET /status returns `active_run_id` (non-null if a run is in progress)
2. If `active_run_id` is non-null:
   - Disable "Run Analysis" button
   - Begin polling GET /runs/{active_run_id}/status every 10 seconds
   - Show progress indicator at current phase
3. On first poll response:
   - If status='completed': show results summary overlay (signals_created, positions_opened, exits_triggered, warnings), auto-refresh data (GET /portfolios, GET /signals), re-enable button
   - If status='failed': show error toast with error_message, re-enable button
   - If status='running': continue polling with progress indicator

**Schwab Degradation (Phase 1):** When Schwab API is unavailable, monitoring is skipped for affected tickers/positions. This is an accepted risk for Phase 1. The `warnings` field on `analysis_runs` (see Appendix B) captures non-fatal degradation events, which surface in the results summary overlay. Single-user context means the user will also see auth errors in backend logs.

**Warnings Rendering Rules (Results Summary Overlay):**
- **0 warnings** (`warnings` is NULL): Omit the warnings section entirely from the results summary
- **1-3 warnings**: Display as inline bulleted list directly in the results summary overlay, each showing the warning `message` text
- **4+ warnings**: Show first 3 inline with an "and N more..." expandable link that reveals the full list on click
- Each warning displays its `type` as a subtle label prefix (e.g., "Schwab Stock: NVDA monitoring skipped after 3 retries")

**Technical Stack:**
- **Framework**: Vue.js 3 (Composition API)
- **HTTP Client**: Axios or native fetch()
- **Charts**: Chart.js or lightweight sparkline library (e.g., vue-sparklines)
- **Styling**: Tailwind CSS or Bootstrap for rapid prototyping
- **Deployment**: Local dev server (`npm run serve`) during Phase 1; no production build needed until Phase 2

**See Also:**
- **Section 4.2**: Visualization functional requirements (FR-004 through FR-008; FR-009 deferred to Phase 2)
- **Section 4.3**: Integration functional requirements (FR-012, FR-050)
- **Appendix C**: REST API contract for request/response formats expected by dashboard

---

### 3.6 Integration Patterns

This section describes how system components communicate and handle cross-cutting concerns like authentication, data consistency, and error boundaries.

#### 3.6.1 Component Communication

All inter-component communication uses **synchronous HTTP/JSON over REST**, with no message queues, event buses, or pub/sub patterns:

```
Vue Dashboard ────HTTP GET/POST (JSON)───▶ FastAPI Backend ────SQL queries───▶ SQLite Database
                                                  │
                                                  ├──HTTPS──▶ Reddit API (PRAW)
                                                  ├──HTTPS──▶ OpenAI API (GPT-4o-mini + vision)
                                                  ├──HTTPS──▶ yfinance API (stock prices)
                                                  └──HTTPS──▶ Schwab API (real-time pricing, options data)
```

**Communication Characteristics:**
- **Asynchronous for analysis**: POST /analyze returns HTTP 202 immediately; frontend polls GET /runs/{id}/status every 10 seconds for progress updates
- **Synchronous for all other endpoints**: Standard request/response; no webhooks, no WebSockets
- **RESTful JSON**: All payloads use JSON serialization
- **Timeout handling**: Frontend sets 30-second timeout for standard endpoints; polling uses 10-second intervals with no overall timeout (run completes or fails)
- **Error propagation**: Backend returns structured errors; frontend displays user-friendly messages
- **Backend connectivity errors**: On page load failure (all requests fail): persistent top-level banner "Unable to connect to backend. Is the server running?" with "Retry" button. On individual request failure after page load: inline error in content area "Failed to load [data type]" with retry option
- **Concurrency control**: Single analysis run enforced; POST /analyze returns HTTP 409 if a run is already in progress. Background thread uses isolated SQLite connection (WAL mode enables concurrent reads)

#### 3.6.2 Authentication & Security

The system uses **differentiated authentication** based on API requirements:

| Integration | Authentication Method | Configuration | Security Notes |
|-------------|----------------------|---------------|----------------|
| **Dashboard → Backend** | None (unauthenticated) | N/A | Acceptable: local deployment, single user, experimental tool; no sensitive data exposure risk |
| **Backend → Reddit** | OAuth2 via PRAW | Environment variables: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | Required by Reddit API; credentials stored in `.env` file (excluded from git via `.gitignore`) |
| **Backend → OpenAI** | API key (Bearer token) | Environment variable: `OPENAI_API_KEY` | Standard OpenAI auth; key stored in `.env`; monthly spend tracked via OpenAI dashboard |
| **Backend → yfinance** | None (public API) | N/A | Free public API; no rate limits enforced (best-effort availability) |
| **Backend → Schwab** | OAuth 2.0 (Authorization Code Grant) | Environment variables: `SCHWAB_CLIENT_ID`, `SCHWAB_CLIENT_SECRET`, `SCHWAB_CALLBACK_URL`; Token storage: `./data/schwab_token.json` (excluded from git) | Requires funded Schwab brokerage account; free API access; see Schwab OAuth Lifecycle below |

**Schwab OAuth 2.0 Lifecycle:**

Schwab uses Authorization Code Grant (requires browser-based user consent), distinct from Reddit's Script/Password grant (which only needs `.env` credentials):

| Phase | Process | Frequency |
|-------|---------|-----------|
| **Initial Setup** | CLI setup script: (1) opens browser to Schwab authorization URL, (2) user logs in and consents, (3) Schwab redirects to callback URL with authorization code, (4) script exchanges code for access token + refresh token, (5) tokens saved to `./data/schwab_token.json` | One-time manual step |
| **Normal Operation** | Access token (30-minute TTL) refreshed proactively before expiration using stored refresh token. On 401 response: immediate token refresh and retry | Automatic, transparent |
| **Refresh Token Renewal** | Refresh token has 7-day TTL. If user runs /analyze at least once per week, refresh token auto-renews. If refresh token expires (7+ days of inactivity): log error, instruct user to re-authenticate via CLI script | Automatic if active; manual re-auth if lapsed |
| **Graceful Degradation** | If Schwab API unavailable (auth failure or service outage): retry with exponential backoff (1s, 2s, 4s, max 15s), up to 3 attempts; if all fail: log warning, skip monitoring for affected tickers/positions (retry on next /analyze run) | Automatic retry + skip |

**Token Storage:** File-based at `./data/schwab_token.json` (not database, not `.env`). File contains `access_token`, `refresh_token`, `expires_at`, `refresh_expires_at`. Added to `.gitignore`.

**Phase 2 Considerations (Real Trading):**
- Add dashboard authentication (basic auth or API key)
- Secure .env file with restricted file permissions (chmod 600)
- Consider vault solution (e.g., HashiCorp Vault) for API keys if deploying to cloud

#### 3.6.3 Data Consistency Strategies

The system enforces consistency through database constraints and application-level checks:

| Consistency Concern | Solution | Enforcement Level |
|---------------------|----------|-------------------|
| **Duplicate comments** | Check `reddit_id` exists before AI analysis; if exists, skip OpenAI call and reuse stored annotations | Application logic (Python) + SQLite UNIQUE constraint on reddit_id |
| **Duplicate signals** | Unique constraint on `(ticker, signal_type, signal_date)`; daily rollup model means first run creates signal, subsequent runs upsert (update existing) | SQLite UNIQUE constraint + application upsert logic |
| **Duplicate positions** | Check `signal.position_opened` flag before creating position; once true, never create another position for this signal | Application logic (Python) |
| **Stale price data** | Fetch intraday prices via Schwab API (real-time quote + 5-min candles); for multi-day gaps use yfinance daily OHLC for missed days then Schwab for today; if both fail, log warning and skip monitoring for affected tickers; retry on next /analyze run | Application logic with tiered fallback |
| **Portfolio cash availability** | Deduct position_size from portfolio.cash_available on position open; return to cash on position close; enforce cash_available ≥ 0 before opening new position | Application logic (Python) + SQLite CHECK constraint |
| **Schema evolution** | Additive migrations only Phase 1: use ALTER TABLE ADD COLUMN with defaults for new columns, standard CREATE TABLE for new tables. Destructive changes (rename/drop columns) require database rebuild with documented data loss acknowledgment. No migration framework needed — simple SQL scripts suffice. Phase 2 will use Alembic or similar migration tool | Manual rebuild (drop tables, re-run schema.sql) |

**Trade-off: ACID vs Availability**
- SQLite provides ACID guarantees via transactions; WAL mode enables concurrent reads during background analysis
- Batch-of-5 commits during Phase 3 (AI analysis) minimize data loss on failure: if analysis fails at comment 450, the first 445 are preserved (max loss: 5 comments' API cost). On retry, check if comment already analyzed before calling OpenAI; if so, reassign to current run and skip
- Checkpoint transactions at phase boundaries (Phase 4-5, Phase 6, Phase 7) ensure each major phase is atomic
- Analysis runs tracked in analysis_runs table with status ('running', 'completed', 'failed') for crash recovery

#### 3.6.4 Error Boundary Definitions

The system defines **four error boundary tiers**, each with different failure propagation behavior:

| Boundary Tier | Scope | Failure Strategy | Example Scenario |
|---------------|-------|------------------|------------------|
| **Tier 1: Hard Fail (Abort Run)** | Critical path failures that prevent meaningful results | Log error, rollback SQLite transaction, return HTTP 5xx, user sees error message and retries manually | Reddit API outage (can't fetch posts), SQLite write failure (can't persist results) |
| **Tier 2: Retry with Backoff** | Transient external API failures | Exponential backoff (1s, 2s, 4s, 8s, max 30s), retry up to 3-5 times, continue if successful, fail to Tier 1 if all retries exhausted | OpenAI rate limit (429 response), network timeout on yfinance call |
| **Tier 3: Graceful Degradation** | Non-critical data enrichment failures | Retry 3 times with backoff, if all fail: log warning, continue with NULL/default value, analysis proceeds | Image analysis failure (continue without image context), single comment AI failure (skip comment, use remaining comments for signal detection) |
| **Tier 4: Log and Continue** | Expected variation, not actual failures | Log info message, continue processing | Comment deduplication (reddit_id already exists), yfinance returns no price data for obscure ticker (skip monitoring, retry next run) |

**Error Boundary Decision Tree:**
```
Error occurs
├─ Is it on critical path (Reddit fetch, SQLite write)?
│  └─ YES → Tier 1: Hard Fail (abort run, return 5xx)
│
├─ Is it a transient external API error (rate limit, timeout)?
│  └─ YES → Tier 2: Retry with Backoff (3-5 retries, then fail to Tier 1)
│
├─ Is it enrichment data (images, author trust, single comment)?
│  └─ YES → Tier 3: Graceful Degradation (retry 3x, then continue with NULL)
│
└─ Is it expected variation (deduplication, missing data)?
   └─ YES → Tier 4: Log and Continue (info log, no user impact)
```

**Logging Strategy:**
- All errors logged with full stack trace to `logs/backend.log`
- Structured logging (JSON format) for easy parsing during debugging
- Log levels: DEBUG (verbose data), INFO (normal operation), WARNING (degraded mode), ERROR (failure), CRITICAL (abort run)

**Monitoring During Phase 1:**
- Manual log review after each /analyze run
- No automated alerting (experimental tool, single user)
- Phase 2 will add monitoring dashboard (e.g., Grafana) if tool graduates to real trading

---

## 4. Functional Requirements

### 4.1 Trend Detection (Must Have)

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-001 | **Signal-Based Trend Detection** — Identify trading signals using two detection methods: Quality signals (substantive reasoning from multiple users with high AI confidence) and Consensus signals (high comment volume with strong directional alignment from many distinct users). See FR-015, FR-016, FR-040 for detailed algorithms. | Must | qc-1-rm-01, qc-sd-2-007 |
| FR-002 | **Sentiment Analysis with Sarcasm Handling** — Use OpenAI to analyze WSB comment sentiment, correctly interpreting sarcasm, memes, and WSB-specific language (diamond hands, tendies, etc.) | Must | Vision Doc, qc-1-sd-001 |

### 4.2 Visualization (Must/Should Have)

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-004 | **Trend Ranking Display** — Present trends as ranked list of tickers ordered by composite trend strength | Must | qc-1-ux-03 |
| FR-005 | **Signal Strength Indicator** — Display confidence/intensity metric for each trend | Must | qc-1-ux-01 |
| FR-006 | **Time Context** — Show when trend emerged and whether accelerating/decelerating | Should | qc-1-ux-01 |
| FR-007 | **Evidence Drill-Down** — Display source comments with AI annotations showing: sarcasm detection, reasoning presence, sentiment classification, and confidence level. Original text always visible alongside interpretation. | Must | qc-1-ux-01, vision-clarity-2026-02-03 |
| FR-008 | **Dual Sparkline Visualization** — Show two compact sparklines per signal card: (1) signal confidence history (7-14 days, from GET /signals/history) and (2) stock price trajectory (7-14 days, from yfinance via GET /prices/{ticker}). Adaptive rendering: ≤2 data points shows dot(s); 3+ points renders full sparkline. | Should | qc-1-ux-03, Phase-1-sparklines-amendment |
| FR-009 | **Watchlist Filtering** — ~~Optional filter to show only user-specified tickers~~ **Deferred to Phase 2.** Not needed for initial hypothesis testing. | Deferred | qc-1-ux-03, HITL-Phase-1 |

### 4.3 Integration (Must Have)

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-010 | **Reddit API Integration** — Fetch data directly from Reddit API using PRAW library. Retrieve top 10 hot posts, up to 1000 comments per post, prioritize top 50 comments per post using financial keywords, author trust, and engagement scoring. | Must | qc-1-sd-002, PRD-arch-2026-02-04 |
| FR-011 | **On-Demand Analysis** — Run analysis when user triggers, not on schedule | Must | qc-1-rm-03, qc-1-arch-002 |
| FR-012 | **Web Dashboard Interface** — Primary interface is a Vue-based web dashboard with data loading on page open, manual refresh button, and interactive exploration. No auto-polling (on-demand usage pattern). Default view: Stock/Quality portfolio. | Must | qc-1-sd-003, qc-2-dev-004 |
| FR-050 | **Default Portfolio View** — Dashboard loads with Stock/Quality portfolio selected by default. User can switch to other portfolios (Stock/Consensus, Options/Quality, Options/Consensus) via tabs. No state persistence needed — always resets to Stock/Quality on page load. | Must | HITL-2026-02-04 |
| FR-013 | **SQLite Storage** — Store processed analysis results and historical data in SQLite database | Must | qc-1-arch-001 |
| FR-014 | **Automated Price Validation** — Integrate yfinance to track actual price movements for prediction validation | Must | qc-2-dev-005 |
| FR-034 | **AI-Based Ticker Extraction** — Extract ticker symbols as part of AI comment analysis (not regex). AI identifies tickers from context (e.g., "apple" → AAPL), normalizes to uppercase, and returns as array. Handles WSB slang and distinguishes tickers from common words. | Must | PRD-review-2026-02-03 |
| FR-038 | **Comment Deduplication** — Before AI analysis, check if comment's `reddit_id` exists in database. If exists, skip AI call and use stored annotations. If new, analyze and store. All comments (new + existing) included in signal aggregation. Saves API costs on overlapping hot posts. | Must | PRD-review-2026-02-03 |
| FR-039 | **Daily Signal Rollup** — Signals aggregate per ticker per calendar day (UTC). First run creates signal; subsequent runs update it with additional comments. One signal per ticker/signal_type/day. Position opens on first run meeting threshold; subsequent runs refine but don't duplicate positions. | Must | PRD-review-2026-02-03 |

### 4.4 Signal Types (Must Have)

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-015 | **Quality Signal Detection** — Identify signals when ≥2 distinct users post substantive, non-sarcastic arguments with explicit reasoning about the same ticker in the same direction. Comments must have `has_reasoning=true`, `sarcasm_detected=false`, and `ai_confidence≥0.6`. Thresholds configurable via `system_config`. | Must | vision-clarity-2026-02-03, HITL-2026-02-04 |
| FR-016 | **Consensus Signal Detection** — Identify signals when ≥30 comments mention the same ticker with ≥70% directional alignment (bullish or bearish). Requires ≥8 distinct users to prevent spam. Neutral comments excluded from alignment calculation. Thresholds configurable via `system_config`. | Must | vision-clarity-2026-02-03, HITL-2026-02-04 |
| FR-040 | **Signal Confidence Calculation** — Calculate signal confidence (0-1) based on: (1) volume above threshold (more = higher), (2) alignment strength (% above minimum), (3) average AI confidence of contributing comments, (4) average author trust score. Formula weights configurable via `system_config`. | Must | HITL-2026-02-04 |
| FR-017 | **Separate Signal Tracking** — Track Quality and Consensus signals as distinct entities with independent performance metrics. When signals conflict, record both without pre-judgment. | Must | vision-clarity-2026-02-03 |
| FR-018 | **Benchmark Comparison** — Display signal performance relative to S&P 500 benchmark over rolling 30-day periods. | Must | vision-clarity-2026-02-03 |
| FR-019 | **Emergence Flag Detection** — Flag signals where ticker was cold (<3 mentions in past 7 days) but suddenly appears (13+ mentions from 8+ distinct users in current snapshot). Emergence is a flag on any signal type, not a separate signal. | Must | vision-clarity-2026-02-03 |
| FR-020 | **Historical Comparison** — FastAPI must compare incoming ticker data against 7-day historical baseline in SQLite to detect emergence. Reddit API provides current snapshot only. | Must | vision-clarity-2026-02-03 |
| FR-032 | **Emergence Activation Threshold** — Emergence detection requires minimum 7 days of historical data. During Days 1-7, `is_emergence` is NULL/disabled for all signals. Day 8+ activates full emergence detection. Dashboard displays activation countdown during warmup period. | Must | HITL-2026-02-03 |
| FR-033 | **Emergence Weighting** — Emergence flag does not affect position sizing in Phase 1. Track emergence as metadata only. After 30-60 days, analyze emergence vs. non-emergence performance to determine if weighting adjustment is warranted for Phase 2. | Must | HITL-2026-02-03 |
| FR-021 | **Comment Annotation Storage** — Store each analyzed comment with permanent AI annotations: sentiment (bullish/bearish/neutral), sarcasm flag, reasoning flag, and confidence level (0-1). | Must | vision-clarity-2026-02-03 |
| FR-022 | **Annotation Pattern Analysis** — ~~Enable querying annotation patterns against prediction outcomes to assess AI interpretation accuracy over time.~~ **Deferred to Phase 2.** Underlying data (comments annotations + position outcomes) exists for manual SQL querying during Phase 1. No dedicated endpoint or UI needed until hypothesis is validated. | Deferred | vision-clarity-2026-02-03 |

**Signal Detection Logic:**

```
QUALITY SIGNAL fires when:
├── ticker has ≥ quality_min_users (default: 2) distinct users
├── each user has ≥1 comment where:
│   ├── has_reasoning = true
│   ├── sarcasm_detected = false
│   ├── ai_confidence ≥ quality_min_confidence (default: 0.6)
│   └── sentiment matches direction (all bullish OR all bearish)
└── direction = unanimous sentiment of qualifying comments

CONSENSUS SIGNAL fires when:
├── ticker has ≥ consensus_min_comments (default: 30) mentions
├── from ≥ consensus_min_users (default: 8) distinct users
├── with ≥ consensus_min_alignment (default: 70%) in same direction
│   (neutral comments excluded from alignment calc)
└── direction = majority sentiment
```

**Confidence Calculation Formula:**

```
signal_confidence =
    (volume_score × weight_volume) +
    (alignment_score × weight_alignment) +
    (avg_ai_confidence × weight_ai_confidence) +
    (avg_author_trust × weight_author_trust)

Where:
├── volume_score = min(1.0, actual_count / (threshold × 3))
│   For Quality signals: actual_count = distinct qualifying users; threshold = quality_min_users (default 2)
│     Example: 4 users / (2 × 3) = 0.67
│   For Consensus signals: actual_count = total non-neutral comments; threshold = consensus_min_comments (default 30)
│     Example: 45 comments / (30 × 3) = 0.50
├── alignment_score = (actual_alignment - min_alignment) / (1.0 - min_alignment)
│   Example: (0.85 - 0.70) / (1.0 - 0.70) = 0.50
├── avg_ai_confidence = mean of contributing comments' ai_confidence
├── avg_author_trust = mean of contributing comments' author_trust_score

Default weights: volume=0.25, alignment=0.25, ai_confidence=0.30, author_trust=0.20
```

### 4.5 Portfolio Management (Must Have)

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-023 | **Confidence-Weighted Position Sizing** — Allocate position sizes based on signal confidence level. Higher confidence signals receive larger allocations within risk limits. Stocks use confidence multipliers (0.5×/0.75×/1.0×); options use fixed 2% of portfolio. | Must | HITL-2026-02-03, HITL-2026-02-04 |
| FR-024 | **Separate Dual-Signal Positions** — When both Quality and Consensus signals fire on the same ticker, open positions in all 4 portfolios (one per portfolio). Conflicting directions are valid (e.g., Quality=bullish, Consensus=bearish results in long + short positions). Enables isolated performance analysis per signal type. | Must | HITL-2026-02-03 |
| FR-025 | **Maximum Concurrent Positions** — Limit each portfolio to 10 concurrent positions maximum (40 total across all portfolios). When limit reached: (1) find lowest-confidence open position in that portfolio, (2) if new signal confidence exceeds lowest by >0.1, close lowest and open new position, (3) else reject new signal. Safeguard: never replace a position with unrealized gain >+5%. | Must | HITL-2026-02-03 |
| FR-035 | **Four-Portfolio Structure** — Maintain 4 independent paper trading portfolios to isolate performance by instrument type and signal type: (1) Stocks/Quality, (2) Stocks/Consensus, (3) Options/Quality, (4) Options/Consensus. Each portfolio has separate capital ($100k each), position limits (10 each), and performance tracking. When a signal fires, open positions in both relevant portfolios (stock and option) for that signal type. | Must | PRD-review-2026-02-03 |
| FR-036 | **Instrument Type Selection** — For each signal, open positions in both instrument types: stock position (long only for Phase 1; bearish signals recorded but no short stock positions opened) and options position (call for bullish, put for bearish). Track independently for comparative analysis. Phase 2 may add short selling based on Phase 1 bearish signal accuracy data. | Must | PRD-review-2026-02-03, HITL-Phase-1 |
| FR-037 | **Options Parameters** — Options positions use: (1) delta-based strike selection targeting ~0.30 delta, (2) 14-21 DTE expiration, (3) 2% of portfolio per position, (4) premium-based exit strategy with partial take-profit and trailing stop, (5) Schwab API for options data (confirmed; OAuth 2.0 Authorization Code Grant, see Section 3.6.2). | Must | PRD-review-2026-02-03, HITL-2026-02-04, qc-rm-2-007 |

**Position Sizing Formula (Stocks):**

```
Base allocation = portfolio_value / 20  (assumes ~10 max positions + buffer)

Position size = base_allocation × confidence_multiplier

Confidence multiplier:
├── 0.50 - 0.60 confidence: 0.50× (half position)
├── 0.60 - 0.75 confidence: 0.75× (three-quarter position)
└── 0.75 - 1.00 confidence: 1.00× (full position)

Maximum position size: 15% of portfolio (risk control)
Minimum position size: 2% of portfolio (meaningful allocation)
```

**Position Sizing Formula (Options):**

```
Position size = portfolio_value × 0.02  (fixed 2% of portfolio)

Contract selection:
├── Direction: Call (bullish signal) or Put (bearish signal)
├── Strike: Nearest strike with delta ~0.30
│   └── Calls: 0.25-0.35 delta (OTM)
│   └── Puts: -0.25 to -0.35 delta (OTM)
├── Expiration: 14-21 DTE (prefer ~17-18 DTE if available)
└── Contracts: floor(position_size / (premium × 100))

Example:
├── Portfolio: $100,000
├── Position size: $2,000 (2%)
├── Premium: $3.50 per contract
└── Contracts: floor(2000 / 350) = 5 contracts
```

**Strike Selection Algorithm (deterministic):**
1. Fetch options chain from Schwab for ticker
2. Filter expirations: 14 <= DTE <= 21
3. If no expirations in window: skip position (do not open); log warning "No valid expiration in 14-21 DTE window for {ticker}"
4. If multiple expirations: prefer closest to 17 DTE (tiebreak: prefer later expiration)
5. Within selected expiration:
   a. Bullish signal → scan CALL strikes, target delta closest to +0.30
   b. Bearish signal → scan PUT strikes, target delta closest to -0.30
   c. Acceptable delta tolerance:
      - Calls: [+0.15, +0.50]
      - Puts: [-0.50, -0.15]
   d. If best delta outside tolerance: skip position (do not open); log warning "No strike with acceptable delta for {ticker} ({option_type})"
6. Record selected delta, DTE, and strike price on the position

**Options Data Source:**

Primary: Schwab API (confirmed)
- Provides real-time options chains with greeks (delta, theta, IV)
- OAuth 2.0 Authorization Code Grant authentication (see Section 3.6.2 for lifecycle)
- Free with funded brokerage account
- Token stored in `./data/schwab_token.json`

**No fallback required.** If Schwab API is temporarily unavailable, log warning and skip options monitoring for affected positions (retry on next /analyze run). Black-Scholes estimation removed from Phase 1 scope per intraday monitoring decision.

### 4.6 Exit Strategy — Stocks (Must Have)

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-026 | **Bracket Exit Strategy (Stocks)** — Implement three-condition exit: stop-loss at -10%, take-profit trigger at +15%, and time-based exit. Thresholds calibrated for typical WSB stock volatility (3-8% daily moves). | Must | HITL-2026-02-03 |
| FR-027 | **Partial Take-Profit** — When +15% gain reached, exit 50% of position and apply trailing stop to remainder. Locks in gains while preserving upside. | Must | HITL-2026-02-03 |
| FR-028 | **Trailing Stop** — After partial take-profit, set trailing stop at -7% from peak price for remaining position. Exit triggers when price drops 7% from highest point reached. | Must | HITL-2026-02-03 |
| FR-029 | **Gain-Based Time Extension** — Extend holding window based on unrealized gains: base 5 days if <+5%, extend to 7 days if +5-15% (with breakeven stop), extend to 10 days for trailing remainder after take-profit. | Must | HITL-2026-02-03 |
| FR-030 | **Breakeven Stop Promotion** — When position reaches +5% gain and Day 5, raise stop-loss to entry price (breakeven) to protect gains. | Must | HITL-2026-02-03 |
| FR-031 | **Intraday Price Monitoring** — Track intraday prices via Schwab API (real-time quotes + 5-minute candles) to detect stop-loss and take-profit triggers with intraday granularity. For multi-day gaps between runs: fetch yfinance daily OHLC for missed days, then Schwab 5-min candles for current day. Check exit conditions against each candle's high/low in chronological order. Runs automatically as part of `/analyze` pipeline (Phase 6). All exit strategy thresholds configurable via system_config (see Section 3.3.4). | Must | HITL-2026-02-03, Phase-1-intraday-amendment |
| FR-049 | **Price Monitoring Schedule** — Position monitoring executes automatically at end of each `/analyze` run. Can run at any time (not limited to after-hours). Schwab API provides real-time quotes for stocks and options premiums; yfinance provides daily OHLC fallback for stocks. If Schwab unavailable: fall back to yfinance for stocks, skip options monitoring. If price data unavailable for a position, log warning and skip (will retry on next run). All timestamps stored in UTC; display converted to ET. Hold days calculated as calendar days (not trading days). | Must | HITL-2026-02-04, Phase-1-intraday-amendment |

**Exit Strategy Decision Tree:**

```
ENTRY: Signal fires → Open position (confidence-weighted size)

DAILY MONITORING:
├── Price ≤ -10% from entry?
│   └── EXIT 100% (stop-loss)
│
├── Price ≥ +15% from entry? (first time)
│   └── EXIT 50% (take-profit)
│       → Set trailing stop at -7% from peak
│       → Extend window to Day 10
│
├── Trailing stop active AND price ≤ peak - 7%?
│   └── EXIT remainder (trailing stop)
│
├── Price ≥ +5% AND Day ≥ 5? (no take-profit yet)
│   └── Raise stop to breakeven
│       → Extend window to Day 7
│
├── Day = 5 AND gain < +5%?
│   └── EXIT 100% (time stop)
│
├── Day = 7 AND gain +5-15% AND shares_remaining = shares? (extended, no take-profit)
│   └── EXIT 100% (extended time stop)
│
└── Day = 10? (trailing remainder)
    └── EXIT remainder (max time stop)
```

### 4.7 Exit Strategy — Options (Must Have)

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-041 | **Premium-Based Stop-Loss (Options)** — Exit 100% of contracts if premium drops to -50% from entry. Options are inherently volatile; wider stop than stocks. | Must | HITL-2026-02-04 |
| FR-042 | **Premium-Based Take-Profit (Options)** — When premium reaches +100% from entry, exit 50% of contracts and apply trailing stop to remainder. Locks in gains while allowing for larger moves. | Must | HITL-2026-02-04 |
| FR-043 | **Trailing Stop (Options)** — After partial take-profit, set trailing stop at -30% from peak premium for remaining contracts. Wider than stocks due to options volatility. | Must | HITL-2026-02-04 |
| FR-044 | **Expiration Protection** — Exit 100% of remaining contracts when DTE ≤ 2 days to avoid expiration risk, assignment, and rapid theta decay. | Must | HITL-2026-02-04 |
| FR-045 | **Time Stop (Options)** — Exit 100% of remaining contracts after 10 days of hold, regardless of P/L. Prevents holding through excessive theta decay. | Must | HITL-2026-02-04 |
| FR-048 | **Options Position Monitoring** — Daily monitoring checks all open options positions against exit conditions. Fetch current premium via options data source. Check conditions in priority order: (1) expiration protection, (2) stop-loss, (3) take-profit trigger, (4) trailing stop, (5) time stop. Update peak_premium tracking after each check. | Must | HITL-2026-02-04 |

**Options Monitoring Algorithm:**

```
FOR each open options position:
    1. FETCH current data:
       - current_premium = last trade price or mark price
       - current_dte = expiration_date - today
       - hold_days = today - entry_date

    2. CHECK exit conditions (in priority order):

       a. EXPIRATION PROTECTION (highest priority)
          IF current_dte <= 2:
              EXIT 100% of contracts_remaining
              exit_reason = 'expiration'
              CONTINUE to next position

       b. STOP-LOSS
          premium_change_pct = (current_premium - entry_price) / entry_price
          IF premium_change_pct <= -0.50:
              EXIT 100% of contracts_remaining
              exit_reason = 'stop_loss'
              CONTINUE to next position

       c. TAKE-PROFIT (first trigger only)
          IF contracts_remaining = contracts AND premium_change_pct >= 1.00:
              contracts_exited = floor(contracts_remaining * 0.5)
              INSERT INTO position_exits (position_id, exit_date, exit_price, exit_reason, quantity_pct, contracts_exited, realized_pnl)
                VALUES (position.id, today, entry_price * 2.00, 'take_profit', 0.5, contracts_exited, (entry_price * 2.00 - entry_price) * contracts_exited * 100)
              UPDATE positions SET contracts_remaining = contracts_remaining - contracts_exited
              SET trailing_stop_active = TRUE
              SET peak_premium = current_premium
              -- Do not exit remainder yet; continue monitoring

       d. TRAILING STOP (only if partial exit done)
          IF trailing_stop_active:
              UPDATE peak_premium = MAX(peak_premium, current_premium)
              trailing_threshold = peak_premium * 0.70  -- 30% below peak
              IF current_premium <= trailing_threshold:
                  EXIT 100% of contracts_remaining
                  exit_reason = 'trailing_stop'
                  CONTINUE to next position

       e. TIME STOP
          IF hold_days >= 10:
              EXIT 100% of contracts_remaining
              exit_reason = 'time_stop'
              CONTINUE to next position

    3. UPDATE position record:
       - peak_premium (if current > previous peak and no exit)
```

**Options Monitoring Data Requirements:**

| Data Point | Source | Frequency |
|------------|--------|-----------|
| Current premium | Schwab API (no fallback; skip if unavailable) | Intraday (on each /analyze run) |
| Expiration date | Stored at entry | Static |
| Entry premium | Stored at entry | Static |
| Peak premium | Calculated during monitoring | Updated daily |
| Contracts remaining | Tracked after partial exits | Updated on exit |

**Options vs Stocks Monitoring Differences:**

| Aspect | Stocks | Options |
|--------|--------|---------|
| Price source | Schwab real-time quote + 5-min candles; yfinance daily OHLC fallback | Schwab options premiums + greeks (no fallback; skip if unavailable) |
| Expiration check | N/A | Check DTE ≤ 2 |
| Breakeven stop | Yes (Day 5, +5%) | No |
| Time extension | Variable (5/7/10 days) | Fixed 10 days max |
| Trailing threshold | -7% from peak | -30% from peak |

### 4.8 Reddit Integration (Must Have)

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-046 | **Post Image Analysis** — When a Reddit post contains an image (i.redd.it, imgur, preview.redd.it), analyze the image using GPT-4o-mini vision API to extract visual context (charts, earnings calendars, financial data). Include image description in comment analysis prompt. Analysis is synchronous (completes before comment analysis begins). On failure, retry up to 3 times with exponential backoff (2s, 5s, 10s). If all retries fail, log warning, set `image_analysis=NULL`, and continue with comment analysis. Image context is supplementary, not required. | Must | PRD-arch-2026-02-04, HITL-2026-02-04 |
| FR-047 | **Author Trust Database** — Maintain historical author data in SQLite `authors` table. Track: first_seen, total_comments, high_quality_comments, total_upvotes, avg_conviction_score, avg_sentiment_accuracy, last_active. Calculate trust score (0-1) based on tenure, quality ratio, and historical accuracy (see Appendix F for formulas). Update after each analysis run and after prediction outcomes resolve. | Must | PRD-arch-2026-02-04 |

**Options Exit Strategy Decision Tree:**

```
ENTRY: Signal fires → Buy calls (bullish) or puts (bearish)
       Strike: ~0.30 delta, Expiration: 14-21 DTE, Size: 2% of portfolio

DAILY MONITORING (checked in priority order):
├── DTE ≤ 2 days?
│   └── EXIT 100% (expiration protection) — highest priority
│
├── Premium ≤ -50% from entry?
│   └── EXIT 100% (stop-loss)
│
├── Premium ≥ +100% from entry? (first time, contracts_remaining = contracts)
│   └── EXIT 50% of contracts (take-profit)
│       → INSERT INTO position_exits
│       → Set trailing stop at -30% from peak premium
│       → Let remainder run
│
├── Trailing stop active AND premium ≤ peak - 30%?
│   └── EXIT remainder (trailing stop)
│
└── Day = 10 of hold?
    └── EXIT 100% (time stop)
```

**Options vs Stocks Exit Comparison:**

| Parameter | Stocks | Options | Rationale |
|-----------|--------|---------|-----------|
| Stop-loss | -10% | -50% | Options are more volatile |
| Take-profit trigger | +15% | +100% | Options have higher upside potential |
| Partial exit | 50% | 50% of contracts | Same approach |
| Trailing stop | -7% from peak | -30% from peak | Wider for volatility |
| Time limit | 5-10 days | 10 days or DTE-2 | Expiration adds constraint |
| Breakeven stop | Yes (+5%, Day 5) | No | Simpler for options |

---

## 5. Non-Functional Requirements

### 5.1 Accuracy & Measurement

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| NFR-001 | **Benchmark-Relative Performance** — Measure success as aggregate portfolio performance vs S&P 500, not individual prediction accuracy. Target: beat S&P by 10% per 30-day period. | Must (target) | vision-clarity-2026-02-03 |
| NFR-002 | **DTE-Driven Prediction Evaluation** — Predictions evaluated as simulated options positions using same exit conditions as real positions. Lifecycle typically 5-21 days based on option DTE and exit triggers | Must | qc-1-rm-02 |
| NFR-003 | **30-Day Evaluation Periods** — Assess signal performance over rolling 30-day windows rather than per-prediction accuracy | Must | vision-clarity-2026-02-03 |

### 5.2 Performance & Usability

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| NFR-004 | **≤30 Minute Analysis Time** — Complete full analysis within 30 minutes. If exceeded, log warning but continue processing. Optimize in Phase 2 if consistently slow. Hard timeout: if an analysis run exceeds 60 minutes, set status='failed' with error_message='Run timed out after 60 minutes'. Cancel mechanism deferred to Phase 2. | Should | qc-1-rm-03 |
| NFR-005 | **3x Daily Usage** — Support on-demand usage up to ~3 times daily | Should | qc-1-rm-03 |
| NFR-006 | **Desktop Compatibility** — Optimized for desktop browser (no mobile) | Must | qc-1-ux-02 |
| NFR-007 | **Simple, Intuitive UI** — Dashboard usable without training, with clear visual hierarchy and inline help where needed | Must | qc-1-sd-003 |

### 5.3 System Characteristics

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| NFR-008 | **Experimental Flexibility** — Design for iteration, not production robustness | Must | Vision Doc |
| NFR-009 | **Cost Awareness** — Keep OpenAI costs reasonable (~$45/month with GPT-4o-mini analyzing 500 comments per run). Track costs via logging; log warnings if monthly costs exceed $60. No hard limit enforcement for Phase 1. | Should | qc-2-dev-002 |
| NFR-010 | **Single-User Design** — No authentication or multi-user support needed | Must | Vision Doc |

---

## 6. Technical Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Data Acquisition** | PRAW + Reddit OAuth2 | Native Python library, direct control, no external dependency |
| **AI Analysis** | OpenAI GPT-4o-mini | Cost-effective (~$45/month), good at sarcasm |
| **Backend API** | FastAPI (Python) | Fast, modern Python API framework; integrates with existing analysis code |
| **Storage** | SQLite | Embedded database, zero-config, ideal for single-user local-first deployment |
| **Frontend** | Vue.js | Reactive dashboard UI, component-based, good DX |
| **Real-Time Pricing** | Schwab API (OAuth 2.0) | Primary source for intraday stock quotes, 5-min candles, options premiums and greeks; free with funded brokerage account |
| **Historical Pricing** | yfinance | Free, well-established, no API key needed; fallback for stocks when Schwab unavailable; source for multi-day gap daily OHLC; source for sparkline price data |

### 6.1 Estimated Costs

| Item | Monthly Cost |
|------|--------------|
| OpenAI (GPT-4o-mini, ~500 comments/day) | ~$45 |
| Image analysis (GPT-4o-mini vision, ~10 images/run × 3 runs/day) | ~$1-2 |
| SQLite (embedded) | $0 |
| Schwab API (real-time quotes, options data) | $0 (free with funded account) |
| yfinance (historical prices, sparklines, fallback) | $0 (free) |
| **Total** | **~$46-47/month** |

### 6.2 Deployment (Phase 1)

| Component | Deployment | Notes |
|-----------|------------|-------|
| **SQLite** | File-based (`./data/wsb.db`) | No server required. Schema initialization via Python script. Backup = copy file. |
| **FastAPI** | Local development server (`uvicorn`) | No production WSGI needed for Phase 1. |
| **Vue Dashboard** | Local dev server (`npm run serve`) | No production build or hosting required until Phase 2. |

---

## 7. Success Criteria

### 7.1 Primary Success Metric

| Metric | Target | Measurement |
|--------|--------|-------------|
| Benchmark-Relative Return | Beat S&P 500 by 10% | Simulated portfolio performance over 30-day periods |

**Definition of success:** Aggregate portfolio return exceeds S&P 500 return by 10% over a 30-day evaluation period. Success requires either signal type (Quality or Consensus) achieving this threshold.

### 7.2 Two Hypotheses Under Test

| Signal Type | Trigger | AI Task |
|-------------|---------|---------|
| **Quality Signals** | Multiple users posting substantive, non-sarcastic arguments with reasoning | Evaluate argument presence and coherence |
| **Consensus Signals** | High volume of users expressing aligned sentiment | Count and categorize directional agreement |

Both signal types are tracked independently. If they conflict on a ticker, both predictions are recorded. The experiment determines which (if either) is predictive.

### 7.3 Evaluation Framework

**Phase 1: Paper Trading (90 days minimum)**

Three consecutive 30-day evaluation periods with these graduation criteria:

| Criterion | Requirement |
|-----------|-------------|
| Win rate | At least 2 of 3 periods beat S&P benchmark |
| Downside protection | No single period loses more than 15% relative to benchmark |
| Consistency | Same signal type performs best across all three periods |
| Primary metric | Stocks portfolio for each signal type is the primary graduation metric; options portfolios provide supplementary data but do not factor into graduation decision |

All three conditions must be met before transitioning to real money. Graduation assessment uses stocks portfolios only. Options portfolios are tracked for supplementary analysis but do not determine pass/fail.

**Phase 2: Real Trading**

Entered only after Phase 1 criteria satisfied. Scope and position sizing determined by Phase 1 learnings.

### 7.4 Failure Conditions

The experiment is considered **failed** (hypothesis invalidated) if:

- Neither signal type beats the benchmark over 90 days
- Both signal types show inconsistent performance (no reliable pattern)
- Losses exceed risk tolerance during paper trading

**Failure is a valid outcome.** Learning that WSB signals are not predictive is valuable information.

### 7.5 Secondary Success Indicators

- Manual WSB data sorting time is eliminated
- AI successfully distinguishes substantive arguments from noise
- User develops trading intuition through feedback loop
- Tool surfaces signals before mainstream market awareness

---

## 8. Constraints and Assumptions

### 8.1 Constraints

| Constraint | Impact |
|------------|--------|
| Experimental scope | Accept technical debt; don't over-engineer |
| Single user | No auth, no multi-tenancy |
| Swing trading focus | No intraday signals |
| Cost consciousness | Use GPT-4o-mini; monitor API costs |
| Simple UI requirement | Provide intuitive dashboard with clear visual hierarchy |

### 8.2 Assumptions

| Assumption | Risk if Invalid |
|------------|-----------------|
| WSB sentiment contains predictive signal | Core hypothesis fails; experiment unsuccessful |
| AI can parse sarcasm/memes accurately | Analysis produces incorrect signals |
| Reddit API is accessible | PRAW handles rate limiting; API outages logged but no retry logic for Phase 1 |
| SQLite file is writable | Storage layer needs setup |
| Signals are daily rollups | Each calendar day produces one signal per ticker/type; multiple runs refine the same signal. Positions open once per signal. |

---

## 9. Out of Scope

Explicitly excluded from this project:

| Item | Rationale |
|------|-----------|
| Automated trading execution | Vision Doc explicit non-goal |
| Intraday/high-frequency signals | Swing trading focus |
| Other subreddits or social media | WSB-only scope |
| Mobile interface | Desktop-only |
| Alerting/notifications | On-demand usage pattern |
| Multi-user support | Personal tool |
| Production hardening | Experimental project |
| FR-022 Annotation Pattern Analysis | Deferred to Phase 2. Underlying data exists for manual SQL querying; dedicated endpoints and UI deferred until hypothesis validated |
| Phase 2 real trading parameters | Position sizes, risk limits, and portfolio allocation for real money will be defined in Phase 2 PRD based on paper trading performance data |

---

## 10. Traceability

### 10.1 Requirements to Questions

| Requirement | Source Question(s) |
|-------------|-------------------|
| FR-001 | qc-1-rm-01 |
| FR-002 | Vision Doc Section 5, 7; qc-1-sd-001 |
| FR-004, FR-008, FR-009 | qc-1-ux-03 |
| FR-005, FR-006, FR-007 | qc-1-ux-01 |
| FR-010 | qc-1-sd-002, PRD-arch-2026-02-04 |
| FR-046 | PRD-arch-2026-02-04 |
| FR-047 | PRD-arch-2026-02-04 |
| FR-011 | qc-1-rm-03, qc-1-arch-002 |
| FR-012 | qc-1-sd-003, qc-2-dev-004, brainstorm-2026-02-03 |
| FR-013 | qc-1-arch-001 |
| FR-014 | qc-2-dev-005 |
| FR-015, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021, FR-022 | vision-clarity-2026-02-03 |
| FR-023, FR-024, FR-025, FR-035, FR-036, FR-037 | HITL-2026-02-03, PRD-review-2026-02-03 (portfolio management) |
| FR-026, FR-027, FR-028, FR-029, FR-030, FR-031 | HITL-2026-02-03 (exit strategy — stocks) |
| FR-049 | HITL-2026-02-04 (price monitoring schedule) |
| FR-050 | HITL-2026-02-04 (default portfolio view) |
| FR-041, FR-042, FR-043, FR-044, FR-045 | HITL-2026-02-04 (exit strategy — options) |
| FR-048 | HITL-2026-02-04 (options position monitoring) |
| FR-032, FR-033 | HITL-2026-02-03 (emergence handling) |
| NFR-001, NFR-003 | vision-clarity-2026-02-03 |
| NFR-002 | qc-1-rm-02 |
| NFR-004, NFR-005 | qc-1-rm-03 |
| NFR-006 | qc-1-ux-02 |
| NFR-009 | qc-2-dev-002 |

### 10.2 ART Process Summary

| Round | Questions | Answered |
|-------|-----------|----------|
| Round 1 | 14 | 13 (1 inter-agent) |
| Round 2 | 5 | 5 |
| Round 3 | 0 | - |

**Agents Participated:**
- Requirements Manager (high)
- Software Developer (high)
- Software Architect (medium)
- UI/UX Designer (medium)

**Agents Inactive:**
- Product Manager (personal project, no business context)

### 10.3 Vision Clarity Session (2026-02-03)

Socratic inquiry session refined success criteria and experimental design:

| Topic | Original | Revised |
|-------|----------|---------|
| Success metric | 75% prediction accuracy | Beat S&P by 10% per 30-day period |
| Signal types | Single composite score | Two types: Quality and Consensus |
| Evaluation unit | Per-prediction accuracy | Aggregate portfolio performance |
| Transition criteria | Not specified | 3 periods, 2 of 3 winning, same signal type |
| Emergence detection | Not specified | Flag for cold tickers (<3 mentions/7d) suddenly appearing (13+ mentions, 8+ distinct users) |
| AI role | Implicit | Translator + Filter + Scorer; trust earned through 90-day verification |
| Evidence display | Show sample comments | Annotated comments with AI interpretation overlay |
| Annotation storage | Not specified | Permanent storage of sentiment, sarcasm, reasoning, confidence per comment |

**Source document:** `outputs/vision-clarity.md`

### 10.4 Portfolio & Exit Strategy Session (2026-02-03)

HITL session defined portfolio management and exit strategy parameters:

| Decision | Value | Rationale |
|----------|-------|-----------|
| Position sizing | Confidence-weighted | Higher confidence signals get larger allocations |
| Dual signal handling | Separate positions | Isolates signal type performance for analysis |
| Max concurrent positions | 10 | Balanced diversification for swing trading |
| Stop-loss | -10% | Accommodates WSB stock volatility (3-8% daily moves) |
| Take-profit trigger | +15% | 1.5:1 reward/risk; captures typical WSB momentum |
| Partial exit | 50% at take-profit | Locks gains while preserving upside |
| Trailing stop | -7% from peak | Protects remainder after partial exit |
| Breakeven promotion | +5% gain at Day 5 | Raises stop to entry price |
| Base time window | 5 days | Standard swing trading horizon |
| Extended window | 7 days | For +5-15% positions |
| Max window | 10 days | For trailing remainder after take-profit |
| Emergence weighting | No special weighting | Defer to data; analyze after 30-60 days |
| Emergence activation | 7-day minimum | Ensures accurate cold/hot detection; avoids false positives |

**Exit priority:** Stop-loss > Take-profit > Trailing stop > Breakeven stop > Time stop

**Emergence activation behavior:**
- Days 1-7: `is_emergence = NULL` for all signals; dashboard shows "Emergence detection: Activates in N days"
- Day 8+: Full emergence detection active; dashboard shows "Emergence detection: Active ✓"

### 10.5 Final PRD Review (2026-02-03)

Comprehensive pre-implementation review resolved all implementation ambiguities:

**Critical/High Priority Amendments:**

| Amendment | Requirement | Change |
|-----------|-------------|--------|
| Position sizing formula | FR-023 | Added concrete formula with confidence multipliers (0.5×/0.75×/1.0×) and risk limits (2-15% of portfolio) |
| AI-based ticker extraction | FR-034 (amended) | Changed from regex-based normalization to AI-based extraction during comment analysis. AI identifies tickers from context and normalizes to uppercase. |
| Price monitoring timing | FR-031 | Clarified intraday monitoring via Schwab API, acceptable for swing trading |
| System config init | Appendix B | Added SQL initialization script for deployment |

**Medium Priority Amendments:**

| Amendment | Location | Change |
|-----------|----------|--------|
| Dual signal timing | FR-024 | Clarified positions open immediately when detected, regardless of existing positions |
| Signal rollup model | Section 8.2, FR-039 | Changed from point-in-time to daily rollup; one signal per ticker/type/day, refined across runs |
| Reddit API reliability | Section 8.2 | PRAW handles rate limiting; log failures, no retry logic for Phase 1 |
| Deployment guidance | Section 6.2 (new) | Added SQLite, FastAPI, Vue deployment instructions |
| Phase 2 scope | Section 9 | Real trading parameters deferred to Phase 2 PRD |
| Performance handling | NFR-004 | Log warning if >15 min, continue processing |
| Cost monitoring | NFR-009 | Track via logging, warn if >$60/month |
| Architecture correction | Section 3.1, 3.2 | Moved yfinance API from Vue Dashboard to FastAPI layer (backend fetches prices, dashboard displays) |
| REST API contract | Appendix C (new) | Added complete API endpoint specification with request/response formats |
| Internal data format | Appendix D (new) | Documented internal data structures |
| AI analysis spec | Appendix E (new) | Added OpenAI prompt structure, response format, and ticker extraction rules |
| Position limit behavior | FR-025 (amended) | Clarified replacement logic: new signal must exceed lowest by >0.1 confidence; never replace positions with >+5% unrealized gain |
| Four-portfolio structure | FR-035, FR-036 (new) | Added 4 independent portfolios: stocks/quality, stocks/consensus, options/quality, options/consensus. Each has $100k capital and 10-position limit. |
| Options parameters | FR-037 (amended) | Options parameters fully defined in Section 10.7 (2026-02-04) |
| Schema updates | Appendix B | Added `portfolios` table; updated `positions` with portfolio_id, instrument_type, and option-specific fields |
| API updates | Appendix C | Changed `/portfolio` to `/portfolios` endpoint; added portfolio filtering to positions |
| Dashboard refresh | FR-012 (amended) | Clarified: data loads on page open, manual refresh button, no auto-polling |
| Comment deduplication | FR-038 (new) | Skip AI analysis for existing comments (by reddit_id); reuse stored annotations |
| Daily signal rollup | FR-039 (new) | One signal per ticker/type/day; multiple runs refine same signal; position opens once |

### 10.6 Signal Threshold Definition (2026-02-04)

HITL session defined concrete signal thresholds:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Quality min users | 2 | Lower bar for experimental phase; more signals to evaluate |
| Quality min confidence | 0.6 | AI must be reasonably certain comment has reasoning |
| Consensus min comments | 30 | Balanced threshold for meaningful consensus (calibrated for 500 analyzed comments) |
| Consensus min users | 8 | Anti-spam protection (1.6% of analyzed comment pool) |
| Consensus min alignment | 70% | Clear majority in one direction |
| Thresholds configurable | Yes | Store in system_config; tune without code changes |

**New requirements added:**
- FR-015 (amended): Quality signal with specific thresholds
- FR-016 (amended): Consensus signal with specific thresholds
- FR-040 (new): Signal confidence calculation formula

**Schema updates:**
- Added 11 new config entries to `system_config` initialization SQL

### 10.7 Options Specification (2026-02-04)

HITL session defined complete options parameters:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Strike selection | ~0.30 delta | Consistent risk profile; OTM for leverage |
| Expiration | 14-21 DTE | Balances time for move vs. theta decay |
| Position sizing | 2% of portfolio | Fixed allocation per trade |
| Stop-loss | -50% of premium | Wider than stocks; options are volatile |
| Take-profit trigger | +100% of premium | Captures meaningful gains |
| Partial exit | 50% of contracts | Locks gains, preserves upside |
| Trailing stop | -30% from peak | Wider than stocks for volatility |
| Expiration protection | Exit at DTE ≤ 2 | Avoid assignment and rapid decay |
| Time stop | 10 days max | Prevent excessive theta erosion |
| Data source | Schwab API (primary) | Free with funded account; confirmed, OAuth 2.0 |
| Fallback | Skip + retry | If Schwab unavailable, skip options monitoring for affected positions; retry on next run |

**Requirements added/amended:**
- FR-023 (amended): Added options sizing (2% fixed)
- FR-037 (amended): Replaced TBD with full options parameters
- FR-041 (new): Premium-based stop-loss for options
- FR-042 (new): Premium-based take-profit for options
- FR-043 (new): Trailing stop for options
- FR-044 (new): Expiration protection
- FR-045 (new): Time stop for options

**Section 4.7 added:** Options Exit Strategy with decision tree

### 10.8 Options Position Monitoring (2026-02-04)

HITL session defined complete options monitoring specification:

| Component | Specification |
|-----------|---------------|
| Monitoring algorithm | Priority-ordered: expiration → stop-loss → take-profit → trailing → time stop |
| Data requirements | Current premium (intraday, on each /analyze run), DTE calculation, peak premium tracking |
| Schema additions | `contracts_remaining`, `peak_premium` fields for options positions |
| Endpoint update | `/positions/monitor` consolidated into Phase 6 of `/analyze` pipeline (no separate endpoint) |

**Requirements added:**
- FR-048 (new): Options position monitoring algorithm

**Schema updates:**
- Added `contracts_remaining` to track partial exits
- Added `peak_premium` for options trailing stop calculation

**Endpoint updates:**
- `/positions/monitor` consolidated into Phase 6 of `/analyze` pipeline (no separate endpoint exists)

### 10.9 AI Batching Decision (2026-02-04)

HITL session finalized AI comment batching approach:

| Decision | Value | Rationale |
|----------|-------|-----------|
| Batching strategy | Individual (1 comment/call) | Accuracy over marginal cost savings |
| Cost impact | ~$0.25/month extra | Within budget ($10/month threshold) |
| Implementation | Simple loop | No batch parsing, separators, or error attribution complexity |

**Appendix E.8 updated:** Changed from "recommended batch 5" to "individual analysis selected"

### 10.10 Price Monitoring Schedule (2026-02-04)

HITL session defined daily price monitoring schedule:

| Decision | Value | Rationale |
|----------|-------|-----------|
| Trigger | Automatic (part of `/analyze`) | Consistent with on-demand pattern; no separate manual step |
| Recommended timing | Any time (intraday capable) | Schwab API provides real-time data; not limited to after-hours |
| Timezone | ET for display, UTC for storage | Standard US market timezone |
| Stock prices | Schwab API real-time + 5-min candles | Intraday granularity; yfinance daily OHLC fallback |
| Options prices | Schwab API premiums + greeks | No fallback; skip and retry next run |
| Data unavailable | Log warning, skip, retry next run | Graceful degradation; stocks fall back to yfinance, options monitoring skipped |

**Requirements added:**
- FR-049 (new): Price monitoring schedule specification

**Endpoint updates:**
- `/analyze` now includes automatic position monitoring at end of run

### 10.11 Image Analysis Failure Handling (2026-02-04)

HITL session defined image analysis failure handling:

| Decision | Value | Rationale |
|----------|-------|-----------|
| Retry strategy | 3 attempts with backoff | Balance persistence with not blocking |
| Retry delays | 2s, 5s, 10s | Exponential backoff pattern |
| On final failure | Log warning, continue | Image context is supplementary |
| Comment analysis | Proceeds regardless | Don't block 20+ comments for one image |

**Requirements updated:**
- FR-046 (amended): Added failure handling specification

**Appendix E.9 updated:** Added image analysis failure handling details

### 10.12 Default Portfolio View (2026-02-04)

HITL session defined default portfolio view:

| Decision | Value | Rationale |
|----------|-------|-----------|
| Default portfolio | Stock/Quality | Lead hypothesis; stocks primary, quality is "smart money" bet |
| State persistence | None | Always resets to default on page load; simple implementation |
| Tab order | Stock/Quality, Stock/Consensus, Options/Quality, Options/Consensus | Matches hypothesis priority |

**Requirements added:**
- FR-050 (new): Default portfolio view specification
- FR-012 (amended): Added default view mention

### 10.13 Section 3 Architecture Restructure (2026-02-04)

HITL session expanded Section 3 from 36 lines to ~380 lines, restructuring for implementation clarity:

| Old Section | New Section | Content |
|-------------|-------------|---------|
| 3.1 High-Level Architecture | 3.1 System Overview | Diagram + dependencies + architecture characteristics |
| 3.2 Component Responsibilities | 3.2 FastAPI Backend Architecture | 8 subsystems, 7-phase request flow, state management, error handling, design decisions |
| 3.3 Data Flow | 3.3 Data Model Architecture | 5 table layers, relationships, constraints, config-driven design |
| (N/A) | 3.4 REST API Design | Philosophy, endpoint organization, user workflow, design decisions |
| (N/A) | 3.5 Vue Dashboard Architecture | Responsibilities, state management, UI patterns, integration points |
| (N/A) | 3.6 Integration Patterns | Communication diagram, auth by layer, consistency strategies, 4-tier error boundaries |

**Appendices remain separate** as detailed reference specifications (A through E).

**Key additions:**
- Complete 7-phase POST /analyze request flow documentation
- Error boundary tiers (Hard Fail, Retry with Backoff, Graceful Degradation, Log and Continue)
- State management strategy (stateless architecture with SQLite persistence)
- Design decision rationale with rejected alternatives
- Integration patterns for cross-cutting concerns

### 10.14 Architecture Revision (2026-02-04)

HITL session decided to replace n8n workflow with native FastAPI Reddit integration:

| Decision | Value | Rationale |
|----------|-------|-----------|
| Remove n8n | Yes | Simplify architecture, single codebase |
| Reddit library | PRAW | Native Python, well-maintained, built-in rate limiting |
| Data format | New optimized | No backward compatibility needed |
| Image analysis | Synchronous | Ensures context available before comment analysis |
| Author trust | Full from day 1 | Quality implementation, not minimal viable |
| Storage | Direct to SQLite | No intermediate JSON files |

**Requirements added:**
- FR-046: Post Image Analysis
- FR-047: Author Trust Database

**Requirements modified:**
- FR-010: Changed from n8n integration to Reddit API integration

**Appendices updated:**
- Appendix A: Replaced n8n capabilities with FastAPI Reddit integration
- Appendix B: Added `authors` and `reddit_posts` tables, added `post_id` to comments
- Appendix D: Replaced n8n schema with internal data format
- Appendix E.3: Added image context to AI prompt template

**Technology changes:**

| Amendment | Date | Change |
|-----------|------|--------|
| Storage layer | 2026-02-03 | PostgreSQL → SQLite (better fit for single-user, local-first, experimental project) |

**Removed requirements:**

| Amendment | Date | Change |
|-----------|------|--------|
| Ticker filtering | 2026-02-03 | Removed FR-003 (penny stock/crypto exclusion) per HITL request |

**Review conducted by:** @project-lead
**Version:** 2.0 → 2.1

---

## Appendix A: FastAPI Reddit Integration Capabilities

The FastAPI backend provides native Reddit integration:

- **PRAW library** for OAuth2 authentication
- **Top 10 "hot" posts** from r/wallstreetbets
- **Top 1000 comments per post** sorted by engagement
- **Comment prioritization** using:
  - Financial keyword detection (calls, puts, options, strike, expiry, etc.)
  - Author trust scoring (SQLite-backed historical data)
  - Engagement metrics (upvotes, reply count)
  - Thread depth penalty
- **Parent chain tracking** for conversation context
- **Image analysis** using GPT-4o-mini vision (synchronous)
  - Detects images from i.redd.it, imgur, preview.redd.it
  - Extracts financial data, charts, tickers from images
  - Provides visual context for comment analysis
- **Rate limit handling** via PRAW built-in (60 requests/minute)

Configuration via environment variables:
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`

---

## Appendix B: SQLite Schema

**System Config Table: `system_config`**

| Column | Type | Description |
|--------|------|-------------|
| key | VARCHAR(50) | Config key (primary key) |
| value | TEXT | Config value |
| updated_at | TIMESTAMP | Last update time |

**33 total config entries** organized into 6 groups:
- **System state** (2): `system_start_date`, `phase`
- **Signal thresholds** (5): Quality (2) + Consensus (3)
- **Confidence weights** (4): Volume, alignment, AI confidence, author trust (must sum to 1.0)
- **Author trust** (6): Quality/accuracy/tenure weights, defaults, EMA weight
- **Stock exit strategy** (10): Stop-loss, take-profit, trailing stop, breakeven, time stops
- **Options exit strategy** (6): Stop-loss, take-profit, trailing stop, time stop, expiration protection

See Section 3.3.4 for complete key names and default values. See initialization SQL below for deployment script.

*Note: Portfolio values are tracked in the `portfolios` table, not system_config.*

**Initialization on first deployment:**

```sql
-- Enable foreign keys and WAL mode (required for SQLite)
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- System configuration (33 entries total)
INSERT INTO system_config (key, value, updated_at) VALUES
  -- System state (2 entries)
  ('system_start_date', DATE('now'), DATETIME('now')),
  ('phase', 'paper_trading', DATETIME('now')),
  -- Signal thresholds: Quality (2 entries)
  ('quality_min_users', '2', DATETIME('now')),
  ('quality_min_confidence', '0.6', DATETIME('now')),
  -- Signal thresholds: Consensus (3 entries)
  ('consensus_min_comments', '30', DATETIME('now')),
  ('consensus_min_users', '8', DATETIME('now')),
  ('consensus_min_alignment', '0.7', DATETIME('now')),
  -- Confidence calculation weights (4 entries, must sum to 1.0)
  ('confidence_weight_volume', '0.25', DATETIME('now')),
  ('confidence_weight_alignment', '0.25', DATETIME('now')),
  ('confidence_weight_ai_confidence', '0.30', DATETIME('now')),
  ('confidence_weight_author_trust', '0.20', DATETIME('now')),
  -- Author trust calculation (6 entries, see Appendix F)
  ('trust_weight_quality', '0.40', DATETIME('now')),
  ('trust_weight_accuracy', '0.50', DATETIME('now')),
  ('trust_weight_tenure', '0.10', DATETIME('now')),
  ('trust_default_accuracy', '0.50', DATETIME('now')),
  ('trust_tenure_saturation_days', '30', DATETIME('now')),
  ('accuracy_ema_weight', '0.30', DATETIME('now')),
  -- Stock exit strategy thresholds (10 entries)
  ('stock_stop_loss_pct', '-0.10', DATETIME('now')),
  ('stock_take_profit_pct', '0.15', DATETIME('now')),
  ('stock_trailing_stop_pct', '0.07', DATETIME('now')),
  ('stock_breakeven_trigger_pct', '0.05', DATETIME('now')),
  ('stock_breakeven_min_days', '5', DATETIME('now')),
  ('stock_time_stop_base_days', '5', DATETIME('now')),
  ('stock_time_stop_base_min_gain', '0.05', DATETIME('now')),
  ('stock_time_stop_extended_days', '7', DATETIME('now')),
  ('stock_time_stop_max_days', '10', DATETIME('now')),
  ('stock_take_profit_exit_pct', '0.50', DATETIME('now')),
  -- Options exit strategy thresholds (6 entries)
  ('option_stop_loss_pct', '-0.50', DATETIME('now')),
  ('option_take_profit_pct', '1.00', DATETIME('now')),
  ('option_trailing_stop_pct', '0.30', DATETIME('now')),
  ('option_time_stop_days', '10', DATETIME('now')),
  ('option_expiration_protection_dte', '2', DATETIME('now')),
  ('option_take_profit_exit_pct', '0.50', DATETIME('now'));

-- Initialize 4 portfolios ($100k each, $400k total paper trading capital)
INSERT INTO portfolios (name, instrument_type, signal_type, starting_capital, current_value, cash_available) VALUES
  ('stocks_quality', 'stock', 'quality', 100000, 100000, 100000),
  ('stocks_consensus', 'stock', 'consensus', 100000, 100000, 100000),
  ('options_quality', 'option', 'quality', 100000, 100000, 100000),
  ('options_consensus', 'option', 'consensus', 100000, 100000, 100000);
```

Note: `system_start_date` enables emergence activation countdown. During Days 1-7, `is_emergence` remains NULL for all signals. Day 8+ activates full emergence detection.

**Authors Table: `authors`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| username | VARCHAR(50) UNIQUE | Reddit username |
| first_seen | TIMESTAMP | First comment date |
| total_comments | INT | Lifetime comment count |
| high_quality_comments | INT | Comments with reasoning |
| total_upvotes | INT | Lifetime upvotes received |
| avg_conviction_score | FLOAT | Average conviction (0-1) |
| avg_sentiment_accuracy | FLOAT | Prediction accuracy (0-1) |
| flagged_comments | INT | Problematic comments |
| last_active | TIMESTAMP | Most recent comment |

**Reddit Posts Table: `reddit_posts`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| reddit_id | VARCHAR(20) UNIQUE | Reddit post ID |
| title | TEXT | Post title |
| selftext | TEXT | Post body |
| upvotes | INT | Post score |
| total_comments | INT | Comment count |
| image_url | TEXT | Image URL if present |
| image_analysis | TEXT | GPT-4o-mini vision description |
| fetched_at | TIMESTAMP | When fetched |

**Primary Table: `signals`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| signal_date | DATE | Calendar date (UTC) for daily rollup |
| created_at | TIMESTAMP | When signal first created |
| updated_at | TIMESTAMP | When signal last updated (refined) |
| ticker | VARCHAR(10) | Stock symbol |
| signal_type | VARCHAR(20) | 'quality' or 'consensus' |
| sentiment_score | FLOAT | -1 (bearish) to +1 (bullish) |
| prediction | VARCHAR(10) | 'bullish' or 'bearish' |
| confidence | FLOAT | 0-1 confidence level |
| comment_count | INT | Number of comments analyzed |
| has_reasoning | BOOLEAN | True if quality signal with arguments |
| is_emergence | BOOLEAN | True if ticker was cold (<3 mentions in 7 days); NULL during 7-day warmup |
| prior_7d_mentions | INT | Mention count in previous 7 days |
| distinct_users | INT | Number of distinct users mentioning ticker |
| position_opened | BOOLEAN | True if this signal triggered a position |

**Unique constraint:** `(ticker, signal_type, signal_date)` — One signal per ticker/type/day

**Portfolios Table: `portfolios`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| name | VARCHAR(50) | Portfolio identifier |
| instrument_type | VARCHAR(10) | 'stock' or 'option' |
| signal_type | VARCHAR(20) | 'quality' or 'consensus' |
| starting_capital | FLOAT | Initial capital ($100,000) |
| current_value | FLOAT | Current portfolio value |
| cash_available | FLOAT | Uninvested cash |
| created_at | TIMESTAMP | When portfolio created |

**Seed data:**
```sql
INSERT INTO portfolios (name, instrument_type, signal_type, starting_capital, current_value, cash_available) VALUES
  ('stocks_quality', 'stock', 'quality', 100000, 100000, 100000),
  ('stocks_consensus', 'stock', 'consensus', 100000, 100000, 100000),
  ('options_quality', 'option', 'quality', 100000, 100000, 100000),
  ('options_consensus', 'option', 'consensus', 100000, 100000, 100000);
```

**Positions Table: `positions`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| portfolio_id | INT | FK to portfolios |
| signal_id | INT | FK to signals |
| ticker | VARCHAR(10) | Stock/underlying symbol |
| instrument_type | VARCHAR(10) | 'stock' or 'option' |
| signal_type | VARCHAR(20) | 'quality' or 'consensus' |
| direction | VARCHAR(10) | 'long' or 'short' (stocks); 'call' or 'put' (options). **Note:** For options, `direction` and `option_type` are intentionally redundant — `direction` stores the same value as `option_type` for query consistency across instrument types (e.g., `WHERE direction = 'call'` works alongside `WHERE direction = 'long'`). |
| confidence | FLOAT | Signal confidence (determines position size) |
| position_size | FLOAT | Dollar amount allocated (stocks) or premium paid (options) |
| entry_date | DATE | When position opened |
| entry_price | FLOAT | Stock price or option premium at entry |
| status | VARCHAR(20) | 'open', 'closed' |
| — | — | **Stock-specific fields (nullable for options):** |
| shares | INT | Number of shares at entry (NULL for options); set on position open |
| shares_remaining | INT | Shares remaining after partial exits (NULL for options); decremented on each partial exit |
| — | — | **Monitoring state fields:** |
| stop_loss_price | FLOAT | Current stop-loss level (may be promoted to breakeven) |
| take_profit_price | FLOAT | Take-profit trigger level |
| peak_price | FLOAT | Highest price since entry (for trailing stop; stocks) |
| trailing_stop_active | BOOLEAN | True after partial take-profit |
| time_extension | VARCHAR(10) | 'base' (5d), 'extended' (7d), 'trailing' (10d) |
| — | — | **Option-specific fields (nullable for stocks):** |
| option_type | VARCHAR(10) | 'call' or 'put' (NULL for stocks) |
| strike_price | FLOAT | Option strike price (NULL for stocks) |
| expiration_date | DATE | Option expiration (NULL for stocks) |
| contracts | INT | Number of contracts at entry (NULL for stocks) |
| contracts_remaining | INT | Contracts remaining after partial exits (NULL for stocks) |
| premium_paid | FLOAT | Total premium paid (NULL for stocks) |
| peak_premium | FLOAT | Highest premium since entry, for trailing stop (NULL for stocks) |
| underlying_price_at_entry | FLOAT | Stock price when option opened (NULL for stocks) |
| — | — | **Closure fields:** |
| exit_date | DATE | When position fully closed (all exits complete) |
| exit_reason | VARCHAR(20) | Final exit reason (from last position_exits record) |
| hold_days | INT | Calendar days position was open (entry_date to exit_date) |
| realized_return_pct | FLOAT | Final return including all partial exits |

**Note:** Individual exit events (partial take-profit, trailing stop, etc.) are recorded in the `position_exits` table. The positions table `exit_date` and `exit_reason` reflect the final closure only. `hold_days` uses calendar days per Phase 2 decision.

**Daily Price Tracking: `price_history`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| ticker | VARCHAR(10) | Stock symbol |
| date | DATE | Trading date |
| open | FLOAT | Opening price |
| high | FLOAT | Daily high |
| low | FLOAT | Daily low |
| close | FLOAT | Closing price |
| fetched_at | TIMESTAMP | When data was retrieved |

**Unique constraint:** `(ticker, date)` — One row per ticker per day. Use `INSERT OR REPLACE` (UPSERT) to update existing rows when /analyze runs multiple times per day.

**Benchmark Table: `evaluation_periods`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| portfolio_id | INT | FK to portfolios |
| period_start | DATE | 30-day period start |
| period_end | DATE | 30-day period end |
| instrument_type | VARCHAR(10) | 'stock' or 'option' |
| signal_type | VARCHAR(20) | 'quality' or 'consensus' |
| status | VARCHAR(20) | 'active' or 'completed' (DEFAULT 'active') |
| portfolio_return_pct | FLOAT | Simulated portfolio return |
| sp500_return_pct | FLOAT | S&P 500 return for period |
| relative_performance | FLOAT | portfolio - sp500 |
| beat_benchmark | BOOLEAN | True if relative > 0 |
| total_positions_closed | INT | Positions closed during this period |
| winning_positions | INT | Closed positions with positive return |
| losing_positions | INT | Closed positions with negative return |
| avg_return_pct | FLOAT | Average realized return across closed positions |
| signal_accuracy_pct | FLOAT | Fraction of signals whose positions were profitable |
| value_at_period_start | FLOAT | Portfolio current_value at period start. Used for period-scoped return calculation in multi-period scenarios. |
| created_at | TIMESTAMP | When record created |

**Comments Table: `comments`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| analysis_run_id | INT | FK to analysis_runs; which run analyzed this comment |
| post_id | INT | FK to reddit_posts |
| reddit_id | VARCHAR(20) UNIQUE | Reddit comment ID (deduplication key) |
| author | VARCHAR(50) | Reddit username |
| body | TEXT | Original comment text |
| created_utc | TIMESTAMP | When comment was posted on Reddit |
| score | INT | Reddit upvotes |
| parent_comment_id | INT | FK to comments (self-referential); NULL for top-level comments |
| depth | INT | Thread depth (0 = top-level, 1 = reply, etc.) |
| prioritization_score | FLOAT | Score from Phase 2 prioritization algorithm |
| sentiment | VARCHAR(10) | 'bullish', 'bearish', or 'neutral' (from AI response) |
| sarcasm_detected | BOOLEAN | AI detected sarcasm (matches AI response field name) |
| has_reasoning | BOOLEAN | Contains argument/reasoning (matches AI response field name) |
| reasoning_summary | TEXT | AI-generated summary of the reasoning (if has_reasoning=true) |
| ai_confidence | FLOAT | 0-1 AI certainty in interpretation |
| author_trust_score | FLOAT | Point-in-time author trust score at analysis time (denormalized snapshot from authors table for Phase 4 signal confidence calculation) |
| analyzed_at | TIMESTAMP | When AI analysis was performed |

**Note:** Column names `sarcasm_detected` and `has_reasoning` match the AI response JSON field names exactly (see Appendix E). The previous `is_sarcasm` name was inconsistent. Tickers extracted by AI are stored in the `comment_tickers` junction table, not as a comma-separated string.

**Linked via `signal_comments` junction table** (not direct FK). A comment can contribute to multiple signals (e.g., mentions both AAPL and TSLA).

**Analysis Runs Table: `analysis_runs`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| status | VARCHAR(20) | 'running', 'completed', 'failed' |
| current_phase | INT | Current pipeline phase (1-7) |
| current_phase_label | VARCHAR(50) | Human-readable phase name for UI display |
| progress_current | INT | Current item in phase (e.g., comment 45 of 500) |
| progress_total | INT | Total items in phase |
| started_at | TIMESTAMP | When run started |
| completed_at | TIMESTAMP | When run completed (NULL if running/failed) |
| error_message | TEXT | Error details if failed (NULL if completed) |
| signals_created | INT | Count of signals created/updated (NULL until Phase 4 complete) |
| positions_opened | INT | Count of new positions opened (NULL until Phase 5 complete) |
| exits_triggered | INT | Count of exit events (NULL until Phase 6 complete) |
| warnings | TEXT | JSON array of non-fatal degradation events (e.g., skipped monitoring for ticker due to Schwab failure, image analysis failures). NULL if no warnings. Displayed in results summary overlay. |

**Signal Comments Junction Table: `signal_comments`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| signal_id | INT | FK to signals |
| comment_id | INT | FK to comments |
| created_at | TIMESTAMP | When link was created |

**Unique constraint:** `(signal_id, comment_id)` — prevents duplicate links

**Comment Tickers Junction Table: `comment_tickers`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| comment_id | INT | FK to comments |
| ticker | VARCHAR(10) | Ticker symbol extracted by AI |
| sentiment | VARCHAR(10) | Per-ticker sentiment ('bullish', 'bearish', 'neutral') |
| created_at | TIMESTAMP | When extracted |

**Unique constraint:** `(comment_id, ticker)` — one sentiment per ticker per comment

**Position Exits Table: `position_exits`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment primary key |
| position_id | INT | FK to positions |
| exit_date | DATE | When this exit occurred |
| exit_price | FLOAT | Price at exit (stock price or option premium) |
| exit_reason | VARCHAR(20) | 'stop_loss', 'take_profit', 'trailing_stop', 'breakeven_stop', 'time_stop', 'expiration', 'manual', 'replaced' |
| quantity_pct | FLOAT | Percentage of position closed (0.5 for partial, 1.0 for full) |
| shares_exited | INT | Number of shares exited (stocks only, NULL for options) |
| contracts_exited | INT | Number of contracts exited (options only, NULL for stocks) |
| realized_pnl | FLOAT | Profit/loss on this exit event |
| created_at | TIMESTAMP | When record created |

**Predictions Table: `predictions`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| comment_id | INT | FK to comments |
| ticker | VARCHAR(10) | Stock symbol |
| sentiment | VARCHAR(10) | bullish/bearish |
| option_type | VARCHAR(4) | call/put |
| analysis_run_id | INT | FK to analysis_runs |
| strike_price | FLOAT | Option strike price |
| expiration_date | DATE | Option expiration |
| contract_symbol | VARCHAR(50) | OCC symbol for Schwab lookup |
| entry_premium | FLOAT | Option premium at prediction time |
| entry_date | DATE | When prediction created |
| contracts | INT | max(1, floor(2000 / (entry_premium × 100))) |
| contracts_remaining | INT | Decremented on partial exits |
| current_premium | FLOAT | Updated by Phase 6 monitoring |
| peak_premium | FLOAT | For trailing stop |
| trailing_stop_active | BOOLEAN DEFAULT FALSE | Set after partial take-profit |
| status | VARCHAR(20) NOT NULL DEFAULT 'tracking' | tracking/resolved/expired |
| simulated_return_pct | FLOAT | Blended return from all prediction_exits |
| is_correct | BOOLEAN | simulated_return_pct > 0 |
| resolved_at | TIMESTAMP | When prediction resolved |
| hitl_override | VARCHAR(10) | correct/incorrect/excluded (NULL = auto) |
| hitl_override_at | TIMESTAMP | When override applied |
| created_at | TIMESTAMP NOT NULL | DEFAULT (DATETIME('now')) |

**Unique constraint:** `(comment_id, ticker)` — one prediction per ticker per comment

**Foreign keys:** `comment_id → comments(id)`, `analysis_run_id → analysis_runs(id)`

**Prediction Outcomes Table: `prediction_outcomes`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| prediction_id | INT | FK to predictions |
| day_offset | INT | Days since prediction creation |
| premium | FLOAT | Option premium at check time |
| underlying_price | FLOAT | Stock price for reference |
| recorded_at | TIMESTAMP | DEFAULT (DATETIME('now')) |

**Unique constraint:** `(prediction_id, day_offset)` — one snapshot per prediction per day

**Prediction Exits Table: `prediction_exits`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| prediction_id | INT | FK to predictions |
| exit_date | DATE | When exit triggered |
| exit_premium | FLOAT | Premium at exit |
| exit_reason | VARCHAR(30) | stop_loss, take_profit, trailing_stop, time_stop, expiration |
| quantity_pct | FLOAT | 0.5 for partial take-profit, 1.0 for full |
| contracts_exited | INT | Contracts closed in this exit |
| simulated_pnl | FLOAT | (exit_premium - entry_premium) × contracts_exited × 100 |
| created_at | TIMESTAMP | DEFAULT (DATETIME('now')) |

---

## Appendix C: REST API Contract

### C.1 Analysis

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| POST | `/analyze` | Trigger analysis pipeline. Returns HTTP 202 Accepted with `{data: {run_id}}` immediately. Pipeline runs in background thread (10-30 minutes): acquisition → AI analysis → signal detection → position management → price monitoring → post-analysis updates (author trust + evaluation periods). Returns HTTP 409 Conflict if a run is already in progress. | FR-010, FR-011, FR-024, FR-046, FR-047, FR-049 |
| GET | `/runs` | List analysis runs with timestamps and status | FR-006 |
| GET | `/runs/{id}/status` | Poll run progress. Returns: `{data: {status, current_phase, current_phase_label, progress_current, progress_total, signals_created, positions_opened, exits_triggered, error_message, warnings}}`. `warnings` is a JSON array of non-fatal degradation events (see Warnings Event Catalog in Section 3.2.2); NULL while running, populated on completion. Frontend polls every 10 seconds during active run. | Phase-2-polling |

### C.2 Signals

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/signals` | List signals, filterable by `ticker`, `signal_type`, `date_from`, `date_to`, `portfolio_id`. See response shape below. | FR-004, FR-005 |
| GET | `/signals/{id}` | Single signal with full details | FR-007 |
| GET | `/signals/{id}/comments` | Comments for a signal with AI annotations (sentiment, sarcasm_detected, has_reasoning, confidence) via signal_comments junction | FR-007, FR-021 |
| GET | `/signals/history` | Historical signal confidence data for sparklines. Query params: `ticker`, `signal_type`, `days` (default 14). Returns one confidence value per day per ticker/signal_type, reflecting the most recent /analyze run for that day. | FR-008 |

**GET /signals Response Shape:**

Base fields always returned: `id`, `ticker`, `signal_type`, `signal_date`, `prediction`, `confidence`, `comment_count`, `sentiment_score`, `has_reasoning`, `is_emergence`, `prior_7d_mentions`, `distinct_users`.

When `portfolio_id` is provided: adds `position_opened`, `skip_reason`, `position_summary` fields. When `portfolio_id` is omitted: those 3 fields are omitted entirely (not null, omitted).

`skip_reason` is computed dynamically by the API (not stored in the signals table). The backend derives the reason from context: bearish signal + stock portfolio → 'bearish_long_only', portfolio at capacity → 'portfolio_full', etc.

`position_summary` and `skip_reason` are mutually exclusive (one is always null when present).

`position_summary` fields: `position_id`, `status` (open/closed), `entry_date`, `entry_price`, `unrealized_return_pct` (backend-calculated from live Schwab/yfinance price, open positions only), `realized_return_pct` (closed only), `hold_days` (closed only).

```json
// GET /signals?portfolio_id=1&signal_type=quality
{
  "data": [
    {
      "id": 42,
      "ticker": "NVDA",
      "signal_type": "quality",
      "signal_date": "2026-02-06",
      "prediction": "bullish",
      "confidence": 0.78,
      "comment_count": 15,
      "sentiment_score": 0.65,
      "has_reasoning": true,
      "is_emergence": false,
      "prior_7d_mentions": 8,
      "distinct_users": 5,
      "position_opened": true,
      "skip_reason": null,
      "position_summary": {
        "position_id": 7,
        "status": "open",
        "entry_date": "2026-02-04",
        "entry_price": 142.50,
        "unrealized_return_pct": 4.07,
        "realized_return_pct": null,
        "hold_days": null
      }
    },
    {
      "id": 43,
      "ticker": "PLTR",
      "signal_type": "quality",
      "signal_date": "2026-02-06",
      "prediction": "bearish",
      "confidence": 0.65,
      "comment_count": 8,
      "sentiment_score": -0.42,
      "has_reasoning": true,
      "is_emergence": false,
      "prior_7d_mentions": 22,
      "distinct_users": 12,
      "position_opened": false,
      "skip_reason": "bearish_long_only",
      "position_summary": null
    }
  ],
  "meta": {
    "total": 2,
    "limit": 50,
    "offset": 0,
    "timestamp": "2026-02-06T14:30:00Z",
    "version": "1.0"
  }
}
```

**Rules:**
- Response uses standard `{data, meta}` envelope (see C.6/C.7)
- `skip_reason` is computed dynamically by the API per-portfolio, not stored in the database
- `position_summary` and `skip_reason` are mutually exclusive (one is always null)
- When `portfolio_id` is omitted, `position_summary`, `skip_reason`, and `position_opened` are omitted entirely
- `position_summary.status` = "open": `unrealized_return_pct` populated (backend-calculated), `realized_return_pct` = null, `hold_days` = null
- `position_summary.status` = "closed": `realized_return_pct` populated, `unrealized_return_pct` = null, `hold_days` populated

**GET /signals/{id}/comments Response Schema:**

```json
{
  "data": [
    {
      "id": 123,
      "body": "NVDA earnings going to crush it...",
      "author": "trader123",
      "created_utc": "2026-02-05T14:30:00Z",
      "score": 42,
      "depth": 0,
      "parent_comment_id": null,
      "sentiment": "bullish",
      "sarcasm_detected": false,
      "has_reasoning": true,
      "ai_confidence": 0.82,
      "author_trust_score": 0.72,
      "reasoning_summary": "Cites datacenter revenue growth and upcoming earnings catalyst",
      "ticker_sentiments": [
        {"ticker": "NVDA", "sentiment": "bullish"}
      ]
    }
  ],
  "meta": {
    "total": 5,
    "timestamp": "2026-02-06T14:30:00Z",
    "version": "1.0"
  }
}
```

**GET /signals/history Response Schema:**

Query params: `ticker` (optional — omit to batch all tickers for given signal_type), `signal_type`, `days` (default 14). Grouped by ticker when multiple tickers returned. Only days with signals are included.

```json
{
  "data": {
    "NVDA": [
      {"date": "2026-02-05", "confidence": 0.72},
      {"date": "2026-02-06", "confidence": 0.78}
    ],
    "AMD": [
      {"date": "2026-02-06", "confidence": 0.55}
    ]
  },
  "meta": {
    "days": 14,
    "signal_type": "quality",
    "timestamp": "2026-02-06T14:30:00Z",
    "version": "1.0"
  }
}
```

### C.3 Positions & Portfolio

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/portfolios` | List all 4 portfolios with summary stats (value, positions, performance) | FR-035 |
| GET | `/portfolios/{id}` | Single portfolio detail: value, cash, positions, allocation breakdown | FR-035 |
| GET | `/positions` | List positions, filterable by `portfolio_id`, `status` (open/closed), `ticker`, `instrument_type`, `signal_type`. Includes position_exits history for each position. | FR-023, FR-024, FR-025 |
| GET | `/positions/{id}` | Single position with exit strategy state (stops, peak price, time extension) and full position_exits history | FR-026-031 |
| POST | `/positions/{id}/close` | Manual early exit with reason. Creates position_exits record. Supports partial exits. See schema below. | — |

**POST /positions/{id}/close Schema:**

Request:
```json
{
  "reason": "string (required, free text)",
  "quantity_pct": "float (optional, 0 < x <= 1.0, default 1.0)"
}
```

Response (standard envelope):
```json
{
  "data": {
    "position": { "...updated position with status (open if partial, closed if full), shares_remaining/contracts_remaining updated" },
    "exit": { "...created position_exits record with exit_reason='manual', exit_price from Schwab/yfinance, quantity_pct, realized_pnl" }
  },
  "meta": {
    "timestamp": "2026-02-06T14:30:00Z",
    "version": "1.0"
  }
}
```

Status lifecycle:
- Partial close (`quantity_pct < 1.0`): status stays 'open', shares_remaining/contracts_remaining decremented
- Full close (shares_remaining hits 0 or contracts_remaining hits 0): status='closed', exit_date set, hold_days calculated

Errors:
- `400`: Invalid request (quantity_pct out of range, exceeds remaining quantity)
- `404`: Position not found
- `409`: Position already closed
- `503`: Price data unavailable (Schwab + yfinance both failed)

**Note:** Position monitoring (exit condition checks) runs automatically as Phase 6 of the `/analyze` pipeline. There is no separate `/positions/monitor` endpoint. Exit events are recorded in the `position_exits` table.

**GET /positions Response Schema:**

Backend computes convenience fields: `current_price`, `unrealized_return_pct`, `nearest_exit_distance_pct` (minimum distance to any exit trigger as percentage, used by frontend for "Near Exit" amber highlight when ≤ 0.02), `hold_days` (live-computed as `(today - entry_date).days` for open positions; stored value for closed positions). **Note:** GET /positions returns live `hold_days` for open positions, while GET /signals `position_summary.hold_days` is null for open positions (only populated on close). This divergence is intentional: positions need live hold days for exit condition awareness; signals show hold days as a completed-position metric.

```json
{
  "data": [
    {
      "id": 7,
      "portfolio_id": 1,
      "ticker": "NVDA",
      "instrument_type": "stock",
      "signal_type": "quality",
      "direction": "long",
      "status": "open",
      "entry_date": "2026-02-04",
      "entry_price": 142.50,
      "position_size": 5000.00,
      "shares": 35,
      "shares_remaining": 35,
      "confidence": 0.78,
      "current_price": 148.30,
      "unrealized_return_pct": 4.07,
      "nearest_exit_distance_pct": 0.068,
      "stop_loss_price": 128.25,
      "take_profit_price": 163.88,
      "peak_price": 149.10,
      "trailing_stop_active": false,
      "hold_days": 2,
      "position_exits": []
    },
    {
      "id": 12,
      "portfolio_id": 3,
      "ticker": "NVDA",
      "instrument_type": "option",
      "signal_type": "quality",
      "direction": "call",
      "option_type": "call",
      "status": "open",
      "entry_date": "2026-02-04",
      "entry_price": 3.50,
      "position_size": 2000.00,
      "strike_price": 155.00,
      "expiration_date": "2026-02-21",
      "contracts": 5,
      "contracts_remaining": 5,
      "premium_paid": 1750.00,
      "underlying_price_at_entry": 142.50,
      "confidence": 0.78,
      "current_price": 4.80,
      "unrealized_return_pct": 37.14,
      "nearest_exit_distance_pct": 0.15,
      "peak_premium": 5.10,
      "trailing_stop_active": false,
      "hold_days": 2,
      "dte": 15,
      "premium_change_pct": 0.371,
      "position_exits": []
    }
  ],
  "meta": {
    "total": 8,
    "limit": 50,
    "offset": 0,
    "timestamp": "2026-02-06T14:30:00Z",
    "version": "1.0"
  }
}
```

**Note:** For options positions, the backend computes additional convenience fields: `dte` (days to expiration from `expiration_date`), `premium_change_pct` (decimal, `(current_price - entry_price) / entry_price`). Stock-specific fields (`shares`, `shares_remaining`, `stop_loss_price`, `take_profit_price`, `peak_price`) are null for options; options-specific fields (`option_type`, `strike_price`, `expiration_date`, `contracts`, `contracts_remaining`, `premium_paid`, `peak_premium`, `underlying_price_at_entry`) are null for stocks.

**GET /portfolios Response Schema:**

Backend computes convenience fields: `open_position_count`, `total_pnl`, `total_pnl_pct`.

```json
{
  "data": [
    {
      "id": 1,
      "name": "stocks_quality",
      "instrument_type": "stock",
      "signal_type": "quality",
      "starting_capital": 100000.00,
      "current_value": 103500.00,
      "cash_available": 65000.00,
      "open_position_count": 7,
      "total_pnl": 3500.00,
      "total_pnl_pct": 3.50,
      "created_at": "2026-02-01T00:00:00Z"
    }
  ],
  "meta": {
    "timestamp": "2026-02-06T14:30:00Z",
    "version": "1.0"
  }
}
```

### C.4 Validation & Performance

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/evaluation-periods` | 30-day period performance vs S&P 500 benchmark. Query params: `portfolio_id` (required, scopes to specific portfolio). Returns active and completed periods with summary metrics. See response schema below. | FR-018 |
| GET | `/prices/{ticker}` | Price history for ticker (sparklines, validation). Query params: `days` (default 14) | FR-008, FR-014 |

**GET /evaluation-periods Response Schema:**

```json
{
  "data": [
    {
      "id": 1,
      "portfolio_id": 1,
      "period_start": "2026-01-15",
      "period_end": "2026-02-14",
      "instrument_type": "stock",
      "signal_type": "quality",
      "status": "active",
      "portfolio_return_pct": 3.50,
      "sp500_return_pct": 1.20,
      "relative_performance": 2.30,
      "beat_benchmark": true,
      "total_positions_closed": 4,
      "winning_positions": 3,
      "losing_positions": 1,
      "avg_return_pct": 5.25,
      "signal_accuracy_pct": 0.75,
      "value_at_period_start": 100000.00,
      "created_at": "2026-01-15T00:00:00Z"
    }
  ],
  "meta": {
    "portfolio_id": 1,
    "timestamp": "2026-02-06T14:30:00Z",
    "version": "1.0"
  }
}
```

**Note:** For active periods, metrics (`portfolio_return_pct`, `sp500_return_pct`, etc.) reflect live running values. For completed periods, metrics are final. `status` is 'active' or 'completed'.

**GET /prices/{ticker} Response Schema:**

Returns daily closing prices for sparkline rendering. Empty `data` array for invalid or missing tickers (not an error).

```json
{
  "data": [
    {"date": "2026-01-24", "close": 135.20},
    {"date": "2026-01-27", "close": 138.50},
    {"date": "2026-01-28", "close": 140.10},
    {"date": "2026-02-06", "close": 148.30}
  ],
  "meta": {
    "ticker": "NVDA",
    "days": 14,
    "timestamp": "2026-02-06T14:30:00Z",
    "version": "1.0"
  }
}
```

### C.5 System

| Method | Endpoint | Description | Source |
|--------|----------|-------------|--------|
| GET | `/status` | System status: current phase, emergence activation state, days until activation, open position count, last run timestamp, active_run_id (for page reload recovery — if non-null, frontend resumes polling). See response schema below. | FR-032, Phase-2-polling |

**GET /status Response Schema:**

```json
{
  "data": {
    "phase": "paper_trading",
    "emergence_active": false,
    "emergence_days_remaining": 5,
    "open_position_count": 14,
    "last_run_completed_at": "2026-02-06T14:30:00Z",
    "active_run_id": null
  },
  "meta": {
    "timestamp": "2026-02-06T14:35:00Z",
    "version": "1.0"
  }
}
```

**Field details:**
- `phase`: From system_config ('paper_trading' or 'real_trading')
- `emergence_active`: true if system has ≥7 days of history
- `emergence_days_remaining`: Days until emergence activates (0 if active; null if active)
- `open_position_count`: Total open positions across all 4 portfolios
- `last_run_completed_at`: Timestamp of most recent completed analysis run (null if none)
- `active_run_id`: Non-null if an analysis run is currently in progress (frontend uses for page reload recovery)

### C.6 Response Formats

All endpoints return JSON. Standard envelope:

```json
{
  "data": { ... },
  "meta": {
    "timestamp": "2026-02-03T14:30:00Z",
    "version": "1.0"
  }
}
```

Error responses:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description"
  }
}
```

### C.7 Pagination

List endpoints support pagination:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `limit` | 50 | Items per page (max 100) |
| `offset` | 0 | Number of items to skip |

Response includes:

```json
{
  "data": [...],
  "meta": {
    "total": 142,
    "limit": 50,
    "offset": 0
  }
}
```

---

## Appendix D: Internal Data Format

This appendix documents the optimized internal data structures used by FastAPI when processing Reddit data.

### D.1 ProcessedComment

| Field | Type | Description |
|-------|------|-------------|
| reddit_id | string | Reddit comment ID |
| post_id | int | FK to reddit_posts |
| author | string | Reddit username |
| body | string | Comment text |
| score | int | Reddit score (net upvotes) |
| depth | int | Thread depth (0 = top-level) |
| created_utc | int | Unix timestamp |
| priority_score | float | Composite priority (0-1) |
| financial_score | float | Financial keyword density (0-1) |
| author_trust_score | float | Historical trust (0-1) |
| parent_chain | array | Parent comments for context |

### D.2 ProcessedPost

| Field | Type | Description |
|-------|------|-------------|
| reddit_id | string | Reddit post ID |
| title | string | Post title |
| selftext | string | Post body text |
| upvotes | int | Post score |
| total_comments | int | Comment count |
| image_url | string/null | Image URL if present |
| image_analysis | string/null | GPT-4o-mini vision description |
| comments | array | Array of ProcessedComment objects |

### D.3 Parent Chain Entry

| Field | Type | Description |
|-------|------|-------------|
| id | string | Parent comment ID |
| body | string | Parent comment text |
| depth | int | Parent's thread depth |
| author | string | Parent's author |

### D.4 Key Changes from Previous Format

1. Removed redundant `topCommentsStructured` array
2. Consolidated to single `score` field (removed duplicate `upvotes`)
3. Added `post_id` for direct database linking
4. Flattened structure (no nested metadata objects)
5. Image analysis is synchronous and stored with post

### D.5 Example

```json
{
  "reddit_id": "1qei3d3",
  "title": "Weekly Earnings Thread 1/19 - 1/23",
  "selftext": "",
  "upvotes": 75,
  "total_comments": 96,
  "image_url": "https://i.redd.it/example.jpeg",
  "image_analysis": "Chart showing INTC earnings forecast with projected revenue growth of 15% QoQ. Highlights datacenter segment.",
  "comments": [
    {
      "reddit_id": "o002wz8",
      "post_id": 1,
      "author": "trader123",
      "body": "INTC calls looking good for earnings...",
      "score": 42,
      "depth": 0,
      "created_utc": 1768600892,
      "priority_score": 0.72,
      "financial_score": 0.45,
      "author_trust_score": 0.65,
      "parent_chain": []
    }
  ]
}
```

---

## Appendix E: AI Analysis Specification

OpenAI GPT-4o-mini analyzes each comment to extract structured data. This appendix defines the prompt structure and expected response format.

### E.1 Input Context

Each API call includes:

| Field | Source | Purpose |
|-------|--------|---------|
| `comment_body` | `ProcessedComment.body` (Appendix D.1) | Text to analyze |
| `parent_chain` | `ProcessedComment.parent_chain` (Appendix D.1/D.3) | Conversation context |
| `post_title` | `ProcessedPost.title` (Appendix D.2) | Topic context |
| `author_trust` | `ProcessedComment.author_trust_score` (Appendix D.1) | Historical reliability |
| `image_context` | `ProcessedPost.image_analysis` (Appendix D.2) | Visual context from post images (charts, data) |

### E.2 System Prompt

```
You are a financial sentiment analyzer specializing in WallStreetBets (WSB) content.
Your task is to analyze comments and extract structured trading signals.

WSB Communication Style:
- Heavy use of sarcasm and self-deprecating humor ("I'm going to lose all my money")
- Inverse statements ("X is definitely going to zero" often means bullish)
- Meme language: "diamond hands" (hold), "paper hands" (sell), "tendies" (profits),
  "to the moon" (bullish), "GUH" (loss), "apes" (retail investors), "regarded" (self-censored)
- Loss porn is celebrated; gains are often downplayed
- "This is financial advice" = sarcasm (it's not)

Your job:
1. See through sarcasm to identify actual sentiment
2. Extract ticker symbols mentioned (normalize to uppercase)
3. Identify if the comment contains substantive reasoning vs. hype
4. Assess confidence based on argument quality and author trust
```

### E.3 User Prompt Template

```
Analyze this WSB comment:

Post: "{post_title}"

Post Image Context (if available): "{image_description}"

Parent context (if reply):
{parent_chain_formatted}

Comment by {author} (trust score: {author_trust}):
"{comment_body}"

Respond with this exact JSON structure:
{
  "tickers": ["TICKER1", "TICKER2"],
  "ticker_sentiments": [
    {"ticker": "TICKER1", "sentiment": "bullish|bearish|neutral"},
    {"ticker": "TICKER2", "sentiment": "bullish|bearish|neutral"}
  ],
  "sentiment": "bullish|bearish|neutral",
  "sarcasm_detected": true|false,
  "has_reasoning": true|false,
  "confidence": 0.0-1.0,
  "reasoning_summary": "string or null"
}

Rules:
- ticker_sentiments must have one entry per ticker in tickers array
- sentiment is the overall comment direction (for single-ticker, matches ticker_sentiments[0].sentiment)
- reasoning_summary is null if has_reasoning is false
```

### E.4 Expected Response Format

```json
{
  "tickers": ["NVDA", "AMD"],
  "ticker_sentiments": [
    {"ticker": "NVDA", "sentiment": "bullish"},
    {"ticker": "AMD", "sentiment": "bearish"}
  ],
  "sentiment": "bullish",
  "sarcasm_detected": false,
  "has_reasoning": true,
  "confidence": 0.82,
  "reasoning_summary": "Cites datacenter revenue growth and upcoming earnings catalyst"
}
```

### E.5 Field Definitions

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `tickers` | array | Uppercase symbols | Stock tickers mentioned. Normalize variants (e.g., "apple" → "AAPL"). Empty array if none. |
| `ticker_sentiments` | array | `[{"ticker": "X", "sentiment": "bullish"}]` | Per-ticker sentiment direction. Required when multiple tickers have different sentiment (e.g., bullish NVDA, bearish AMD in same comment). Each entry maps a ticker to its specific sentiment. |
| `sentiment` | string | `bullish`, `bearish`, `neutral` | Overall directional sentiment after accounting for sarcasm. For single-ticker comments, matches `ticker_sentiments[0].sentiment`. |
| `sarcasm_detected` | boolean | true/false | Whether comment uses sarcasm or irony |
| `has_reasoning` | boolean | true/false | Contains substantive argument (not just "X to the moon") |
| `confidence` | float | 0.0 - 1.0 | AI confidence in interpretation. Factors: clarity, sarcasm ambiguity, author trust |
| `reasoning_summary` | string/null | Free text | Brief summary of argument if `has_reasoning` is true; null otherwise |

### E.6 Confidence Scoring Guidelines

| Scenario | Confidence Modifier |
|----------|---------------------|
| Clear, direct statement | +0.2 |
| Substantive reasoning provided | +0.2 |
| High author trust (>0.6) | +0.1 |
| Ambiguous sarcasm | -0.2 |
| Meme-heavy, no substance | -0.2 |
| Contradicts parent context | -0.1 |

Base confidence starts at 0.5; modifiers adjust up/down within [0.0, 1.0].

### E.7 Ticker Extraction Rules

AI should:
1. **Identify explicit tickers**: $AAPL, AAPL, "Apple stock"
2. **Normalize to uppercase**: nvda → NVDA
3. **Resolve common names**: "the mouse" → DIS, "Zuck" → META
4. **Exclude non-tickers**: "I", "A", "CEO", "DD", "YOLO" (unless clearly ticker context)
5. **Include crypto**: BTC, ETH (WSB discusses these)
6. **Deduplicate**: Return each ticker once per comment

### E.8 Batching Strategy

**Decision: Individual analysis (1 comment per API call)**

| Option Considered | Trade-off | Decision |
|-------------------|-----------|----------|
| 1 comment/call | Most accurate, ~$0.25/month extra | **Selected** |
| 5 comments/call | Marginal savings, cross-contamination risk | Rejected |
| 10+ comments/call | Significant confusion risk | Rejected |

**Rationale:**
- Cost difference is negligible (~$0.25/month, well within $10/month budget)
- This is an experiment — accuracy matters more than marginal savings
- No risk of AI confusing comments with each other
- Simpler implementation, easier to debug and attribute errors
- Each comment gets full context (post image analysis, author trust) without interference

### E.9 Error Handling

| Scenario | Action |
|----------|--------|
| Malformed JSON response | Retry once; if retry also fails, log warning and skip comment |
| Rate limit (429) | Exponential backoff (1s, 2s, 4s, max 30s), up to 3 retries |
| Empty tickers array | Valid response; comment mentions no tickers |
| Timeout | Retry once; if retry also fails, log warning and skip comment |
| Image analysis failure | Retry 3 times (2s, 5s, 10s delays); if all fail, log warning and continue without image context |

**Image Analysis Failure Handling:**

```
1. Attempt image fetch + GPT-4o-mini vision analysis
2. On failure (network error, invalid image, API error, timeout):
   - Retry 1: wait 2 seconds, retry
   - Retry 2: wait 5 seconds, retry
   - Retry 3: wait 10 seconds, retry
3. If all 3 retries fail:
   - Log warning: "Image analysis failed for post {post_id}: {error}"
   - Set image_analysis = NULL in database
   - Continue with comment analysis (image context is supplementary)
4. Comment analysis proceeds regardless of image analysis outcome
```

---

## Appendix F: Author Trust Calculation

This appendix specifies the exact formulas for calculating author trust scores, conviction scores, and sentiment accuracy. These calculations support comment prioritization (FR-010), signal confidence (FR-040), and the author trust database (FR-047).

### F.1 Overview

Author trust quantifies historical reliability of Reddit users. The system tracks raw metrics and derives a composite trust score used in:

| Usage Point | Weight | Reference |
|-------------|--------|-----------|
| Comment priority_score | 30% | Section 3.2.2 Phase 2 |
| Signal confidence | 20% | FR-040 |
| AI prompt context | Informational | Appendix E.3 |

### F.2 Trust Score Calculation

The trust score is a composite value (0.0 - 1.0) calculated from three components:

```
trust_score = (quality_ratio × 0.40) + (accuracy_component × 0.50) + (tenure_factor × 0.10)
```

#### F.2.1 Quality Ratio

Measures the proportion of substantive comments:

```
quality_ratio = high_quality_comments / max(total_comments, 1)
```

Where `high_quality_comments` = count of comments where AI analysis returned `has_reasoning=true`.

#### F.2.2 Accuracy Component

Measures prediction accuracy against realized returns:

```
if avg_sentiment_accuracy IS NOT NULL:
    accuracy_component = avg_sentiment_accuracy
else:
    accuracy_component = 0.5  # neutral default for new authors
```

See Section F.4 for how `avg_sentiment_accuracy` is calculated.

#### F.2.3 Tenure Factor

Rewards established presence, saturating at 30 days:

```
days_active = (current_date - first_seen).days
tenure_factor = min(1.0, days_active / 30.0)
```

#### F.2.4 Complete Algorithm

**Implementation Note:** Pseudocode below shows default values for clarity. Implementation MUST read weights from `system_config` (`trust_weight_quality`, `trust_weight_accuracy`, `trust_weight_tenure`, `trust_default_accuracy`, `trust_tenure_saturation_days`) to enable runtime tuning per Section 3.3.4.

```python
def calculate_trust_score(author: Author) -> float:
    """Calculate trust score (0.0 - 1.0) for an author."""

    # Quality component (40% weight)
    quality_ratio = author.high_quality_comments / max(author.total_comments, 1)

    # Accuracy component (50% weight)
    if author.avg_sentiment_accuracy is not None:
        accuracy_component = author.avg_sentiment_accuracy
    else:
        accuracy_component = 0.5  # neutral default

    # Tenure component (10% weight)
    days_active = (date.today() - author.first_seen.date()).days
    tenure_factor = min(1.0, days_active / 30.0)

    # Weighted combination
    trust_score = (
        quality_ratio * 0.40 +
        accuracy_component * 0.50 +
        tenure_factor * 0.10
    )

    return round(trust_score, 3)
```

### F.3 Conviction Score Calculation

The conviction score measures the strength and quality of individual comments. It is calculated per-comment, then averaged across all author comments.

#### F.3.1 Per-Comment Conviction

```
comment_conviction = (length_factor × 0.20) + (reasoning_bonus × 0.20) + (ai_confidence × 0.60)
```

Where:
- `length_factor = min(1.0, character_count / 500)` — longer comments (up to 500 chars) indicate more effort
- `reasoning_bonus = 1.0 if has_reasoning else 0.0` — substantive arguments add conviction
- `ai_confidence` = confidence value from AI analysis (0.0 - 1.0)

#### F.3.2 Author Average

```
avg_conviction_score = mean(comment_conviction for all author's comments)
```

#### F.3.3 Update Process (Phase 7: Post-Analysis Updates)

When processing new comments in Phase 7 (Post-Analysis Updates):

```python
def update_author_conviction(author: Author, new_comments: list[Comment]) -> None:
    """Update author's avg_conviction_score with new comments."""

    # Calculate conviction for each new comment
    new_convictions = []
    for comment in new_comments:
        length_factor = min(1.0, len(comment.body) / 500)
        reasoning_bonus = 1.0 if comment.has_reasoning else 0.0
        ai_confidence = comment.ai_confidence

        conviction = (
            length_factor * 0.20 +
            reasoning_bonus * 0.20 +
            ai_confidence * 0.60
        )
        new_convictions.append(conviction)

    # Recalculate running average
    old_total = author.total_comments - len(new_comments)  # count before this update
    old_sum = author.avg_conviction_score * old_total if author.avg_conviction_score else 0
    new_sum = sum(new_convictions)

    author.avg_conviction_score = (old_sum + new_sum) / author.total_comments
```

### F.4 Sentiment Accuracy Calculation

Sentiment accuracy measures how well an author's bullish/bearish predictions would have performed as actual options positions. This is calculated when simulated predictions resolve through the same exit conditions as real positions.

#### F.4.1 Accuracy Determination

For each resolved prediction:

```
1. The prediction was created from a comment_ticker (bullish → call, bearish → put)
2. Phase 6 monitored the simulated option using real Schwab premium data
3. Exit conditions triggered (stop-loss, take-profit, trailing stop, time stop, expiration)
4. Blended return calculated from prediction_exits:
   simulated_return_pct = SUM(prediction_exits.simulated_pnl) / (entry_premium × contracts × 100)

Accuracy determination:
- is_correct = TRUE if simulated_return_pct > 0
- is_correct = FALSE if simulated_return_pct ≤ 0
- HITL override takes precedence: correct/incorrect/excluded
- Excluded predictions do not affect accuracy
```

**Implementation Note:** The per-ticker sentiment from `comment_tickers` is used to determine option type (bullish → call, bearish → put). Each comment_ticker generates exactly one prediction per unique (comment_id, ticker) pair.

#### F.4.2 Running Average Update

**Implementation Note:** Pseudocode below shows default EMA weight (0.30) for clarity. Implementation MUST read `accuracy_ema_weight` from `system_config` to enable runtime tuning per Section 3.3.4.

Uses exponential moving average to weight recent accuracy more heavily:

```python
def update_sentiment_accuracy(author: Author, is_correct: bool, is_excluded: bool) -> None:
    """Update author's avg_sentiment_accuracy after prediction resolves."""

    if is_excluded:
        return

    new_accuracy = 1.0 if is_correct else 0.0

    if author.avg_sentiment_accuracy is None:
        author.avg_sentiment_accuracy = new_accuracy
    else:
        # EMA: accuracy_ema_weight from system_config (default 0.30)
        author.avg_sentiment_accuracy = (
            (1 - accuracy_ema_weight) * author.avg_sentiment_accuracy +
            accuracy_ema_weight * new_accuracy
        )
```

#### F.4.3 Cold Start Timeline

Predictions resolve within the option's lifecycle (typically 5-21 days based on DTE and exit conditions). New authors begin receiving accuracy data after their first predictions resolve — approximately 2-4 weeks vs 30-60 days under the previous position-based system.

New authors have `avg_sentiment_accuracy = NULL` until their first prediction resolves. During this period:
- Trust score uses 0.5 (neutral) for the accuracy component
- Prediction lifecycle is DTE-driven (~17-30 days depending on exit triggers)
- Authors with no resolved predictions continue using the neutral default

### F.5 Default Values

| Scenario | Value | Rationale |
|----------|-------|-----------|
| New author trust_score | 0.5 | Neutral starting point; neither trusted nor distrusted |
| New author avg_conviction_score | NULL | No data; calculated on first comment |
| New author avg_sentiment_accuracy | NULL | No data; 0.5 used in trust calculation |
| Minimum comments for trust adjustment | 1 | Trust adjusts immediately; quality_ratio and conviction provide signal even with 1 comment |

### F.6 System Configuration

Add the following to `system_config` for tunability:

| Key | Default | Description |
|-----|---------|-------------|
| `trust_weight_quality` | 0.40 | Weight for quality_ratio in trust calculation |
| `trust_weight_accuracy` | 0.50 | Weight for accuracy_component in trust calculation |
| `trust_weight_tenure` | 0.10 | Weight for tenure_factor in trust calculation |
| `trust_default_accuracy` | 0.50 | Default accuracy for authors with no history |
| `trust_tenure_saturation_days` | 30 | Days until tenure_factor reaches 1.0 |
| `accuracy_ema_weight` | 0.30 | Weight for new data in accuracy EMA |

### F.7 Flagged Comments (Phase 2)

The `flagged_comments` column exists for future spam/manipulation detection. In Phase 1:
- Column is populated but not used in trust calculation
- Future implementation may apply trust penalties for flagged comments
- Flagging criteria to be defined in Phase 2 requirements

### F.8 Example Calculations

**Example 1: New Author (First Comment)**
```
Author: u/diamond_hands_guy
first_seen: today
total_comments: 1
high_quality_comments: 1
avg_conviction_score: 0.76  # calculated from first comment
avg_sentiment_accuracy: NULL

trust_score = (1/1 × 0.40) + (0.5 × 0.50) + (0/30 × 0.10)
            = 0.40 + 0.25 + 0.00
            = 0.65
```

**Example 2: Established Author (Good Track Record)**
```
Author: u/solid_dd_writer
first_seen: 45 days ago
total_comments: 23
high_quality_comments: 18
avg_conviction_score: 0.72
avg_sentiment_accuracy: 0.68

trust_score = (18/23 × 0.40) + (0.68 × 0.50) + (1.0 × 0.10)
            = (0.783 × 0.40) + 0.34 + 0.10
            = 0.313 + 0.34 + 0.10
            = 0.753
```

**Example 3: Active Author (Poor Track Record)**
```
Author: u/yolo_everything
first_seen: 60 days ago
total_comments: 45
high_quality_comments: 5
avg_conviction_score: 0.41
avg_sentiment_accuracy: 0.32

trust_score = (5/45 × 0.40) + (0.32 × 0.50) + (1.0 × 0.10)
            = (0.111 × 0.40) + 0.16 + 0.10
            = 0.044 + 0.16 + 0.10
            = 0.304
```

---

**Document Complete**

*Generated by ART (Anchor Requirements Team)*
*HITL Affirmation: 2026-01-16*
*Revised: 2026-02-03 (Vision Clarity Session)*
*Revised: 2026-02-03 (Portfolio & Exit Strategy Session)*
*Revised: 2026-02-04 (Signal Threshold Definition)*
*Revised: 2026-02-04 (Options Specification)*
*Revised: 2026-02-04 (Architecture Revision — Replace n8n with FastAPI Reddit Integration)*
*Revised: 2026-02-04 (Options Position Monitoring Specification)*
*Revised: 2026-02-04 (AI Batching Decision — Individual Analysis)*
*Revised: 2026-02-04 (Price Monitoring Schedule)*
*Revised: 2026-02-04 (Image Analysis Failure Handling)*
*Revised: 2026-02-04 (Default Portfolio View)*
*Revised: 2026-02-04 (Section 3 Architecture Restructure)*
*Consolidated: 2026-02-06 (v3.0 — Galileo Phase 2 consolidation)*
*Consolidated: 2026-02-06 (v3.4 — Phase 3b Re-Validation, 43 amendments)*
*Consolidated: 2026-02-07 (v3.5 — Phase 3c Second Re-Validation, 34 amendments)*

---

## Consolidation Changelog (v2.4 → v3.0)

This section documents all changes applied during the v3.0 consolidation, which merged 37 Phase 1 amendments (from 4 amendment documents) and 28 Phase 2 HITL decisions into the PRD body.

### Phase 1 Amendment Sources Merged
- `prd-amendments-intraday.md` (14 amendments): Schwab API intraday monitoring
- `prd-amendments-comment-signal-junction.md` (8 amendments): Junction tables, comments schema
- `prd-amendments-dual-sparklines.md` (7 amendments): Dual sparklines, signals/history endpoint
- `prd-amendments-position-exits.md` (8 amendments): Normalized position_exits table

### Phase 2 Decisions Merged (28 question cards)

**Cluster 1 — Analysis Runs & Polling (5 cards)**
- Added `analysis_runs` table schema (status, phase tracking, progress, results)
- POST /analyze returns HTTP 202 with run_id (async polling pattern)
- GET /runs/{id}/status endpoint for frontend polling
- 4-stage progress indicator (Fetching → Analyzing → Detecting → Monitoring)
- Single-run enforcement (HTTP 409), page reload recovery, results summary overlay
- Background thread with isolated SQLite connection, crash detection

**Cluster 2 — Comments Schema (3 cards)**
- Renamed `is_sarcasm` → `sarcasm_detected` (matches AI response format)
- Removed `signal_id` FK from comments (linked via signal_comments junction)
- Removed `ticker_mentions` VARCHAR (replaced by comment_tickers junction)
- Added `analysis_run_id`, `parent_comment_id`, `depth`, `prioritization_score`, `reasoning_summary`, `analyzed_at`
- Added `signal_comments` junction table (signal_id, comment_id)
- Added `comment_tickers` junction table (comment_id, ticker, sentiment)

**Cluster 3 — Schwab API (4 cards)**
- Schwab confirmed as primary pricing source (no longer "pending")
- Full OAuth 2.0 lifecycle specification (setup, refresh, degradation)
- Token storage: `./data/schwab_token.json` (not database, not .env)
- yfinance for sparkline price data (live fetch, not from price_history)
- Tiered gap handling: yfinance daily OHLC for missed days + Schwab 5-min for today

**Cluster 4 — Sub-Tab Layout & Signal Card UX (5 cards)**
- Sub-tabs within each portfolio tab: "Signals" (default), "Positions", and "Performance"
- Two-row signal card layout with dual sparklines
- Adaptive sparkline rendering (dots for ≤2 points, line for 3+)
- Signal card position status (4 visual states: Position Open, Position Closed, Below threshold, Not eligible)
- Position monitoring indicators (4 visual states: active, near exit, partial, market closed)
- Market hours indicator (client-side, header-level)

**Cluster 5 — Position & Exit Edge Cases (5 cards)**
- `position_opened` = TRUE when at least one position opened for signal
- Market hours deferral: skip entirely (no deferred queue)
- `hold_days` uses calendar days (not trading days)
- Consistent simulated fill: trigger-based exits use trigger price, discretionary use current

**Cluster 6 — Config, Cleanup & Checkpoints (4 cards)**
- 16 exit strategy config keys enumerated (10 stock + 6 options), total 33 system_config entries
- FR-001 text updated from velocity/intensity to Quality/Consensus methods
- Per-comment commits during Phase 3 AI analysis (not batched, not single transaction)
- Schwab OAuth lifecycle added as implementation constraint in Section 3.6.2

### Validation Round Amendments (v3.1, 2026-02-06)

7 validation question cards resolved (qc-val-001 through qc-val-007):

| Card | Change | Sections Updated |
|------|--------|-----------------|
| qc-val-001 | Added `shares` and `shares_remaining` columns to positions table (mirrors options pattern) | Appendix B: positions table |
| qc-val-002 | Added `ticker_sentiments` array to AI response format for per-ticker sentiment direction | Appendix E.4, E.5; Phase 3 pseudocode |
| qc-val-003 | Changed polling interval from 3s to 10s in all references (matches Phase 2 decision) | Sections 3.4.3, 3.5.1, 3.5.4, 3.6.1; Appendix C |
| qc-val-004 | Added Performance as third sub-tab per portfolio (Signals, Positions, Performance) | Sections 3.5.1, 3.5.3, 3.5.4 |
| qc-val-005 | Added `analysis_run_id` reassignment step to Phase 3 dedup pseudocode | Section 3.2.2 Phase 3 |
| qc-val-006 | Renamed Phase 7 to "Post-Analysis Updates"; added evaluation period auto-creation logic (7b) | Section 3.2.2 Phase 7; Appendix F.3.3 |
| qc-val-007 | Split position status indicators into two distinct sets: signal-card indicators (Signals sub-tab) and position monitoring indicators (Positions sub-tab) | Section 3.5.1; Cluster 4 summary |

### Validation Round 2 Amendments (v3.2, 2026-02-06)

13 Phase 3 validation question cards resolved (qc-val3-001 through qc-val3-ux-003):

| Card(s) | Change | Sections Updated |
|---------|--------|-----------------|
| qc-val3-001, qc-val3-005, qc-val3-arch-002, qc-val3-rm-001 | Added `shares_exited INT` to position_exits table; fixed Phase 6 pseudocode to use actual schema column names (`shares_remaining`/`contracts_remaining` instead of `remaining_quantity`, `realized_pnl` instead of `proceeds`) | Appendix B: position_exits; Section 3.2.2 Phase 6 |
| qc-val3-003, qc-val3-arch-001 | Added `status VARCHAR(20)` and `created_at TIMESTAMP` to evaluation_periods; fixed Phase 7b to use `period_start`/`period_end` column names; changed to shared 30-day window across all 4 portfolios (4 rows in lockstep, not independent cycles) | Appendix B: evaluation_periods; Section 3.2.2 Phase 7b |
| qc-val3-ux-001 | Added 5 denormalized summary columns to evaluation_periods (`total_positions_closed`, `winning_positions`, `losing_positions`, `avg_return_pct`, `signal_accuracy_pct`); added `portfolio_id` query param to GET /evaluation-periods | Appendix B: evaluation_periods; Appendix C.4 |
| qc-val3-ux-002 | Added Performance sub-tab empty state definitions (no periods, active-only with live metrics, zero positions) | Section 3.5.1 |
| qc-val3-002 | Added full JSON schema to AI prompt template E.3 (replaces bare "Respond with JSON only.") | Appendix E.3 |
| qc-val3-004 | Clarified Phase 4 signal detection uses `comment_tickers.sentiment` (per-ticker) for direction alignment, not `comments.sentiment` (overall) | Section 3.2.2 Phase 4 |
| qc-val3-006 | Added `skip_reason VARCHAR(30)` to signals table; enriched GET /signals with `position_summary` object and `portfolio_id` query param for signal card state 2/4 support | Appendix B: signals; Appendix C.2; Section 3.2.2 Phase 5 |
| qc-val3-rm-002 | Updated POST /analyze description from "author trust update" to "post-analysis updates (author trust + evaluation periods)" | Appendix C.1 |
| qc-val3-ux-003 | Updated user workflow step 6 to reflect Performance sub-tab navigation with `portfolio_id` param; moved sparkline call out (belongs to Signals sub-tab) | Section 3.4.3 |

### Phase 4 Gap Analysis Amendments (v3.3, 2026-02-06)

10 Phase 4 gap analysis question cards resolved (qc-4-sd-001 through qc-4-ux-002):

| Card(s) | Change | Sections Updated |
|---------|--------|-----------------|
| qc-4-sd-001 | Removed yfinance + Black-Scholes fallback for options; split Schwab error handling into stocks/options rows; updated graceful degradation to retry + skip pattern | Section 3.2.4; Section 3.6.2; Section 4.5; Section 10.7 |
| qc-4-rm-001 | Fixed emergence thresholds in Vision Clarity to match pseudocode (13/8 not 5/3) | Section 10.3 |
| qc-4-sd-003 | Added deterministic options strike selection algorithm with call+put support; added 'no_valid_strike' to skip_reason enum | Section 4.5; Appendix B: signals |
| qc-4-arch-003 | Added explicit portfolio current_value formula (cash + mark-to-market) to Phase 5/6 pseudocode | Section 3.2.2 Phase 5, Phase 6 |
| qc-4-rm-002 | Defined "closed position" for evaluation metrics; partially exited positions excluded until fully closed | Section 3.2.2 Phase 7b |
| qc-4-arch-001 | Added POST /positions/{id}/close schema with partial exit support via quantity_pct | Appendix C.3 |
| qc-4-arch-002 | Added GET /signals complete response shape with position_summary, base fields, JSON example | Appendix C.2 |
| qc-4-ux-001 | Documented GET /signals/history aggregation behavior (latest confidence per day) | Appendix C.2 |
| qc-4-ux-002 | Added value_at_period_start column to evaluation_periods for multi-period return scoping | Appendix B: evaluation_periods |

### Schema Changes Summary (v3.0-3.5)
- **New tables:** analysis_runs, signal_comments, comment_tickers, position_exits (4 new)
- **Removed tables:** predictions (v3.4 — functionality covered by positions.realized_return_pct + evaluation_periods + authors)
- **Modified tables:** comments (6 columns added, 3 removed/renamed, `author_trust_score` added in v3.4), signals (`skip_reason` removed in v3.4 — computed dynamically by API), positions (partial exit fields removed, moved to position_exits), evaluation_periods (`status`, `created_at`, 5 summary columns added in v3.2, `value_at_period_start` added in v3.3), position_exits (`shares_exited` added in v3.2, `'replaced'` exit_reason added in v3.5), analysis_runs (`warnings` TEXT added in v3.4), price_history (UNIQUE(ticker, date) constraint added in v3.4)
- **system_config:** 18 → 34 entries (+16 exit strategy parameters)
- **Total tables:** 13 (was 10; +4 new, -1 removed)

### Phase 3b Re-Validation Amendments (v3.4, 2026-02-06)

43 Phase 3b re-validation question cards resolved across 4 agents:

**Software Developer (SD) — 10 cards:**

| Card | Change | Sections Updated |
|------|--------|-----------------|
| qc-val3b-sd-001 | Options monitoring pseudocode: replaced `partial_exit_done/price/date` with `position_exits` INSERT pattern matching Phase 6 stock approach | Section 4.7 |
| qc-val3b-sd-002 | Phase 6 cash formula: proceeds-only (no realized_pnl addition). Stock: `cash += exit_price * shares_exited`. Options: `cash += exit_price * contracts_exited * 100` | Section 3.2.2 Phase 6 |
| qc-val3b-sd-003 | Options exit cash: added x100 contract multiplier | Section 3.2.2 Phase 6 |
| qc-val3b-sd-004 | `closed_date` → `exit_date` in Phase 6 pseudocode | Section 3.2.2 Phase 6; Appendix C.3 |
| qc-val3b-sd-005 | `cost_basis` → `position_size` as return calculation denominator | Section 3.2.2 Phase 6 |
| qc-val3b-sd-006 | Quality signal direction: unanimity (not majority) | Section 4.4 |
| qc-val3b-sd-007 | `skip_reason` removed from signals table; computed dynamically per-portfolio in API | Section 3.2.2 Phase 5; Appendix B: signals; Appendix C.2 |
| qc-val3b-sd-008 | `price_history` table: added UPSERT step to Phase 6; added UNIQUE(ticker, date) constraint | Section 3.2.2 Phase 6; Appendix B: price_history |
| qc-val3b-sd-009 | `value_at_period_start` set in both Phase 7b creation paths | Section 3.2.2 Phase 7b |
| qc-val3b-sd-010 | Options exit decision tree reordered: expiration protection first | Section 4.7 |

**Architecture (ARCH) — 8 cards:**

| Card | Change | Sections Updated |
|------|--------|-----------------|
| qc-val3b-arch-001 | Cash formula fixed to proceeds-only (converges with sd-002) | Section 3.2.2 Phase 6 |
| qc-val3b-arch-002 | `closed_date` → `exit_date` (converges with sd-004) | Section 3.2.2 Phase 6; Appendix C.3 |
| qc-val3b-arch-003 | Options pseudocode normalized to position_exits (converges with sd-001) | Section 4.7 |
| qc-val3b-arch-004 | `cost_basis` → `position_size` (converges with sd-005) | Section 3.2.2 Phase 6 |
| qc-val3b-arch-005 | First-run handling for `last_check_time` in Phase 6 | Section 3.2.2 Phase 6 |
| qc-val3b-arch-006 | `breakeven_stop` exit_reason when promoted stop-loss fires | Section 3.2.2 Phase 6 |
| qc-val3b-arch-007 | `author_trust_score FLOAT` added to comments table | Appendix B: comments |
| qc-val3b-arch-008 | GET /signals standardized to `{data, meta}` envelope | Appendix C.2 |

**Requirements Manager (RM) — 13 cards:**

| Card | Change | Sections Updated |
|------|--------|-----------------|
| qc-val3b-rm-001 | Options pseudocode normalized (converges with sd-001) | Section 4.7 |
| qc-val3b-rm-002 | `closed_date` → `exit_date` (converges with sd-004) | Section 3.2.2 Phase 6; Appendix C.3 |
| qc-val3b-rm-003 | Appendix E.1 input context updated from n8n format to Appendix D references; added `image_context` row | Appendix E.1 |
| qc-val3b-rm-004 | E.9 error handling: "smaller batch" → "log and skip comment"; standardized 3 retries with exponential backoff | Appendix E.9 |
| qc-val3b-rm-005 | `predictions` table removed from Phase 1 (13 tables total); prediction tables re-added in prediction accuracy redesign (16 tables total) | Section 3.3.1; Appendix B |
| qc-val3b-rm-006 | `cost_basis` → `position_size` (converges with sd-005) | Section 3.2.2 Phase 6 |
| qc-val3b-rm-007 | Section 10.8 `/positions/monitor` clarified as consolidated into Phase 6 | Section 10.8 |
| qc-val3b-rm-008 | Appendix F.1 cross-reference "Section 2.3.2" → "Section 3.2.2 Phase 2" | Appendix F.1 |
| qc-val3b-rm-009 | FR-022 deferred to Phase 2 | Section 4.4; Section 9 |
| qc-val3b-rm-010 | Section 3.5 "See Also" FR range corrected | Section 3.5 |
| qc-val3b-rm-011 | Options config FR tags fixed: `option_time_stop_days` → FR-045, `option_expiration_protection_dte` → FR-044 | Section 3.3.4 |
| qc-val3b-rm-012 | Stock config FR tags fixed: breakeven → FR-030, time stop → FR-029 | Section 3.3.4 |
| qc-val3b-rm-013 | Config-driven implementation notes added to Section 3.3.4, Appendix F.2.4, F.4.2 | Section 3.3.4; Appendix F.2.4; Appendix F.4.2 |

**UI/UX Designer (UX) — 12 cards:**

| Card | Change | Sections Updated |
|------|--------|-----------------|
| qc-val3b-ux-001 | GET /positions response schema with `nearest_exit_distance_pct` | Appendix C.3 |
| qc-val3b-ux-002 | GET /signals/{id}/comments response schema (12 fields) | Appendix C.2 |
| qc-val3b-ux-003 | Sparkline fetching strategy: batch signals/history, lazy prices (max 5 concurrent), placeholder | Section 3.5.3 |
| qc-val3b-ux-004 | Signal card State 1 "Position Open": unrealized return % with color-coding | Section 3.5.1 |
| qc-val3b-ux-005 | `warnings` JSON array added to analysis_runs; results summary references warnings | Appendix B: analysis_runs; Section 3.5.4 |
| qc-val3b-ux-006 | GET /prices/{ticker} response schema | Appendix C.4 |
| qc-val3b-ux-007 | Position monitoring: 3 primary states + Market Closed overlay; "as of [last_run_completed_at]" | Section 3.5.1 |
| qc-val3b-ux-008 | Signal type pill: blue=Quality, purple=Consensus (mapped from signal_type); age label format spec | Section 3.5.1 |
| qc-val3b-ux-009 | GET /signals/history response schema (grouped by ticker, optional ticker param) | Appendix C.2 |
| qc-val3b-ux-010 | GET /portfolios response schema with computed convenience fields | Appendix C.3 |
| qc-val3b-ux-011 | Page reload recovery flow documented | Section 3.5.4 |
| qc-val3b-ux-012 | Schwab degradation: accepted for Phase 1, warnings field covers concern | Section 3.5.4 |

**Cross-Agent Convergences (5):**
- Cash formula: sd-002 + sd-003 + arch-001
- Column name `closed_date` → `exit_date`: sd-004 + arch-002 + rm-002
- Options pseudocode normalization: sd-001 + arch-003 + rm-001
- Return denominator `cost_basis` → `position_size`: sd-005 + arch-004 + rm-006

*Revised: 2026-02-06 (Phase 3b Re-Validation)*

### Phase 3c Second Re-Validation Amendments (v3.5, 2026-02-07)

34 Phase 3c second re-validation question cards resolved across 4 agents (6 cross-agent convergences):

**Software Developer (SD) — 14 cards:**

| Card | Change | Sections Updated |
|------|--------|-----------------|
| qc-val3c-sd-001 | Removed stale yfinance options fallback from monitoring data table (converges with rm-001, arch-001) | Section 4.7 |
| qc-val3c-sd-002 | Replaced "set skip_reason" with "skip position; log warning" in strike selection (converges with rm-002, arch-002) | Section 4.5 |
| qc-val3c-sd-003 | Wrapped POST /positions/{id}/close response in standard `{data, meta}` envelope | Appendix C.3 |
| qc-val3c-sd-004 | Standardized `premium_change` to `premium_change_pct` (decimal notation) in Phase 6 options monitoring | Section 3.2.2 Phase 6 |
| qc-val3c-sd-005 | Made volume_score formula explicit per signal type (Quality: users/threshold, Consensus: comments/threshold) | Section 4.4 |
| qc-val3c-sd-006 | Added explicit author_trust_score persistence step to Phase 3 pseudocode (converges with ux-002) | Section 3.2.2 Phase 3 |
| qc-val3c-sd-007 | Added note explaining direction/option_type intentional redundancy on positions table | Appendix B: positions |
| qc-val3c-sd-008 | Added explicit stop_loss_price/take_profit_price calculation at position creation in Phase 5 | Section 3.2.2 Phase 5 |
| qc-val3c-sd-009 | Documented dynamic skip_reason reliability: only `bearish_long_only` reliable; others show "not eligible" | Section 3.2.2 Phase 5 |
| qc-val3c-sd-010 | Added note that dedup'd comments retain original author_trust_score snapshot | Section 3.2.2 Phase 3 |
| qc-val3c-sd-011 | Added `'replaced'` exit_reason; detailed full close-then-open replacement flow in Phase 5 | Section 3.2.2 Phase 5; Appendix B: position_exits |
| qc-val3c-sd-012 | Added `hold_days` to GET /positions backend-computed convenience fields (converges with ux-001, arch-005) | Appendix C.3 |
| qc-val3c-sd-013 | Added cash guard (`cash_available >= position_size`) check to Phase 5 pseudocode | Section 3.2.2 Phase 5 |
| qc-val3c-sd-014 | Added known-limitation note about `position_opened` signal-level scope (converges with arch-004) | Section 3.2.2 Phase 5 |

**Architecture (ARCH) — 6 cards:**

| Card | Change | Sections Updated |
|------|--------|-----------------|
| qc-val3c-arch-001 | Removed stale yfinance options fallback (converges with sd-001, rm-001) | Section 4.7; Section 10.10 |
| qc-val3c-arch-002 | Replaced "set skip_reason" with log warning (converges with sd-002, rm-002) | Section 4.5 |
| qc-val3c-arch-003 | Added warnings event catalog (5 types) and write mechanism to Phase 6 (converges with arch-006, ux-006) | Section 3.2.2 |
| qc-val3c-arch-004 | Documented position_opened signal-level limitation for partial portfolio failures (converges with sd-014) | Section 3.2.2 Phase 5 |
| qc-val3c-arch-005 | Documented hold_days semantic divergence between GET /positions and GET /signals (converges with sd-012, ux-001) | Appendix C.3 |
| qc-val3c-arch-006 | Added `warnings` to GET /runs/{id}/status response (converges with arch-003, ux-006) | Appendix C.1 |

**Requirements Manager (RM) — 6 cards:**

| Card | Change | Sections Updated |
|------|--------|-----------------|
| qc-val3c-rm-001 | Removed stale yfinance options fallback (converges with sd-001, arch-001) | Section 4.7; Section 10.10 |
| qc-val3c-rm-002 | Replaced "set skip_reason" with log warning (converges with sd-002, arch-002) | Section 4.5 |
| qc-val3c-rm-003 | Added Appendix F entry to Table of Contents | Table of Contents |
| qc-val3c-rm-004 | Updated F.4.1 to use `accuracy_neutral_threshold` from system_config (not hardcoded 1.0) | Appendix F.4.1 |
| qc-val3c-rm-005 | Updated stale "EOD" references to "intraday monitoring via Schwab API" in Sections 10.5 and 10.8 | Section 10.5; Section 10.8 |
| qc-val3c-rm-006 | Updated F.4.1 to use `comment_tickers.sentiment` (per-ticker) instead of `comment.sentiment` | Appendix F.4.1 |

**UI/UX Designer (UX) — 8 cards:**

| Card | Change | Sections Updated |
|------|--------|-----------------|
| qc-val3c-ux-001 | Documented hold_days semantic divergence (converges with sd-012, arch-005) | Appendix C.3 |
| qc-val3c-ux-002 | Added `author_trust_score` to GET /signals/{id}/comments response (converges with sd-006) | Appendix C.2 |
| qc-val3c-ux-003 | Added GET /status JSON response schema | Appendix C.5 |
| qc-val3c-ux-004 | Added GET /evaluation-periods JSON response schema | Appendix C.4 |
| qc-val3c-ux-005 | Added options position example to GET /positions response | Appendix C.3 |
| qc-val3c-ux-006 | Added warnings rendering rules (0: omit, 1-3: inline, 4+: expandable) (converges with arch-003, arch-006) | Section 3.5.4 |
| qc-val3c-ux-007 | Added age label UTC computation note with ≤1 day ET discrepancy documentation | Section 3.5.1 |
| qc-val3c-ux-008 | Added exit_reason human-readable label mapping (8 values including 'replaced') | Section 3.5.1 |

**Cross-Agent Convergences (6):**
- yfinance options fallback removal: sd-001 + rm-001 + arch-001
- Strike selection skip_reason → log warning: sd-002 + rm-002 + arch-002
- author_trust_score in API + pseudocode: sd-006 + ux-002
- position_opened signal-level limitation: sd-014 + arch-004
- hold_days semantic divergence documentation: sd-012 + ux-001 + arch-005
- warnings infrastructure (catalog + API + rendering): arch-003 + arch-006 + ux-006

### Schema Changes Summary (v3.5)
- **Modified tables:** position_exits (`'replaced'` added to exit_reason enum)
- **No new tables, no removed tables** (still 13 total)
- **API contract additions:** GET /status response schema, GET /evaluation-periods response schema, `warnings` added to GET /runs/{id}/status, `author_trust_score` added to GET /signals/{id}/comments, options position example in GET /positions, POST /positions/{id}/close wrapped in standard envelope, `hold_days` documented as convenience field

*Revised: 2026-02-07 (Phase 3c Second Re-Validation)*
