---
id: epic-007
title: REST API & Async Polling Infrastructure
requirements: [API-ANALYZE, API-RUNS, API-RUN-STATUS, API-SIGNALS, API-SIGNAL-DETAIL, API-SIGNAL-COMMENTS, API-SIGNALS-HISTORY, API-PORTFOLIOS, API-PORTFOLIO-DETAIL, API-POSITIONS, API-POSITION-DETAIL, API-POSITION-CLOSE, API-EVAL-PERIODS, API-PRICES, API-STATUS, API-ENVELOPE, API-PAGINATION, API-ERROR-CODES, API-ASYNC, API-STALE-RECOVERY, API-TIMEOUT, ERR-TIER1, ERR-TIER2, ERR-TIER3, ERR-TIER4, ERR-LOGGING, ERR-SQLITE, ERR-DEDUP, ERR-RUN-TIMEOUT, PIPE-055, PIPE-056, NFR-004, NFR-005, API-PREDICTIONS, API-PREDICTION-OVERRIDE]
priority: high
estimated_stories: 10
estimated_story_points: 28
---

# Epic: REST API & Async Polling Infrastructure

## Description
Implement FastAPI REST API layer with 20+ endpoints for analysis orchestration, signal browsing, position monitoring, and portfolio tracking. Split into two phases: **Phase 7a** provides early GET scaffolding enabling frontend parallelism, and **Phase 7b** adds background thread orchestration and mutation endpoints after pipeline epics complete. Includes async POST /analyze pattern (returns HTTP 202 with run_id, background thread runs 10-30 min pipeline, frontend polls every 10s), startup recovery for stale runs, standard response envelope, pagination, 4-tier error boundaries, and warnings event catalog.

## Requirements Traced

### Core API Endpoints (20+)
- **API-ANALYZE**: POST /analyze (trigger pipeline, HTTP 202 + run_id, HTTP 409 if running)
- **API-RUNS**: GET /runs (list analysis runs with timestamps and status)
- **API-RUN-STATUS**: GET /runs/{id}/status (poll progress: status, phase, phase_label, progress, results, warnings)
- **API-SIGNALS**: GET /signals (list with filters: ticker, signal_type, date_from, date_to, portfolio_id; includes position_summary + skip_reason)
- **API-SIGNAL-DETAIL**: GET /signals/{id} (single signal with full details)
- **API-SIGNAL-COMMENTS**: GET /signals/{id}/comments (comments with AI annotations via junction, includes author_trust_score + ticker_sentiments)
- **API-SIGNALS-HISTORY**: GET /signals/history (historical confidence for sparklines, grouped by ticker, params: ticker optional, signal_type, days default 14)
- **API-PORTFOLIOS**: GET /portfolios (all 4 with summary: value, cash, open_position_count, total_pnl, total_pnl_pct)
- **API-PORTFOLIO-DETAIL**: GET /portfolios/{id} (single portfolio with allocation breakdown)
- **API-POSITIONS**: GET /positions (list with filters: portfolio_id, status, ticker, instrument_type, signal_type; includes position_exits + convenience fields)
- **API-POSITION-DETAIL**: GET /positions/{id} (single position with exit strategy state + full position_exits history)
- **API-POSITION-CLOSE**: POST /positions/{id}/close (manual early exit: reason required, quantity_pct optional default 1.0, creates position_exits record, supports partial)
- **API-EVAL-PERIODS**: GET /evaluation-periods (30-day performance vs S&P 500, param: portfolio_id required, active + completed periods with metrics)
- **API-PRICES**: GET /prices/{ticker} (price history for sparklines, param: days default 14, returns daily close via yfinance)
- **API-STATUS**: GET /status (system health: phase, emergence_active, emergence_days_remaining, open_position_count, last_run_completed_at, active_run_id)

### API Infrastructure
- **API-ENVELOPE**: Standard response envelope {data, meta: {timestamp, version}}; errors: {error: {code, message}}
- **API-PAGINATION**: List endpoints: limit (default 50, max 100), offset; response includes total count
- **API-ERROR-CODES**: VALIDATION_ERROR, NOT_FOUND, ANALYSIS_ALREADY_RUNNING, REDDIT_API_ERROR, OPENAI_API_ERROR, SCHWAB_AUTH_ERROR, DATABASE_ERROR
- **API-ASYNC**: POST /analyze async pattern (HTTP 202 immediate return, background thread, isolated SQLite connection, single-run enforcement via HTTP 409)
- **API-STALE-RECOVERY**: On startup, set status='running' records to 'failed' with error message (prevents lockout after crash)
- **API-TIMEOUT**: Frontend timeout 30s for standard endpoints, polling 10s intervals with no overall timeout

### Error Handling (4-tier model)
- **ERR-TIER1**: Hard fail (Reddit outage, SQLite write failure) → log + rollback + HTTP 5xx
- **ERR-TIER2**: Retry with backoff (transient API failures) → exponential 1s-30s, 3-5 retries, escalate to Tier 1 if exhausted
- **ERR-TIER3**: Graceful degradation (image analysis, single comment failure) → retry 3x, continue with NULL/default
- **ERR-TIER4**: Log and continue (comment dedup, missing yfinance) → info log, continue
- **ERR-LOGGING**: Structured JSON to logs/backend.log (DEBUG, INFO, WARNING, ERROR, CRITICAL), full stack traces on errors
- **ERR-SQLITE**: Write failure → rollback, log full trace, return HTTP 500
- **ERR-DEDUP**: Unique constraint violation → catch, skip insert, continue
- **ERR-RUN-TIMEOUT**: 60-min hard timeout sets status='failed', 30-min soft warning logged

