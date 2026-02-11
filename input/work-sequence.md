# Work Sequencing Plan

**Date:** 2026-02-08
**PRD Version:** v3.6
**Total Tasks:** 154 across 9 epics (316 complexity points, 332 story points)
**Developer:** Solo developer (personal tool)
**Timeline Target:** 13-16 weeks with continuous flow and phase milestones

---

## 1. Implementation Phases (Milestones)

### Phase A: Foundation (Weeks 1-2)

**Goal:** Establish database schema, prove Schwab OAuth works, validate SQLite concurrency, set up error handling infrastructure, and scaffold the API layer for frontend parallelism.

**Epics/Stories Included:**
- epic-001 (all 8 stories, 14 tasks, ~26 complexity)
- epic-007 Phase 7a: stories 007-001 through 007-004 (8 tasks, ~15 complexity)

**Entry Criteria:**
- PRD v3.6 finalized
- Development environment ready (Python, Node.js, SQLite)
- Schwab developer account approved with API credentials
- Reddit API credentials available
- OpenAI API key available

**Exit Criteria:**
- All 16 database tables created and validated
- 34 system_config entries seeded with correct defaults
- 4 portfolios initialized at $100k each
- Schwab OAuth spike complete: CLI setup script works, token stored with chmod 600, stock quote and options chain fetch verified
- SQLite WAL concurrency spike passes (background write + main thread read)
- `retry_with_backoff()`, `WarningsCollector`, and structlog configured
- `get_connection()` context manager operational with FK enforcement + WAL
- FastAPI app running with CORS, lifespan, and structlog
- Standard response envelope and Pydantic models defined
- All 15+ GET endpoints returning data (with seed test data)
- Seed data script populates realistic mock data for frontend development
- `uvicorn` serves API, Vue dev server can proxy to it

**Estimated Duration:** 2 weeks (~41 complexity points)

**Risk Notes:**
- **Schwab OAuth spike (HIGH):** If Schwab API access is denied or approval delayed, the spike fails. Mitigation: time-boxed to 2-3 days; if blocked, document findings and defer Schwab-dependent work to later phases while proceeding with yfinance-only fallback path.
- **WAL concurrency spike (LOW):** SQLite WAL is proven technology. Spike is 0.5 days.

---

### Phase B: Data Pipeline + AI Analysis (Weeks 3-5)

**Goal:** Build the Reddit data acquisition pipeline and AI sentiment analysis engine. After this phase, the system can fetch WSB posts, prioritize comments, analyze them with GPT-4o-mini, and store AI-annotated results.

**Epics/Stories Included:**
- epic-002 (9 stories, 14 tasks, ~24 complexity)
- epic-003 (11 stories, 16 tasks, ~33 complexity)
- epic-008 early stories: 008-001, 008-002, 008-004 sparkline spike (6 tasks, ~10 complexity)

**Entry Criteria:**
- Phase A complete (database, connection manager, error utilities, API scaffold with seed data)

**Exit Criteria:**
- Async PRAW client authenticates and fetches top 10 hot posts from r/wallstreetbets
- Image detection works for 3 URL patterns; GPT-4o-mini vision analysis with retry
- Up to 1000 comments fetched per post with parent chain context
- Priority scoring selects top 50 comments per post (~500 total)
- Comment deduplication prevents redundant AI costs
- OpenAI client sends concurrent batch-of-5 requests via ThreadPoolExecutor
- AI responses parsed (tickers, sentiment, sarcasm, reasoning, confidence)
- Batch-of-5 transaction commits protect against crash data loss
- comment_tickers junction records populated
- Cost tracking logs warnings above $60/month
- Vue scaffold running with tabs, sub-tabs, and shared composables
- Sparkline spike completed with recommendation document

**Estimated Duration:** 3 weeks (~67 complexity points)

**Risk Notes:**
- **OpenAI rate limiting (MEDIUM):** 429 responses may slow pipeline. Exponential backoff handles this.
- **Async PRAW rate limiting (LOW):** Async PRAW handles 60 req/min automatically.
- **Malformed JSON responses (MEDIUM):** Retry once, skip on failure, log for review.
- **Concurrent batching race conditions (MEDIUM):** Thread-safe data structures required.

---

### Phase C: Signal Detection + Position Management (Weeks 6-8)

**Goal:** Detect Quality and Consensus signals from AI-annotated comments, calculate confidence scores, and open positions in 4 portfolios with confidence-weighted sizing.

**Epics/Stories Included:**
- epic-004 (7 stories, 9 tasks, ~18 complexity)
- epic-005 (9 stories, 14 tasks, ~32 complexity)

**Entry Criteria:**
- Phase B complete (AI-annotated comments in database with comment_tickers populated)

**Exit Criteria:**
- Quality signals detected (>=2 users with reasoning, unanimous direction, AI confidence >=0.6)
- Consensus signals detected (>=30 comments, >=8 users, >=70% alignment)
- 4-factor confidence scores calculated with config-driven weights
- Emergence detection working with 7-day baseline
- Daily signal rollup UPSERT operational
- Market hours gate prevents position opens outside 9:30-16:00 ET
- Qualified signals (confidence >=0.5) identified and processed
- Confidence-weighted sizing applied (3-tier stocks, fixed 2% options)
- Position limits enforced (10 per portfolio) with replacement logic
- Options strike selection via Schwab chains (DTE 14-21, delta ~0.30)
- Cash guard prevents overdraft
- Stop-loss and take-profit calculated at entry
- Positions opened in all 4 portfolios (stocks/options x quality/consensus)

**Estimated Duration:** 2.5 weeks (~50 complexity points)

**Risk Notes:**
- **Options strike selection (HIGH):** Complex Schwab options chain iteration. Well-defined fallback (skip if no valid strike).
- **Replacement logic edge cases (MEDIUM):** All positions at >+5% gain means no replacement possible (acceptable).
- **Market hours timezone (LOW):** pytz handles EST/EDT correctly.

---

