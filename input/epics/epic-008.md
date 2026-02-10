---
id: epic-008
title: Vue.js Dashboard & User Interface
requirements: [FR-004, FR-005, FR-006, FR-007, FR-008, FR-012, FR-018, FR-050, UI-TABS, UI-SUBTABS, UI-SIGNAL-CARD, UI-SIGNAL-STATES, UI-POSITION-STATES, UI-EXIT-LABELS, UI-EVIDENCE, UI-SPARKLINES, UI-PROGRESS, UI-RESULTS-SUMMARY, UI-WARNINGS, UI-RELOAD-RECOVERY, UI-MANUAL-CLOSE, UI-OPTIONS-DISPLAY, UI-MARKET-HOURS, UI-PERFORMANCE, UI-EMPTY-STATES, UI-EMERGENCE, UI-LAST-ANALYSIS, UI-BACKEND-ERROR, UI-TECH-STACK, UI-NO-STATE, UI-REFRESH, NFR-006, NFR-007, NFR-010, UI-PREDICTIONS]
priority: high
estimated_stories: 16
estimated_story_points: 50
---

# Epic: Vue.js Dashboard & User Interface

## Description
Implement Vue.js 3 web dashboard with 4 portfolio tabs (stocks/options × quality/consensus) × 3 sub-tabs (Signals, Positions, Performance) = 12 views. Includes dual sparklines (signal confidence + stock price), 4-stage progress indicator with results summary, page reload recovery, annotated evidence drill-down, manual position close, options position display with DTE countdown, empty states, token expiration banner, and integration/E2E test suite. Can start at Week 3-4 using seed data from epic-007 Phase 7a.

## Requirements Traced

### Core Dashboard Requirements
- **FR-004**: Trend ranking display (signals ordered by composite confidence)
- **FR-005**: Signal strength indicator (confidence metric per signal)
- **FR-006**: Time context (when signal emerged, acceleration/deceleration)
- **FR-007**: Evidence drill-down (source comments with AI annotations, original text always visible)
- **FR-008**: Dual sparkline visualization (signal confidence history + stock price, 7-14 days, adaptive rendering)
- **FR-012**: Web dashboard interface (Vue-based, data loading on page open, manual refresh, interactive exploration, default: Stock/Quality, no auto-polling)
- **FR-018**: Benchmark comparison (signal performance vs S&P 500 over rolling 30-day periods)
- **FR-050**: Default portfolio view (Stock/Quality on load, no state persistence)

### Tab & Navigation Structure
- **UI-TABS**: 4 horizontal tabs (Stock/Quality default, Stock/Consensus, Options/Quality, Options/Consensus)
- **UI-SUBTABS**: 3 sub-tabs per portfolio (Signals default, Positions, Performance)

### Signal Cards & States
- **UI-SIGNAL-CARD**: Row 1: ticker, direction arrow, confidence badge, comment count, signal type pill (blue=Quality, purple=Consensus); Row 2: dual sparklines, age label, emergence flag
- **UI-SIGNAL-STATES**: 4 states (Position Open: green + unrealized %, Position Closed: gray + realized %, Below threshold: gray text, Not eligible: gray + tooltip)

### Position Monitoring
- **UI-POSITION-STATES**: 3 primary states (Active/Monitoring, Near Exit: amber ≤2%, Partially Closed); overlay: Market Closed (greyed, "as of [timestamp]")
- **UI-EXIT-LABELS**: Map 8 exit_reason values to human-readable labels, display as badge on closed positions
- **UI-OPTIONS-DISPLAY**: DTE countdown, contracts/contracts_remaining, premium_change_pct, strike + option_type (Call/Put)

### Evidence & Annotations
- **UI-EVIDENCE**: Two-column/expandable layout (original comment + AI annotations: sentiment badge, sarcasm flag, reasoning indicator, confidence), "Show Reasoning Summary" expands

### Sparklines
- **UI-SPARKLINES**: ~100px × 30px each, confidence from /signals/history, price from /prices/{ticker}, adaptive rendering (≤2 points: dots, 3+: line), batch signals/history, lazy prices (max 5 concurrent), placeholder while loading