### Warnings Event Catalog
- **PIPE-055**: 7 warning types (schwab_stock_unavailable, schwab_options_unavailable, image_analysis_failed, market_hours_skipped, insufficient_cash, schwab_prediction_unavailable, prediction_strike_unavailable), JSON array on analysis_runs
- **PIPE-056**: Append warning objects in-memory during run, serialize to JSON on completion, NULL if empty

### Performance Requirements
- **NFR-004**: ≤30 min analysis time (warn if exceeded), 60-min hard timeout sets status='failed'
- **NFR-005**: 3× daily usage support (on-demand up to ~3 times/day)

## Technology Decisions

Resolved during Phase 1 planning questions:

- **Input Validation:** Pydantic models for all request/response schemas [qc-sec-002]
- **Pipeline Orchestration:** Phase registry pattern — each pipeline phase is a discrete callable, orchestrator invokes sequentially [qc-arch-001]
- **Logging:** structlog JSON-formatted structured logging [qc-sd-004]

## Technical Scope

### Database Tables Affected
All tables (API provides read/write access to entire schema)

### API Endpoints Included
20+ REST endpoints (see requirements list)

### External Integrations Involved
None directly (API layer orchestrates other Epics' integrations)

### Key Algorithms/Logic
- **Background thread orchestration**: Separate SQLite connection, wrap entire pipeline in try/except, update analysis_runs status
- **Single-run enforcement**: Check status='running' before starting, return HTTP 409 if exists
- **Startup recovery**: On FastAPI startup, query status='running' records, set to 'failed'
- **Progress tracking**: Update current_phase, phase_label, progress_current, progress_total at phase boundaries
- **Warnings accumulation**: Append to in-memory list during run, serialize to JSON at completion
- **Dynamic skip_reason**: Computed per-portfolio in GET /signals (only bearish_long_only reliably computable, others generic "not eligible")
- **Convenience fields**: current_price, unrealized_return_pct, nearest_exit_distance_pct, hold_days, dte, premium_change_pct computed on-demand
- **Standard envelope**: Wrap all responses, inject timestamp + version in meta

## Dependencies

### Phase 7a (Early Scaffold — after epic-001, Weeks 2-3)
- Depends on: epic-001 (database schema only)
- Provides: FastAPI app setup, standard envelope, CRUD GET endpoints (signals, positions, portfolios, etc.), seed test data script
- Enables: epic-008 (Vue dashboard) can start consuming GET endpoints with seed data

### Phase 7b (Pipeline Integration — after epic-006, Weeks 10-12)
- Depends on: epic-001 through epic-006 (full pipeline must be functional)
- Provides: Background thread orchestration, POST /analyze, startup recovery, POST /positions/{id}/close
- Blocks: Full end-to-end testing

## Risk Assessment

**Complexity:** Medium-High

**Key Risks:**
1. **Background thread isolation**: Separate SQLite connection required (WAL mode enables concurrent reads)
   - *Mitigation*: Test with concurrent GET requests during background run
2. **Startup recovery edge cases**: What if crash during Phase 1? (Answer: set status='failed', user can retry)
   - *Mitigation*: Explicit recovery logic on FastAPI startup
3. **Dynamic skip_reason calculation**: Transient reasons (no_valid_strike, insufficient_cash) not stored, only bearish_long_only reliable
   - *Known limitation*: Documented in PRD Phase 3c (SD-009), acceptable for Phase 1
4. **Convenience field performance**: Computing on-demand for 40 positions may be slow
   - *Mitigation*: Optimize with SELECT subqueries, index positions table
5. **Warnings array serialization**: Large warning arrays (e.g., 40 insufficient_cash events) may bloat analysis_runs records
   - *Acceptable*: JSON TEXT column handles this, gzip if needed
6. **HTTP 409 lockout**: If startup recovery fails, user may be locked out
   - *Mitigation*: Manual SQL to reset status if needed (document in operations guide)

**Overall Risk Level:** Medium

## Estimated Stories

### Phase 7a — Early Scaffold (~10 pts, Weeks 2-3)

1. **FastAPI Application Setup**: App initialization, CORS, startup/shutdown events, structlog config
2. **Standard Response Envelope**: Wrapper function for {data, meta}, error responses {error: {code, message}}, Pydantic models
3. **CRUD GET Endpoints**: 15+ GET endpoints with filters, pagination, convenience fields (signals, positions, portfolios, runs, prices, status, evaluation-periods)
4. **Seed Test Data Script**: Populate database with realistic mock data for frontend development (~2 pts)

### Phase 7b — Pipeline Integration (~13 pts, Weeks 10-12)

5. **Background Thread Pipeline Orchestration**: Separate SQLite connection, try/except wrapper, status tracking, phase registry invocation
6. **POST /analyze Async Pattern**: HTTP 202 immediate return, run_id generation, HTTP 409 enforcement
7. **Startup Recovery Logic**: Query status='running' on startup, set to 'failed' with error message
8. **POST /positions/{id}/close Manual Exit**: Request validation (reason required, quantity_pct), INSERT position_exits, UPDATE positions
9. **Prediction API Endpoints (Phase 7b)**: GET /predictions (filters: author, ticker, status, analysis_run_id), GET /predictions/{id} (with prediction_outcomes + prediction_exits history), PATCH /predictions/{id}/override (correct/incorrect/excluded). Acceptance criteria: override validates only correct/incorrect/excluded values, PATCH is idempotent, filter combinations tested. (~2 pts) [API-PREDICTIONS, API-PREDICTION-OVERRIDE]
10. **API Endpoint Unit Tests**: 10 tests covering pagination boundaries, invalid filters, NOT_FOUND, concurrent 409 rejection, startup recovery, manual close validation, response envelope structure. (~3 pts) [QA review gap]