### Phase D: Stock Exit Strategies + Price Monitoring (Weeks 8-10)

**Goal:** Implement price monitoring infrastructure and all 7 stock exit conditions. This is the first half of epic-006, ending at the midpoint checkpoint.

**Epics/Stories Included:**
- epic-006 stories 001-004, 008-012, 015 (stock exits, candle engine, partial exits, peak tracking, close finalization, price history, MonitoredInstrument Protocol): ~18 tasks, ~44 complexity
- epic-008 stories 003, 005-008 (signal cards, sparklines, evidence modal, position list, options display): ~14 tasks, ~26 complexity

**Entry Criteria:**
- Phase C complete (open positions in database to monitor)

**Exit Criteria:**
- last_check_time derived from analysis_runs
- Tiered price data fetching working (same-day Schwab 5-min, multi-day yfinance + Schwab)
- Candle iteration engine processes all open stock positions in priority order
- All 7 stock exit conditions implemented and individually testable:
  - Stop-loss (-10%)
  - Take-profit (+15%)
  - Partial take-profit (50% exit at +15%, trailing stop on remainder)
  - Trailing stop (-7% from peak)
  - Breakeven promotion (at +5% gain, Day 5)
  - Time-based exit (base 5 days, extended 7, trailing 10)
  - Three-tier time extension logic
- Partial exit mechanics (position_exits INSERT, shares_remaining UPDATE, cash proceeds)
- Peak price tracking updated after every check
- Full close finalization (status='closed', exit_date, hold_days, realized_return_pct)
- Price history UPSERT working
- MonitoredInstrument Protocol defined with runtime_checkable
- **MIDPOINT CHECKPOINT:** Velocity check before proceeding to options exits
- Signal cards, dual sparklines, evidence modal, position list, and options display working in dashboard

**Estimated Duration:** 2.5 weeks (~70 complexity points)

**Risk Notes:**
- **Candle iteration complexity (HIGH):** Multiple triggers in same candle, priority ordering. Well-defined: first breach wins.
- **Multi-day gap handling (HIGH):** yfinance daily OHLC for gaps + Schwab for today, chronological merge.
- **Partial exit cash calculation (MEDIUM):** proceeds-only formula, options include x100 multiplier.
- **MIDPOINT CHECKPOINT:** If velocity significantly under budget, reassess timeline before proceeding.

---

### Phase E: Options Exits + Prediction Monitoring (Weeks 10-12)

**Goal:** Complete all 5 options exit conditions, integrate prediction monitoring into the exit loop, and run all exit strategy unit tests. This is the second half of epic-006.

**Epics/Stories Included:**
- epic-006 stories 005-007, 013-014, 016-021 (options exits, Schwab retry, token health, exit tests, prediction monitoring, prediction tests): ~13 tasks, ~36 complexity
- epic-008 stories 009-011 (progress indicator, reload recovery, token banner, empty states, error handling): ~8 tasks, ~14 complexity

**Entry Criteria:**
- Phase D complete (stock exits working, midpoint checkpoint passed)
- MonitoredInstrument Protocol defined

**Exit Criteria:**
- All 5 options exit conditions implemented:
  - Expiration protection (DTE <=2, highest priority)
  - Premium stop-loss (-50%)
  - Premium take-profit (+100%, 50% exit, trailing on remainder)
  - Premium trailing stop (-30% from peak)
  - Time stop (10 days)
- Schwab retry with exponential backoff, yfinance fallback for stocks
- Token health check endpoint (GET /auth/status)
- 19 exit strategy unit tests passing (7 stock + 5 options + 3 partial + 2 peak + 2 time)
- 2 concurrency unit tests passing (Schwab quote fetches across 40 positions)
- Prediction monitoring in exit loop: tracking predictions processed alongside real positions
- 7 prediction monitoring unit tests + 5 edge case tests passing
- Schwab auth error handling (proactive refresh, fallback to yfinance)
- Progress indicator, reload recovery, token banner, empty states working in dashboard

**Estimated Duration:** 2.5 weeks (~50 complexity points)

**Risk Notes:**
- **Exit priority cascade for options (HIGH):** Expiration takes precedence; must handle DTE crossing between runs.
- **Prediction monitoring complexity (HIGH):** Full exit cascade on predictions via protocol; no cash impact.
- **Schwab auth lifecycle (MEDIUM):** Proactive refresh before expiration, 401 retry, fallback path.

---

### Phase F: API Integration + Dashboard Completion + Author Trust (Weeks 12-15)

**Goal:** Wire up the full pipeline through the API layer, complete the dashboard with all remaining views, implement author trust scoring and evaluation periods.

**Epics/Stories Included:**
- epic-007 Phase 7b: stories 007-005 through 007-010 (8 tasks, ~13 complexity)
- epic-009 (7 stories, 12 tasks, ~20 complexity)
- epic-008 stories 012-016 (integration tests, E2E tests, prediction tracking, performance view): ~12 tasks, ~20 complexity

**Entry Criteria:**
- Phase E complete (all exit strategies working, prediction monitoring operational)
- All pipeline phases (002-006) produce correct data

**Exit Criteria:**
- Phase registry with background thread runner operational
- POST /analyze returns HTTP 202, background thread runs full pipeline (Phases 1-7)
- Single-run enforcement (HTTP 409 if already running)
- Startup recovery sets stale 'running' records to 'failed'
- POST /positions/{id}/close manual exit working
- Prediction API endpoints working (GET /predictions, PATCH override)
- 60-min hard timeout, 30-min soft warning
- 10 API unit tests passing
- Author trust calculation (3-component weighted formula) implemented
- Author metrics update running after each pipeline cycle
- Prediction creation at Phase 3.5 (after AI, before signals)
- Prediction resolution with HITL override, EMA accuracy updates
- Evaluation period creation and completion (4 portfolios in lockstep, 30-day rolling)
- S&P 500 benchmark comparison via yfinance
- 7 prediction accuracy tests passing
- Integration test suite: 8 exit edge cases, 10 error injection, 6 portfolio isolation
- E2E test infrastructure (Playwright, mock + real modes)
- 4 baseline E2E scenario tests
- HITL override round-trip regression test
- Prediction tracking view with HITL override dropdown
- Performance sub-tab with evaluation periods
- Full pipeline runs end-to-end: POST /analyze through dashboard display