### Progress & Results
- **UI-PROGRESS**: 4-stage indicator (Fetching Reddit, Analyzing comments N/total, Detecting signals, Monitoring prices), current stage active, next dimmed, results summary on completion
- **UI-RESULTS-SUMMARY**: Overlay with signals_created, positions_opened, exits_triggered, errors, warnings
- **UI-WARNINGS**: 0 warnings: omit, 1-3: inline bulleted list, 4+: first 3 + "and N more..." expandable, type prefix label

### Page Reload & Recovery
- **UI-RELOAD-RECOVERY**: GET /status on load checks active_run_id, resume polling if present, show progress at current phase

### Manual Actions
- **UI-MANUAL-CLOSE**: "Close" button on open positions, inline popover (reason required, quantity radio: full/partial 50%, confirm button, spinner, toast)
- **UI-REFRESH**: "Refresh Prices" button (fetches live prices for open positions, recomputes current_value on demand)

### Indicators & Empty States
- **UI-MARKET-HOURS**: Header-level indicator (when closed: "Market closed -- prices as of [last close time]", client-side ET calculation)
- **UI-PERFORMANCE**: Performance sub-tab (period dates, portfolio return %, S&P 500 return %, relative performance, win/loss, avg return, signal accuracy, scoped to current portfolio)
- **UI-EMPTY-STATES**: Performance (no periods, active-only Day N of 30, zero positions), Signals (no runs yet, no signals for type), Positions (no open positions)
- **UI-EMERGENCE**: Emergence countdown widget (Days 1-7: yellow "Activates in N days", Day 8+: green "Active")
- **UI-LAST-ANALYSIS**: "Last analysis: [relative time]" in header from GET /status

### Error Handling
- **UI-BACKEND-ERROR**: Page load failure: persistent banner "Unable to connect..." + Retry; individual request failure: inline error + retry

### Tech Stack & State Management
- **UI-TECH-STACK**: Vue.js 3 Composition API, Axios or fetch, Chart.js or vue-sparklines, Bootstrap (via bootstrap-vue-next), local dev server
- **UI-NO-STATE**: No localStorage, no Vuex/Pinia, no persistent state, always resets to Stock/Quality on reload

### Non-Functional UI Requirements
- **NFR-006**: Desktop compatibility (optimized for desktop browser, no mobile)
- **NFR-007**: Simple, intuitive UI (usable without training, clear visual hierarchy)
- **NFR-010**: Single-user design (no authentication or multi-user support)

## Technology Decisions

Resolved during Phase 1 planning questions:

- **CSS Framework:** Bootstrap via bootstrap-vue-next for rapid prototyping with pre-built components [qc-ux-003, qc-sd-004]
- **State Management:** Shared Vue composables (useSignals, usePositions, usePortfolios, useAnalysis) for cross-view data sharing — no Vuex/Pinia [qc-ux-002]
- **Sparkline Library:** TBD — 2-point spike to evaluate options before committing [qc-ux-001]
- **Test Strategy:** Weekly smoke tests with real APIs + per-commit regression with mocked APIs [qc-qa-007]

## Technical Scope

### Database Tables Affected
None directly (dashboard consumes REST API only)

### API Endpoints Consumed
All 20+ endpoints from Epic 007 (signals, positions, portfolios, evaluation periods, prices, analysis status)

### External Integrations Involved
None directly (all via backend API)

### Key Algorithms/Logic
- **Sparkline data fetching strategy**: Batch GET /signals/history for all tickers on tab load, lazy GET /prices/{ticker} per signal card (max 5 concurrent), cache on tab switch
- **Adaptive sparkline rendering**: ≤2 points → scatter dots, 3+ points → line chart with interpolation
- **Age label calculation**: Compute from UTC signal_date, display in relative terms ("2 hours ago", "3 days ago"), ≤1 day ET boundary discrepancy acceptable
- **Warnings rendering rules**: 0 → omit section, 1-3 → inline bulleted list, 4+ → first 3 + expandable "and N more..."
- **Polling interval**: 10 seconds for GET /runs/{id}/status during active run
- **Page reload recovery**: GET /status on mount, if active_run_id present, resume polling at current phase
- **Exit reason label mapping**: 8 exit_reason DB values → human-readable labels (e.g., 'stop_loss' → 'Stop Loss', 'breakeven_stop' → 'Breakeven Stop')

