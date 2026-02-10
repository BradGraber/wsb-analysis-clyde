# WSB Analysis Tool - Technical Brief

**Version:** 3.6 | **Date:** 2026-02-07

## System Architecture

Three-tier: FastAPI backend (acquisition, AI, signals, positions), SQLite (persistent storage, `./data/wsb.db`), Vue.js dashboard (visualization). Deployment: local-first, single-user, experimental.

**External Dependencies:**

| Integration | Purpose | Auth | Critical |
|---|---|---|---|
| Reddit (PRAW) | WSB posts/comments | OAuth2 (.env) | Yes |
| OpenAI GPT-4o-mini | Sentiment, sarcasm, image analysis | API Key (.env) | Yes |
| Schwab API | Real-time quotes, 5-min candles, options chains+greeks | OAuth 2.0 (token file) | No (retry+skip) |
| yfinance | Historical prices, S&P 500 benchmark, fallback | None | No (graceful degradation) |

## Backend Pipeline: POST /analyze

Returns HTTP 202 with `run_id`, executes 7 phases in background thread (10-30 min). Single-run enforcement: HTTP 409 if analysis running. Frontend polls GET /runs/{run_id}/status every 10s.

**Phase 1: Acquisition** — Reddit OAuth2, fetch top 10 "hot" posts from r/wallstreetbets, top 1000 comments/post by engagement, synchronous image analysis (GPT-4o-mini vision), build parent chain context.

**Phase 2: Prioritization** — Score: financial keyword density (0.4) + author trust (0.3) + engagement (0.3) - depth penalty. Select top 50 comments/post (~500 total).

**Phase 3: Analysis** — Check dedup by `reddit_id`: if exists, reuse annotations, UPDATE `analysis_run_id`. If new: OpenAI GPT-4o-mini individual call (1 comment/call), parse JSON (tickers, ticker_sentiments, sentiment, sarcasm_detected, has_reasoning, confidence, reasoning_summary). Commit batches of 5 (cost protection). Store per-ticker sentiment in `comment_tickers`.

**Phase 3.5: Prediction Creation** — Batch Schwab options chain fetch/ticker. Create prediction per comment_ticker: strike delta ~0.30, 14-21 DTE (same logic as Phase 5). If no valid strike or Schwab unavailable: status='expired', append warning.

**Phase 4: Signal Detection** — Group by ticker+signal_date (UTC day). **Quality:** >=2 users, reasoning=true, sarcasm=false, ai_confidence>=0.6, unanimous direction. **Consensus:** >=30 comments, >=8 users, >=70% alignment. Signal confidence = volume(25%) + alignment(25%) + avg_ai_confidence(30%) + avg_author_trust(20%). **Emergence:** ticker cold (<3 mentions in 7d) then hot (>=13 mentions, >=8 users), requires 7d history (else NULL). Upsert: UNIQUE(ticker, signal_type, signal_date).

**Phase 5: Position Management** — Check market hours (9:30-16:00 ET); if outside, skip opens. Identify signals: confidence>=0.5, position_opened=false. Open in 2 portfolios/signal (stocks+options for that type). **Stocks long-only Phase 1:** Skip bearish for stock portfolios. Check limit (10/portfolio); if at limit, replace lowest-confidence if new exceeds by >0.1 AND lowest unrealized <=+5%. Cash guard: skip if cash_available < position_size. Calculate stop_loss_price, take_profit_price at creation. Set signal.position_opened=true (signal-level).

**Phase 6: Price Monitoring** — Derive last_check_time: first run uses current run's started_at; subsequent use most recent completed run's started_at. Strategy: if last_check within today, Schwab 5-min candles; if previous day(s), yfinance daily OHLC for gaps then Schwab for today. **Stocks:** Schwab real-time quote + 5-min candles; period_high/period_low catch intraday breaches. Exit priority: (1) Stop-loss: -10% close 100%. (2) Take-profit: +15% close 50%, trailing_active. (3) Trailing: peak*0.93 remainder. (4) Breakeven: +5% AND Day 5, raise stop to entry. (5) Time: Day 5 (<+5%), Day 7 (+5-15%), Day 10 (unconditional). **Options:** Schwab premium+greeks. Exit priority: (1) Expiration: DTE<=2 close 100%. (2) Stop-loss: -50% close 100%. (3) Take-profit: +100% close 50%, trailing_active. (4) Trailing: peak*0.70 remainder. (5) Time: Day 10 close 100%. Each exit: INSERT position_exits, UPDATE positions (decrement remaining), UPDATE portfolio (cash += proceeds-only), recalc current_value. UPSERT daily OHLC to price_history. **Prediction monitoring:** expired-past-expiration, monitor active with shared exit logic, INSERT prediction_exits, resolve when fully exited.