**Estimated Duration:** 3 weeks (~53 complexity points)

**Risk Notes:**
- **Background thread isolation (MEDIUM):** Separate SQLite connection required for WAL concurrent access.
- **Schwab rate limiting for predictions (MEDIUM):** ~50-100 unique tickers per cycle; ticker batching mitigates.
- **E2E test stability (LOW):** Playwright with mock API backend should be reliable.
- **Evaluation period lockstep (LOW):** 4 portfolios in single transaction.

---

### Phase G: Integration Testing + Polish (Weeks 15-16)

**Goal:** End-to-end validation, performance verification, and any remaining cleanup.

**Entry Criteria:**
- Phase F complete (full pipeline operational end-to-end)

**Exit Criteria:**
- Full pipeline run succeeds: POST /analyze through monitoring through dashboard
- 3 runs/day x 7 days simulated (NFR-005 validation)
- Failure scenarios tested: Reddit outage, OpenAI rate limit, Schwab auth expiration
- Data integrity verified: 30-day eval periods, author trust scores, position cash calculations
- Analysis completes within 30-minute target (NFR-004)
- All 225 active requirements verified implemented

**Estimated Duration:** 1 week (buffer/polish)

**Risk Notes:**
- This phase is buffer. If earlier phases run smoothly, it may shrink.
- If earlier phases run over, this absorbs the overrun.

---

## 2. Critical Path

The longest dependency chain from start to finish determines the minimum project duration regardless of parallelism.

### Critical Path Sequence

```
epic-001 (Foundation)
  task-001-001-01 (Core tables, c2)
  task-001-001-02 (Remaining tables, c2)
  task-001-002-01 (Config seed, c2)
  task-001-004-01 (Connection manager, c2)
    |
    v
epic-002 (Reddit Pipeline)
  task-002-001-01 (Async PRAW client, c2)
  task-002-001-02 (Hot posts fetch, c2)
  task-002-003-01 (Comment fetch, c2)
  task-002-007-01 (Priority scoring, c2)
  task-002-008-03 (Storage, c2)
    |
    v
epic-003 (AI Analysis)
  task-003-001-01 (OpenAI client, c2)
  task-003-004-01 (ThreadPoolExecutor batching, c5)
  task-003-005-01 (JSON parsing, c2)
  task-003-008-01 (Batch commits, c2)
  task-003-009-01 (comment_tickers, c2)
    |
    v
epic-004 (Signal Detection)
  task-004-001-01 (Comment aggregation, c2)
  task-004-002-01 (Quality signals, c2)
  task-004-003-01 (Consensus signals, c2)
  task-004-004-01 (Confidence calc, c2)
  task-004-006-01 (Signal UPSERT, c2)
    |
    v
epic-005 (Position Management)
  task-005-002-01 (Qualified signals, c2)
  task-005-003-01 (Position sizing, c3)
  task-005-006-01 (Options chain fetch, c2)
  task-005-006-02 (Strike selection, c3)
  task-005-007-02 (Position INSERT, c3)
    |
    v
epic-006 (Exit Strategies)
  task-006-001-02 (Tiered price fetch, c5)
  task-006-008-01 (Candle iteration engine, c5)
  task-006-002-01 (Stock stop-loss, c2)
  task-006-003-01 (Partial take-profit, c2)
  task-006-005-01 (Options expiration, c2)
  task-006-006-02 (Options premium exits, c3)
  task-006-019-02 (Prediction exit evaluation, c5)
    |
    v
epic-007 Phase 7b (Pipeline Integration)
  task-007-005-01 (Phase registry + bg thread, c2)
  task-007-006-01 (POST /analyze, c2)
    |
    v
Full End-to-End Pipeline Operational
```

### Critical Path Metrics

- **Total complexity on critical path:** ~73 points (subset of 316 total)
- **Critical path spans:** 7 epic transitions
- **Estimated critical path duration:** 12-14 weeks (the remaining tasks provide breadth, not length)

### Key Bottlenecks

| Bottleneck | Blocks | Impact |
|------------|--------|--------|
| task-001-001-01 + 01-001-02 (DB schema) | All downstream epics | Every epic reads/writes DB tables |
| task-001-004-01 (Connection manager) | All DB operations, API scaffold | Shared by all epics and Phase 7a |
| task-003-004-01 (ThreadPoolExecutor, c5) | All AI response processing | Single complex task on critical path |
| task-006-001-02 (Tiered price fetch, c5) | All exit condition evaluation | No exits can fire without price data |
| task-006-008-01 (Candle iteration, c5) | All exit conditions plug into this | Orchestration layer for exit cascade |
| task-006-019-02 (Prediction exits, c5) | Prediction monitoring tests | Most complex prediction-related task |

**Delays to any of these bottleneck tasks directly extend the overall project timeline.**

---

## 3. Parallel Work Opportunities

Even as a solo developer, understanding parallel tracks helps with:
- Context-switching when blocked on external dependencies (e.g., Schwab API approval)
- Identifying work that can proceed independently if a blocker arises
- Choosing which task to pick up next within a phase

### Track 1: Backend Pipeline (Critical Path)

```
epic-001 --> epic-002 --> epic-003 --> epic-004 --> epic-005 --> epic-006 --> epic-007b
```

This is the main pipeline chain. Each epic depends on the previous.

### Track 2: API Scaffold (Branches from epic-001)

```
epic-001 --> epic-007a (Weeks 2-3)
```

Phase 7a (FastAPI setup, GET endpoints, seed data) can start as soon as the database schema and connection manager are ready. It does NOT wait for epic-002 through epic-006.

### Track 3: Frontend (Branches from epic-007a)

```
epic-007a --> epic-008 (starting Week 3-4)
```