## Dependencies
- Depends on: epic-007 Phase 7a (GET endpoints + seed data available at Week 3-4)
- Blocks: None (this is final user-facing layer)

**Note:** Can start significantly earlier than original plan. Phase 7a provides GET scaffolding with seed test data, enabling frontend development in parallel with backend pipeline epics (002-006). Full integration testing deferred until Phase 7b completes.

## Risk Assessment

**Complexity:** Medium

**Key Risks:**
1. **Sparkline data fetching performance**: Lazy loading prices for 10+ signals may cause flicker
   - *Mitigation*: Max 5 concurrent, placeholder while loading, cache on tab switch
2. **Polling interval battery drain**: 10-second polling for 30 minutes = 180 requests
   - *Acceptable*: Desktop browser only, no mobile, user initiates analysis
3. **Page reload recovery edge cases**: What if user reloads during Phase 7? (Answer: resume polling, show current phase)
   - *Mitigation*: GET /status returns current_phase + progress, UI displays accurately
4. **Empty state proliferation**: 3 sub-tabs × 4 portfolios × 3 empty state types = 36 potential empty states
   - *Mitigation*: Reusable empty state component with slot for message
5. **Manual close UX**: Inline popover may be clunky on narrow screens
   - *Acceptable*: Desktop-optimized, no mobile support required
6. **Evidence drill-down modal complexity**: Showing 50+ comments with annotations may be slow
   - *Mitigation*: Paginate comments (GET /signals/{id}/comments supports pagination)

**Overall Risk Level:** Low-Medium (frontend complexity is manageable, no novel patterns)

## Estimated Stories

1. **Vue App Scaffold & Routing**: Vue 3 setup, router for 4 tabs, Bootstrap via bootstrap-vue-next integration [qc-ux-003, qc-sd-004]
2. **Portfolio Tabs & Sub-Tabs**: 4 horizontal tabs, 3 sub-tabs per portfolio, default to Stock/Quality + Signals. Includes shared composables scaffolding (useSignals, usePositions, usePortfolios, useAnalysis). (~5 pts) [qc-ux-002]
3. **Signal Cards Layout**: Ticker, direction arrow, confidence badge, comment count, signal type pill, age label, emergence flag
4. **Sparkline Spike**: 2-point spike to evaluate Chart.js, vue-sparklines, inline SVG, and/or other options. Produce recommendation before main sparkline story. (~2 pts) [qc-ux-001]
5. **Dual Sparklines**: Batch /signals/history, lazy /prices, adaptive rendering (dots vs line), placeholder while loading
6. **Evidence Drill-Down Modal**: Two-column layout (original comment + annotations), "Show Reasoning Summary" expand/collapse
7. **Position List & Monitoring Indicators**: 3 primary states (Active, Near Exit, Partially Closed), Market Closed overlay
8. **Options Position Display**: DTE countdown, contracts, premium_change_pct, strike + option_type
9. **4-Stage Progress Indicator**: Fetching/Analyzing/Detecting/Monitoring stages, results summary overlay, warnings rendering
10. **Page Reload Recovery**: GET /status on mount, resume polling if active_run_id present
11. **Dashboard Token Expiration Banner**: Polls GET /auth/status from epic-006 Story 14, persistent warning banner when Schwab token expires within 24h. (~2 pts) [qc-sec-003]
12. **Integration & E2E Test Suite**: VCR.py setup for API mocking, 8 exit edge case tests (test #8 replaced: prediction-based accuracy flow instead of old PIPE-053 position-close flow) [qc-qa-002], 10 error injection tests (4-tier model) [qc-qa-005], 6 portfolio isolation tests [qc-qa-006], E2E regression suite (per-commit mocked, weekly smoke with real APIs) [qc-qa-007], regression test #11: HITL override round-trip (PATCH → GET reflects change). (~8 pts)
13. **Prediction Tracking View & HITL Override**: Table of predictions per author (accessible from evidence modal). Shows: ticker, option_type, strike, entry_premium, current_premium, status, exit_reason, is_correct, HITL override dropdown. (~3 pts) [UI-PREDICTIONS]
14. **Performance Sub-Tab Content View**: Display evaluation periods for active portfolio with portfolio return %, S&P 500 return %, relative performance, win/loss counts, avg return, signal accuracy. (~3 pts) [UI-PERFORMANCE, FR-018]