**Phase 7: Post-Analysis** — **7a. Author Trust:** Increment total_comments, high_quality_comments, total_upvotes; recalc avg_conviction_score; update avg_sentiment_accuracy from resolved predictions using EMA. **7b. Evaluation Periods:** All 4 portfolios share 30-day window; if no active, create 4 rows; if expired, complete and create new.

## Error Handling (4-Tier)

| Tier | Scope | Response |
|---|---|---|
| 1: Hard Fail | Critical path | Rollback, HTTP 5xx, abort |
| 2: Retry | Transient API | Exponential backoff (1s,2s,4s,8s max 30s), 3-5 retries |
| 3: Degradation | Non-critical | Retry 3x, log warning, NULL |
| 4: Log | Expected variation | Log info, continue |

**Warnings:** schwab_stock_unavailable, schwab_options_unavailable, image_analysis_failed, market_hours_skipped, insufficient_cash, schwab_prediction_unavailable, prediction_strike_unavailable. Appended to `analysis_runs.warnings` (JSON array).

## Data Model

**7 Layers:** (1) Configuration (system_config), (2) Source Data (reddit_posts, authors, comments, analysis_runs), (3) Junction (signal_comments, comment_tickers), (4) Analytics (signals), (5) Trading (portfolios, positions, position_exits, price_history), (6) Predictions (predictions, prediction_outcomes, prediction_exits), (7) Evaluation (evaluation_periods).

**Constraints:** Unique signal/day (ticker, signal_type, signal_date), comment dedup (reddit_id UNIQUE), PRAGMA foreign_keys=ON, 10 positions/portfolio (app-enforced), 4 portfolios ($100k each isolated).

**Configuration:** 33 `system_config` entries: signal detection (quality_min_users=2, quality_min_confidence=0.6, consensus_min_comments=30, consensus_min_users=8, consensus_min_alignment=0.7), confidence weights (volume 0.25, alignment 0.25, ai_confidence 0.30, author_trust 0.20), author trust (quality 0.40, accuracy 0.50, tenure 0.10, default_accuracy 0.50, tenure_saturation_days 30, ema_weight 0.30), stock exits (stop_loss -0.10, take_profit 0.15, trailing_stop 0.07, breakeven_trigger 0.05, breakeven_min_days 5, time_stop_base 5, time_stop_base_min_gain 0.05, time_stop_extended 7, time_stop_max 10, take_profit_exit_pct 0.50), options exits (stop_loss -0.50, take_profit 1.00, trailing_stop 0.30, time_stop 10, expiration_protection_dte 2, take_profit_exit_pct 0.50), system (system_start_date, phase).

**Schema Init:** PRAGMA foreign_keys=ON + journal_mode=WAL, INSERT 33 system_config, INSERT 4 portfolios $100k, set system_start_date=today.

## REST API

**Philosophy:** Stateless, async analysis (202), envelope {data, meta}, pagination (default 50, max 100), filter-friendly query params.

**6 Categories:** (1) Analysis: POST /analyze, GET /runs, GET /runs/{id}/status. (2) Signals: GET /signals, GET /signals/{id}, GET /signals/{id}/comments, GET /signals/history. (3) Portfolio: GET /portfolios, GET /portfolios/{id}. (4) Positions: GET /positions, GET /positions/{id}, POST /positions/{id}/close. (5) Validation: GET /evaluation-periods, GET /prices/{ticker}. (6) System: GET /status.

**Key Behaviors:** POST /analyze HTTP 202 with run_id, 409 if running, background thread isolated connection, startup crash recovery (stale 'running' to 'failed'). GET /runs/{id}/status: polled 10s, returns status, current_phase, progress, signals_created, positions_opened, exits_triggered, error_message, warnings. GET /signals with portfolio_id: adds position_opened, skip_reason (computed), position_summary.

## Vue Dashboard

**State:** No persistent state (loads Stock/Quality default), session-local only, no auto-refresh.

**Structure:** Four tabs: Stock/Quality (default), Stock/Consensus, Options/Quality, Options/Consensus. Sub-tabs: Signals (default), Positions, Performance.