The Vue dashboard can start consuming GET endpoints with seed data immediately after Phase 7a. Frontend development proceeds in parallel with backend pipeline work.

### Track 4: Author Trust (Branches after epic-005/006)

```
epic-005 + epic-006 --> epic-009
```

Author trust and evaluation systems can start once strike selection (epic-005) and exit evaluation (epic-006) are available. Prediction creation reuses the strike selection function.

### Within-Phase Parallel Opportunities

| Phase | Independent Tasks (can interleave) |
|-------|-----------------------------------|
| Phase A | Schwab spike (001-006) runs independently of schema validation (001-005); API scaffold (007-001) can start once connection manager is ready |
| Phase B | epic-002 (Reddit) and OpenAI client setup (003-001) can proceed independently; data models (002-008-01) have no dependencies; Vue scaffold (008-001) is fully independent |
| Phase C | Market hours gate (005-001) has no dependencies; confidence calculation (004-004) is independent of emergence detection (004-005) |
| Phase D | Stock exit conditions (006-002 through 006-004) are independent of each other once candle engine (006-008) exists; dashboard components are independent of each other |
| Phase E | Options exit conditions (006-005 through 006-007) are independent of each other; prediction monitoring (006-019) is independent of exit tests (006-016/017) |
| Phase F | Author trust (009-001/002) is independent of pipeline integration (007-005); E2E tests (008-014) are independent of prediction tracking view (008-015) |

### Blocked-Work Fallback Strategy

If blocked on Schwab API (approval delay, outage):
- Proceed with all non-Schwab work (Reddit pipeline, AI analysis, signal detection)
- Use mock Schwab responses (VCR.py cassettes) for position management development
- yfinance provides stock price fallback for exit monitoring
- Options-related tasks can be stubbed and completed when Schwab access is restored

---

## 4. Risk Reduction Ordering

### Spikes Front-Loaded

| Spike | Phase | Timing | Impact if Fails |
|-------|-------|--------|-----------------|
| Schwab OAuth Spike (story-001-006) | Phase A | Week 1 | Blocks position management + exit monitoring. Fallback: yfinance-only, defer options |
| WAL Concurrency Spike (story-001-007) | Phase A | Week 1 | Blocks background thread pipeline. Low risk (WAL is proven) |
| Sparkline Library Spike (story-008-004) | Phase B | Week 3-4 | Blocks sparkline implementation only. Fallback: inline SVG |

All three spikes are scheduled in the first 3-4 weeks, before any dependent implementation work begins.

### Most Complex Epic in Middle, Not End

Epic-006 (76 story points, 31 tasks) is the most complex epic. It is scheduled in Phases D-E (Weeks 8-12), with a midpoint checkpoint after stock exits. This ensures:
- Foundation and pipeline are stable before attempting complex exit logic
- Problems surface with 4-6 weeks of buffer remaining
- Midpoint checkpoint enables course correction if velocity is lower than expected

### Frontend Scaffold Early for Visual Progress

Phase 7a (API scaffold) is in Week 2, and Vue dashboard development begins in Week 3-4. This provides:
- Visual progress and motivation (seeing data in a UI) while backend pipeline work continues
- Early validation of API contract design (frontend consumption reveals gaps)
- Parallel work capacity when blocked on backend tasks

### Midpoint Checkpoint for Epic-006

After stock exits (stories 001-004, 008-012) are complete, a velocity check is performed before proceeding to options exits. If stock exits took 3 weeks instead of the estimated 2.5, the options exit estimate should be inflated proportionally. This prevents the most complex epic from silently running over budget.

### Integration Points as Natural Checkpoints

| Checkpoint | When | What to Verify |
|------------|------|----------------|
| Phase A exit | Week 2 | Schema + API scaffold serving seed data |
| Phase B exit | Week 5 | ~500 AI-annotated comments per run |
| Phase C exit | Week 8 | Signals detected, positions opened in 4 portfolios |
| Phase D midpoint | Week 10 | Stock exits firing correctly (7 conditions) |
| Phase E exit | Week 12 | All exit conditions working, predictions monitored |
| Phase F exit | Week 15 | Full pipeline end-to-end operational |

---

## 5. Milestone Summary Table

| Phase | Weeks | Duration | Tasks | Complexity | Key Deliverable |
|-------|-------|----------|-------|------------|-----------------|
| A: Foundation | 1-2 | 2 wk | 22 | 41 | DB + API scaffold + Schwab spike |
| B: Data Pipeline + AI | 3-5 | 3 wk | 36 | 67 | ~500 AI-annotated comments/run + Vue scaffold |
| C: Signal + Position | 6-8 | 2.5 wk | 23 | 50 | Signals detected, positions opened |
| D: Stock Exits + Dashboard | 8-10 | 2.5 wk | 32 | 70 | 7 stock exit conditions + dashboard views |
| E: Options Exits + Predictions | 10-12 | 2.5 wk | 21 | 50 | 5 options exits + prediction monitoring |
| F: API Integration + Trust | 12-15 | 3 wk | 32 | 53 | Full pipeline + author trust + E2E tests |
| G: Polish + Buffer | 15-16 | 1 wk | -- | -- | Integration validation + buffer |
| **TOTAL** | **1-16** | **~16 wk** | **154** (note: some overlap in counting) | **316** | **Complete WSB analysis tool** |

*Note: Phases D and E have some dashboard tasks running in parallel with backend work. Task counts in this table approximate the primary focus of each phase.*

---

## 6. Task Execution Order

### Phase A: Foundation (Weeks 1-2)

#### Epic-001: Database Foundation + Schwab + Utils

**Story 001-001: Database Schema Creation**
1. task-001-001-01 -- Create core entity tables (system_config, authors, reddit_posts, signals, portfolios, positions) [c2]
2. task-001-001-02 -- Create tracking, junction, and prediction tables with FK relationships [c2]

**Story 001-002: Configuration Seed Data**
3. task-001-002-01 -- Create seed script with all 34 system_config entries using INSERT OR IGNORE [c2]

**Story 001-003: Portfolio Initialization**
4. task-001-003-01 -- Seed four portfolio records with $100k starting capital each [c1]

**Story 001-004: Connection Management**
5. task-001-004-01 -- Implement get_connection context manager with FK enforcement and WAL verification [c2]
6. task-001-004-02 -- Implement get_config helper and write unit tests for connection manager [c2]

**Story 001-005: Schema Validation Script**
7. task-001-005-01 -- Implement schema validation script checking tables, columns, config, and portfolios [c2]

**Story 001-008: Error Handling Shared Module** (can start in parallel with stories 001-001 through 001-005)
8. task-001-008-01 -- Implement retry_with_backoff utility with exponential backoff [c2]
9. task-001-008-02 -- Implement WarningsCollector class with thread-safe append and JSON serialization [c2]
10. task-001-008-03 -- Configure structlog for JSON logging to logs/backend.log [c1]

**Story 001-006: Schwab OAuth Spike** (time-boxed, 2-3 days)
11. task-001-006-01 -- Build Schwab OAuth CLI setup script with token storage [c2]
12. task-001-006-02 -- Implement Schwab token refresh logic with proactive and 401-retry strategies [c2]
13. task-001-006-03 -- Verify Schwab API with stock quote and options chain fetch, document findings [c2]

**Story 001-007: SQLite Concurrency Spike** (0.5 day)
14. task-001-007-01 -- Implement and run WAL mode concurrency validation test [c2]

#### Epic-007 Phase 7a: API Scaffold (overlapping Week 2)

**Story 007-001: FastAPI Application Setup**
15. task-007-001-01 -- Initialize FastAPI application with lifespan, CORS, and structlog [c2]

**Story 007-002: Standard Response Envelope**
16. task-007-002-01 -- Create Pydantic response/error models and wrap_response utility [c2]
17. task-007-002-02 -- Override FastAPI default exception handlers for envelope compliance [c1]

**Story 007-003: CRUD GET Endpoints**
18. task-007-003-01 -- Implement GET /signals, /signals/{id}, /signals/{id}/comments, and /signals/history endpoints [c2]
19. task-007-003-02 -- Implement GET /positions, /positions/{id} with convenience fields and exit history [c2]
20. task-007-003-03 -- Implement GET /portfolios, /portfolios/{id}, and /evaluation-periods endpoints [c2]
21. task-007-003-04 -- Implement GET /runs, /runs/{id}/status, /prices/{ticker}, and /status endpoints [c2]

**Story 007-004: Seed Test Data Script**
22. task-007-004-01 -- Create idempotent seed data script for frontend development [c2]

---

### Phase B: Data Pipeline + AI Analysis (Weeks 3-5)

#### Epic-002: Reddit Data Acquisition Pipeline

**Story 002-008: Data Models** (start first -- no dependencies, consumed by all other epic-002 tasks)
23. task-002-008-01 -- Define ProcessedPost, ProcessedComment, and ParentChainEntry data models [c1]

**Story 002-001: Async PRAW Authentication & Hot Posts Fetching**
24. task-002-001-01 -- Implement Async PRAW OAuth2 client initialization with environment variable validation [c2]
25. task-002-001-02 -- Implement hot posts fetching with ProcessedPost construction [c2]

**Story 002-002: Image Detection & Vision Analysis**
26. task-002-002-01 -- Implement image URL detection for three domain patterns [c1]
27. task-002-002-02 -- Implement GPT-4o-mini vision analysis with retry logic and graceful degradation [c2]

**Story 002-003: Comment Fetching & Parent Chain**
28. task-002-003-01 -- Implement comment fetching with engagement sorting and replace_more handling [c2]
29. task-002-003-02 -- Implement parent chain building for threaded comment context [c2]

**Story 002-004: Financial Keyword Scoring**
30. task-002-004-01 -- Implement financial keyword detection and density scoring [c2]

**Story 002-005: Author Trust Lookup**
31. task-002-005-01 -- Implement batch author trust score lookup with default fallback [c2]

**Story 002-006: Engagement & Depth Scoring**
32. task-002-006-01 -- Implement engagement score calculation, normalization, and depth penalty [c2]

**Story 002-007: Priority Scoring & Selection**
33. task-002-007-01 -- Implement composite priority scoring formula and top-50-per-post selection [c2]

**Story 002-008 (continued): Deduplication & Storage**
34. task-002-008-02 -- Implement comment deduplication check and analysis_run_id update [c2]
35. task-002-008-03 -- Implement atomic post and comment storage with transaction handling [c2]

**Story 002-009: Reddit Pipeline Tests**
36. task-002-009-01 -- Write Reddit pipeline unit tests covering all algorithmic components [c2]

#### Epic-003: AI Sentiment Analysis (overlaps with epic-002 second half)

**Story 003-001: OpenAI Client Setup** (can start in parallel with epic-002)
37. task-003-001-01 -- Implement OpenAI client wrapper with bearer token authentication [c2]
38. task-003-001-02 -- Implement monthly cost tracking with $60 warning threshold [c2]

**Story 003-002: AI Prompt Engineering**
39. task-003-002-01 -- Define system prompt and user prompt template with context formatting [c2]
40. task-003-002-02 -- Implement parent chain formatting for conversation context [c2]

**Story 003-003: Comment Deduplication Logic**
41. task-003-003-01 -- Implement batch deduplication query for comments by reddit_id [c2]
42. task-003-003-02 -- Implement dedup decision logic with analysis_run_id update [c2]

**Story 003-004: Concurrent AI Request Batching**
43. task-003-004-01 -- Implement ThreadPoolExecutor batch orchestrator for concurrent AI calls [c5]

**Story 003-005: AI Response Parsing**
44. task-003-005-01 -- Implement JSON extraction and field validation for AI responses [c2]
45. task-003-005-02 -- Implement ticker normalization and exclusion filtering [c2]