**Signal Card:** Row 1 (ticker, direction, confidence badge, comment count, type pill, age); Row 2 (dual sparklines: confidence history + price trajectory 7-14d, emergence flag). Adaptive: <=2 points = dots, 3+ = line.

**Position Status:** Open (green, unrealized %), Closed (gray, realized %), Below threshold (<0.5), Not eligible (tooltip).

**Monitoring:** Active, Near Exit (amber, <=0.02 distance), Partially Closed (remaining %), Market Closed overlay.

**Page Recovery:** GET /status returns active_run_id; if non-null, resume polling.

## Authentication & Security

| Integration | Method | Storage |
|---|---|---|
| Dashboard to Backend | None | N/A (local single-user) |
| Backend to Reddit | OAuth2 (PRAW) | .env: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT |
| Backend to OpenAI | API Key | .env: OPENAI_API_KEY |
| Backend to yfinance | None | N/A (public) |
| Backend to Schwab | OAuth 2.0 (Auth Code Grant) | .env: SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET, SCHWAB_CALLBACK_URL; Token: ./data/schwab_token.json |

**Schwab:** CLI setup (one-time), access token 30-min TTL (auto-refresh), refresh token 7d TTL (auto-renew if active weekly, else manual re-auth), graceful degradation (retry 3x, skip tickers).

## AI Analysis

**Strategy:** Individual (1 comment/call), full context (post image, author trust, parent chain). **Response:** JSON: tickers[], ticker_sentiments[], sentiment, sarcasm_detected, has_reasoning, confidence, reasoning_summary. **Mapping:** sarcasm_detected to comments.sarcasm_detected, has_reasoning to comments.has_reasoning, sentiment to comments.sentiment, ticker_sentiments to comment_tickers, confidence to comments.ai_confidence, reasoning_summary to comments.reasoning_summary. **Ticker Rules:** Explicit ($AAPL, AAPL), normalize uppercase, resolve names ("the mouse" to DIS), exclude non-tickers (I, A, CEO, DD, YOLO), include crypto, deduplicate.

## Author Trust

**Trust:** (quality_ratio * 0.40) + (accuracy * 0.50) + (tenure * 0.10). quality_ratio=high_quality/max(total,1), accuracy=avg_sentiment_accuracy (0.5 if NULL), tenure=min(1.0, days_active/30).

**Conviction:** (length_factor * 0.20) + (reasoning_bonus * 0.20) + (ai_confidence * 0.60). length=min(1.0, chars/500), reasoning=1.0 if has_reasoning.

**Accuracy:** Predictions from comment_tickers, monitored by Phase 6 with Schwab premiums, EMA update: new=(1-weight)*old + weight*new. Cold start: NULL until first resolves (~2-4 weeks), uses 0.5.

## Portfolios & Positions

**Four Portfolios:** stocks_quality, stocks_consensus, options_quality, options_consensus. Each $100k, max 10 open.

**Sizing:** Stocks: base=value/20, confidence tier (0.5x/0.75x/1.0x), min 2% max 15%. Options: fixed 2%, strike delta ~0.30 (calls [+0.15,+0.50], puts [-0.50,-0.15]), 14-21 DTE, contracts=floor(size/(premium*100)).

**Value:** current_value = cash + SUM(stock positions) + SUM(option positions). Open: cash -= cost. Close: cash += proceeds (proceeds-only).

## Evaluation Framework

**30-Day Windows:** 4 portfolios share window (4 rows lockstep). Metrics: portfolio_return_pct, sp500_return_pct, relative_performance, beat_benchmark.

**Graduation (90d):** 3 consecutive periods: (1) >=2 of 3 beat S&P, (2) no period loses >15% relative, (3) same signal type best across all three. Stocks only (options supplementary).

## Technical Stack & Constraints

FastAPI (Python), SQLite, Vue.js 3 (Composition API), PRAW, OpenAI GPT-4o-mini (~$45/mo), Schwab API (OAuth 2.0), yfinance, Chart.js/vue-sparklines, Tailwind/Bootstrap. Total ~$46-47/mo.

**Constraints:** Experimental, single-user, swing trading, cost-conscious (GPT-4o-mini), desktop only.

**Out of Scope:** Automated trading, intraday/HFT, other subreddits, mobile, alerts, multi-user, production hardening, FR-022 Annotation Pattern Analysis.

**Directory:** src/backend/ (FastAPI), src/frontend/ (Vue.js), src/data/ (SQLite, Schwab tokens), .env (API keys).