**Story 003-006: Malformed JSON Retry**
46. task-003-006-01 -- Implement malformed JSON retry with single retry attempt [c2]
47. task-003-006-02 -- Implement rate limit (429) exponential backoff retry [c2]

**Story 003-007: Author Trust Snapshot**
48. task-003-007-01 -- Persist author trust snapshot from Phase 2 to comments table [c1]

**Story 003-008: Batch-of-5 Commit Transaction**
49. task-003-008-01 -- Implement batch-of-5 transaction commit with rollback handling [c2]

**Story 003-009: Comment Tickers Junction Population**
50. task-003-009-01 -- Insert comment_tickers junction records within batch transaction [c2]

**Story 003-010: Concurrency Unit Tests**
51. task-003-010-01 -- Write 3 concurrency unit tests for batch-of-5 processing [c2]

**Story 003-011: AI Parsing and Deduplication Unit Tests**
52. task-003-011-01 -- Write 8 unit tests for AI response parsing and deduplication [c2]

#### Epic-008 (Early): Vue Scaffold + Sparkline Spike

**Story 008-001: Vue App Scaffold** (independent -- can start immediately)
53. task-008-001-01 -- Initialize Vue 3 project with Vite, Router, and Bootstrap integration [c2]
54. task-008-001-02 -- Create API client module and establish fetch/Axios pattern [c1]

**Story 008-002: Portfolio Tabs & Sub-Tabs**
55. task-008-002-01 -- Implement 4 portfolio tabs with 3 sub-tabs and default navigation [c2]
56. task-008-002-02 -- Scaffold shared composables with stub implementations [c2]

**Story 008-004: Sparkline Spike** (time-boxed, 1 day)
57. task-008-004-01 -- Evaluate sparkline rendering approaches and produce recommendation [c2]

---

### Phase C: Signal Detection + Position Management (Weeks 6-8)

#### Epic-004: Signal Detection & Confidence Calculation

**Story 004-001: Comment Aggregation by Ticker**
58. task-004-001-01 -- Implement comment aggregation query and return structure for signal detection [c2]

**Story 004-002: Quality Signal Detection**
59. task-004-002-01 -- Implement Quality signal detection algorithm with unanimity check [c2]

**Story 004-003: Consensus Signal Detection**
60. task-004-003-01 -- Implement Consensus signal detection algorithm with alignment calculation [c2]

**Story 004-004: Confidence Calculation**
61. task-004-004-01 -- Implement 4-factor weighted confidence calculation with signal-type branching [c2]

**Story 004-005: Emergence Detection**
62. task-004-005-01 -- Implement emergence detection with 7-day historical baseline and warmup logic [c2]

**Story 004-006: Daily Signal Rollup**
63. task-004-006-01 -- Implement daily signal UPSERT with signal_comments junction population [c2]
64. task-004-006-02 -- Implement Phase 4 pipeline orchestrator integrating all signal detection steps [c2]

**Story 004-007: Signal Detection Tests**
65. task-004-007-01 -- Write unit tests for Quality and Consensus signal detection algorithms [c2]
66. task-004-007-02 -- Write unit tests for confidence calculation, emergence detection, and daily rollup UPSERT [c2]

#### Epic-005: Position Management & Portfolio Limits

**Story 005-001: Market Hours Check**
67. task-005-001-01 -- Implement market hours gate function with ET timezone handling [c2]

**Story 005-002: Qualified Signal Filtering**
68. task-005-002-01 -- Implement qualified signal query with configurable confidence threshold [c2]

**Story 005-003: Confidence-Weighted Sizing**
69. task-005-003-01 -- Implement confidence-weighted position sizing with min/max clamping [c3]

**Story 005-004: Position Count & Replacement Logic**
70. task-005-004-01 -- Implement position count check and replacement candidate identification [c3]
71. task-005-004-02 -- Implement close-then-open replacement flow with atomic transaction [c3]

**Story 005-005: Stocks Long-Only Rule**
72. task-005-005-01 -- Implement stocks long-only filter with bearish signal handling [c2]

**Story 005-006: Options Strike Selection**
73. task-005-006-01 -- Implement options chain fetch and DTE filtering [c2]
74. task-005-006-02 -- Implement delta-based strike selection with tolerance filtering [c3]

**Story 005-007: Cash Guard & Position Opening**
75. task-005-007-01 -- Implement cash guard check with insufficient-funds handling [c1]
76. task-005-007-02 -- Implement position INSERT with Schwab quote fetch and share/contract calculation [c3]
77. task-005-007-03 -- Implement portfolio cash update, value recalculation, and position_opened flag [c2]

**Story 005-008: Stop-Loss/Take-Profit Calculation**
78. task-005-008-01 -- Implement stop-loss and take-profit calculation at position entry [c2]

**Story 005-009: Position Management Tests**
79. task-005-009-01 -- Write concurrent quote fetch and ThreadPoolExecutor integration tests [c2]
80. task-005-009-02 -- Write replacement flow and cash guard integration tests [c2]

---

### Phase D: Stock Exit Strategies + Dashboard Core (Weeks 8-10)

#### Epic-006 (First Half): Stock Exits + Infrastructure

**Story 006-015: MonitoredInstrument Protocol** (foundational -- implement first)
81. task-006-015-01 -- Define MonitoredInstrument Protocol with runtime_checkable [c3]

**Story 006-001: Tiered Price Data Fetching**
82. task-006-001-01 -- Implement last_check_time derivation from analysis_runs [c2]
83. task-006-001-02 -- Implement tiered price data fetching and candle merge [c5]

**Story 006-008: Candle Iteration Logic**
84. task-006-008-01 -- Implement candle iteration engine with priority-ordered exit evaluation [c5]

**Story 006-002: Stock Exit: Stop-Loss & Take-Profit**
85. task-006-002-01 -- Implement stock stop-loss exit condition function [c2]
86. task-006-002-02 -- Implement stock take-profit exit condition function [c2]

**Story 006-003: Stock Exit: Partial Take-Profit & Trailing Stop**
87. task-006-003-01 -- Implement stock partial take-profit exit logic [c2]
88. task-006-003-02 -- Implement stock trailing stop exit condition function [c2]

**Story 006-004: Stock Exit: Breakeven Promotion & Time Extension**
89. task-006-004-01 -- Implement breakeven stop promotion logic [c2]
90. task-006-004-02 -- Implement stock three-tier time extension logic [c3]

**Story 006-009: Partial Exit Mechanics**
91. task-006-009-01 -- Implement partial exit record creation and position update [c3]

**Story 006-010: Peak Tracking**
92. task-006-010-01 -- Implement peak price and peak premium tracking [c2]

**Story 006-011: Full Close Finalization**
93. task-006-011-01 -- Implement full close finalization logic [c2]

**Story 006-012: Price History UPSERT**
94. task-006-012-01 -- Implement price history UPSERT logic [c2]

#### Epic-008 (Dashboard Core): Signal + Position Views

**Story 008-003: Signal Cards Layout**
95. task-008-003-01 -- Build SignalCard component with two-row layout and confidence ordering [c2]
96. task-008-003-02 -- Implement 4 signal card states based on position status [c2]

**Story 008-005: Dual Sparklines**
97. task-008-005-01 -- Implement confidence sparkline with batch fetching and adaptive rendering [c2]
98. task-008-005-02 -- Implement price sparkline with lazy loading and concurrency throttle [c2]

**Story 008-006: Evidence Drill-Down Modal**
99. task-008-006-01 -- Build evidence drill-down modal with signal header and comment layout [c2]
100. task-008-006-02 -- Add comment pagination and reasoning summary expand/collapse [c2]

**Story 008-007: Position List & Monitoring Indicators**
101. task-008-007-01 -- Build position list with 3 primary states, exit badges, and market hours overlay [c2]
102. task-008-007-02 -- Implement manual close popover with reason, quantity, and confirmation flow [c2]

**Story 008-008: Options Position Display**
103. task-008-008-01 -- Extend position card with options-specific fields and DTE countdown [c2]

**MIDPOINT CHECKPOINT** -- Velocity check on stock exit conditions before proceeding to Phase E.

---

### Phase E: Options Exits + Prediction Monitoring (Weeks 10-12)

#### Epic-006 (Second Half): Options Exits + Predictions

**Story 006-005: Options Exit: Expiration Protection**
104. task-006-005-01 -- Implement options expiration protection exit condition [c2]

**Story 006-006: Options Exit: Premium Monitoring**
105. task-006-006-01 -- Implement options premium stop-loss exit condition [c2]
106. task-006-006-02 -- Implement options premium take-profit and trailing stop exits [c3]

**Story 006-007: Options Exit: Time Stop**
107. task-006-007-01 -- Implement options time stop exit condition [c1]

**Story 006-013: Schwab Retry & Fallback**
108. task-006-013-01 -- Implement Schwab exponential backoff retry wrapper [c2]
109. task-006-013-02 -- Implement fallback strategy and auth error handling [c3]

**Story 006-014: Token Health Check**
110. task-006-014-01 -- Implement GET /auth/status token health check endpoint [c2]

**Story 006-016: Stock Exit Unit Tests**
111. task-006-016-01 -- Write stock stop-loss, take-profit, and partial exit unit tests (Tests 1-4) [c3]
112. task-006-016-02 -- Write breakeven, time extension, and priority unit tests (Tests 5-9) [c3]

**Story 006-017: Options Exit Unit Tests**
113. task-006-017-01 -- Write options exit condition unit tests (Tests 1-6) [c3]
114. task-006-017-02 -- Write exit mechanics and x100 multiplier unit tests (Tests 7-10) [c2]

**Story 006-018: Concurrency Unit Tests**
115. task-006-018-01 -- Write concurrency unit tests for ThreadPoolExecutor Schwab fetching [c2]

**Story 006-019: Prediction Monitoring in Exit Loop**
116. task-006-019-01 -- Implement prediction loading and Schwab cache reuse in monitoring loop [c2]
117. task-006-019-02 -- Implement prediction exit evaluation and outcome recording [c5]

**Story 006-020: Prediction Monitoring Unit Tests**
118. task-006-020-01 -- Write prediction monitoring unit tests (7 tests) [c3]

**Story 006-021: Prediction Edge Case Tests**
119. task-006-021-01 -- Write prediction edge case tests (5 tests) [c2]

#### Epic-008 (Progress + Recovery): Remaining UI Components

**Story 008-009: 4-Stage Progress Indicator**
120. task-008-009-01 -- Build 4-stage progress indicator with polling and stage mapping [c2]
121. task-008-009-02 -- Implement results summary overlay and warnings display [c2]

**Story 008-010: Page Reload Recovery + Indicators**
122. task-008-010-01 -- Implement page reload recovery and header indicators [c2]
123. task-008-010-02 -- Implement backend error banner with retry and Refresh Prices button [c2]
124. task-008-010-03 -- Build reusable EmptyState component and configure all empty state messages [c1]

**Story 008-011: Token Expiration Banner**
125. task-008-011-01 -- Implement token expiration banner with polling and dismissal [c2]

---

### Phase F: API Integration + Dashboard Completion + Author Trust (Weeks 12-15)

#### Epic-007 Phase 7b: Pipeline Integration

**Story 007-005: Background Thread Orchestration**
126. task-007-005-01 -- Implement phase registry and background thread runner with isolated SQLite connection [c2]
127. task-007-005-02 -- Add 60-minute hard timeout and 30-minute soft warning to pipeline runner [c2]

**Story 007-006: POST /analyze Async Pattern**
128. task-007-006-01 -- Implement POST /analyze endpoint with HTTP 202, single-run enforcement, and warnings accumulation [c2]

**Story 007-007: Startup Recovery Logic**
129. task-007-007-01 -- Add startup recovery to set stale running analysis runs to failed [c1]

**Story 007-008: POST /positions/{id}/close Manual Exit**
130. task-007-008-01 -- Implement POST /positions/{id}/close with validation, partial/full close, and transactional updates [c2]

**Story 007-009: Prediction API Endpoints**
131. task-007-009-01 -- Implement GET /predictions, GET /predictions/{id}, and PATCH /predictions/{id}/override endpoints [c2]

**Story 007-010: API Endpoint Unit Tests**
132. task-007-010-01 -- Write Phase 7a API tests (envelope, pagination, GET errors) [c2]
133. task-007-010-02 -- Write Phase 7b API tests (analyze lifecycle, recovery, manual close) [c2]

#### Epic-009: Author Trust & Evaluation Systems

**Story 009-001: Author Trust Calculation**
134. task-009-001-01 -- Implement calculate_trust_score function with config-driven weights and unit tests [c2]

**Story 009-002: Author Metrics Update**
135. task-009-002-01 -- Implement author metrics upsert pipeline step (Phase 7a) [c2]
136. task-009-002-02 -- Implement conviction score calculation with running average update [c2]

**Story 009-003: Prediction Creation & Strike Selection**
137. task-009-003-01 -- Implement Phase 3.5 prediction creation pipeline step with sentiment-to-option mapping [c2]
138. task-009-003-02 -- Implement batched Schwab strike selection and premium fetch for predictions [c2]
139. task-009-003-03 -- Implement graceful degradation and warning handling for unavailable predictions [c1]

**Story 009-004: Prediction Resolution & Accuracy Update**
140. task-009-004-01 -- Implement prediction resolution logic with HITL override support [c2]
141. task-009-004-02 -- Implement EMA-based author accuracy update with cold start handling [c2]

**Story 009-005: Evaluation Period Creation**
142. task-009-005-01 -- Implement evaluation period creation for 4 portfolios in lockstep [c2]

**Story 009-006: Evaluation Period Completion**
143. task-009-006-01 -- Implement evaluation period completion with portfolio metrics and S&P 500 benchmark [c2]
144. task-009-006-02 -- Implement evaluation period rollover (create next active period after completion) [c1]

**Story 009-007: Prediction-Based Accuracy Tests**
145. task-009-007-01 -- Write 7 prediction-based accuracy tests covering EMA, HITL override, and cold start [c2]

#### Epic-008 (Completion): Testing + Final Views

**Story 008-012: Integration Tests**
146. task-008-012-01 -- Write 8 exit edge case integration tests [c2]
147. task-008-012-02 -- Write 6 portfolio isolation integration tests [c2]

**Story 008-013: Error Injection Tests**
148. task-008-013-01 -- Configure VCR.py and write 10 error injection tests across 4 tiers [c2]
149. task-008-013-02 -- Write HITL override round-trip regression test [c1]

**Story 008-014: E2E Test Suite**
150. task-008-014-01 -- Set up Playwright E2E infrastructure with mock and real modes [c2]
151. task-008-014-02 -- Write 4 baseline E2E scenario tests across all portfolio tabs [c2]

**Story 008-015: Prediction Tracking View**
152. task-008-015-01 -- Build prediction tracking table with author filtering [c2]
153. task-008-015-02 -- Add HITL override dropdown to prediction rows [c2]

**Story 008-016: Performance Sub-Tab**
154. task-008-016-01 -- Build performance sub-tab with evaluation period table and summary card [c2]

---

### Phase G: Integration Testing + Polish (Weeks 15-16)

No new tasks. This phase is dedicated to:
- Full pipeline end-to-end validation (POST /analyze through dashboard)
- Simulated 3 runs/day load testing
- Failure scenario testing (Reddit outage, OpenAI rate limit, Schwab auth expiry)
- Data integrity verification
- Performance validation (30-minute target)
- Any bug fixes discovered during integration testing

---

## Appendix: Complexity Totals by Epic

| Epic | Tasks | Complexity Points | Phase(s) |
|------|-------|-------------------|----------|
| epic-001 | 14 | 26 | A |
| epic-002 | 14 | 24 | B |
| epic-003 | 16 | 33 | B |
| epic-004 | 9 | 18 | C |
| epic-005 | 14 | 32 | C |
| epic-006 | 31 | 80 | D, E |
| epic-007 | 16 | 28 | A (7a), F (7b) |
| epic-008 | 30 | 55 | B, D, E, F |
| epic-009 | 12 | 20 | F |
| **TOTAL** | **154** (note: 2 tasks double-counted) | **316** | |

## Appendix: Epic-Level Dependency Graph

```
epic-001 (Foundation, 14 tasks)
    |
    +----> epic-007a (API Scaffold, 8 tasks) -------> epic-008 (Dashboard, 30 tasks)
    |                                                    ^
    +----> epic-002 (Reddit, 14 tasks)                   |
    |         |                                           |
    |         v                                           |
    |      epic-003 (AI Analysis, 16 tasks)               |
    |         |                                           |
    |         v                                           |
    |      epic-004 (Signal Detection, 9 tasks)           |
    |         |                                           |
    |         v                                           |
    |      epic-005 (Position Mgmt, 14 tasks)             |
    |         |                                           |
    |         v                                           |
    |      epic-006 (Exit Strategies, 31 tasks)           |
    |         |                                           |
    |         v                                           |
    |      epic-007b (Pipeline Integration, 8 tasks) -----+
    |         |
    |         v
    +----> epic-009 (Author Trust, 12 tasks)
              ^
              |
              +-- depends on: epic-003 (AI annotations)
              +-- depends on: epic-005 (strike selection)
              +-- depends on: epic-006 (exit evaluation)
```

**Critical Path:** epic-001 -> epic-002 -> epic-003 -> epic-004 -> epic-005 -> epic-006 -> epic-007b

**Parallel Paths:**
- epic-007a branches from epic-001 (Week 2)
- epic-008 starts after epic-007a (Week 3-4), completes after epic-007b
- epic-009 starts after epic-005 + epic-006 complete

---

*Document generated by Delivery Manager (Galileo) agent, Phase 6 work sequencing.*
