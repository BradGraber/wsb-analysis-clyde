---
id: epic-006
title: Price Monitoring & Exit Strategies
requirements: [FR-014, FR-026, FR-027, FR-028, FR-029, FR-030, FR-031, FR-041, FR-042, FR-043, FR-044, FR-045, FR-048, FR-049, PIPE-042, PIPE-043, PIPE-044, PIPE-045, PIPE-046, PIPE-047, PIPE-048, PIPE-049, PIPE-050, PIPE-051, INT-YFINANCE, ERR-YFINANCE, ERR-SCHWAB-STOCK, ERR-SCHWAB-OPTIONS, ERR-SCHWAB-AUTH, PIPE-058, DB-PREDICTION-EXITS]
priority: high
estimated_stories: 21
estimated_story_points: 76
---

# Epic: Price Monitoring & Exit Strategies

## Description
Implement dual exit strategies (stocks: 7 conditions, options: 5 conditions) with intraday price monitoring via Schwab API (5-min candles) and yfinance fallback for stocks. Includes tiered gap handling for multi-day intervals, candle iteration for correct exit ordering, partial exit mechanics, and peak tracking for trailing stops. Schwab OAuth lifecycle (setup, token refresh) is handled by epic-001; this epic consumes the Schwab client.

## Requirements Traced

### Stock Exit Strategy (7 conditions)
- **FR-026**: Bracket exit strategy (stop-loss -10%, take-profit +15%, time-based exit)
- **FR-027**: Partial take-profit (at +15%, exit 50%, apply trailing stop to remainder)
- **FR-028**: Trailing stop (after partial take-profit, -7% from peak price)
- **FR-029**: Gain-based time extension (base 5 days if <+5%, extended 7 days if +5-15%, trailing 10 days)
- **FR-030**: Breakeven stop promotion (at +5% gain and Day 5, raise stop-loss to entry_price)

### Options Exit Strategy (5 conditions)
- **FR-041**: Premium-based stop-loss (exit 100% if premium drops to -50% from entry)
- **FR-042**: Premium-based take-profit (at +100% premium, exit 50% contracts, apply trailing stop)
- **FR-043**: Trailing stop (after partial take-profit, -30% from peak premium)
- **FR-044**: Expiration protection (exit 100% when DTE ≤2, highest priority)
- **FR-045**: Time stop (exit 100% after 10 days hold)
- **FR-048**: Options position monitoring (check all open, priority: expiration > stop-loss > take-profit > trailing > time)

### Price Monitoring Infrastructure
- **FR-014**: Automated price validation (yfinance for price movements)
- **FR-031**: Intraday price monitoring (Schwab real-time + 5-min candles, multi-day gaps: yfinance daily OHLC, chronological candle iteration)
- **FR-049**: Price monitoring schedule (executes at end of /analyze, any time, calendar days for hold_days, UTC storage + ET display)

### Pipeline Implementation (Phase 6)
- **PIPE-042**: Derive last_check_time (first run: started_at, subsequent: prior completed run's started_at)
- **PIPE-043**: Tiered price data strategy (same-day: Schwab 5-min, multi-day gap: yfinance daily OHLC for gap + Schwab for today)
- **PIPE-044**: Stock exit priority order (stop-loss > take-profit > trailing > breakeven > time)
- **PIPE-045**: Options exit priority order (expiration > stop-loss > take-profit > trailing > time)
- **PIPE-046**: Period high/low derivation (aggregate intraday candles, iterate chronologically on breach)
- **PIPE-047**: Exit record creation (INSERT position_exits, UPDATE positions shares/contracts_remaining, UPDATE portfolio cash with proceeds-only)
- **PIPE-048**: Breakeven stop detection (when stop_loss_price == entry_price: exit_reason='breakeven_stop')
- **PIPE-049**: Full close finalization (set status='closed', exit_date, hold_days, realized_return_pct = SUM(exits.realized_pnl)/position_size)
- **PIPE-050**: Price history UPSERT (INSERT OR REPLACE price_history on UNIQUE(ticker, date))
- **PIPE-051**: Schwab retry with backoff (1s, 2s, 4s max 15s, up to 3 attempts, log and skip on failure)

### External Integrations
- **INT-YFINANCE**: No auth, historical prices, S&P 500 benchmark, sparkline data, daily OHLC fallback

### Error Handling
- **ERR-YFINANCE**: Data unavailable → log warning, skip monitoring, retry next run (Tier 4)
- **ERR-SCHWAB-STOCK**: Quote failure → retry 3x (1s, 2s, 4s max 15s), skip ticker on failure (Tier 2)
- **ERR-SCHWAB-OPTIONS**: Premium failure → same retry as stocks, skip options monitoring (Tier 2)
- **ERR-SCHWAB-AUTH**: Token expired → proactive refresh, refresh token expired → log error + re-auth instructions, fallback to yfinance for stocks, skip options

## Technology Decisions

Resolved during Phase 1 planning questions:

- **Exit Architecture:** Hybrid — private functions per exit condition, called in priority cascade order. Enables isolated unit testing of each condition. [qc-arch-003]
- **API Mocking:** VCR.py for recording/replaying Schwab API responses in tests [qc-qa-003]

## Technical Scope

### Database Tables Affected
- positions (SELECT open positions, UPDATE shares/contracts_remaining, status, exit_date, hold_days, realized_return_pct, peak_price, peak_premium)
- position_exits (INSERT exit records)
- portfolios (UPDATE cash_available with proceeds)
- price_history (INSERT OR REPLACE daily OHLC)
- analysis_runs (READ for last_check_time derivation)

### API Endpoints Included
None directly (this is backend pipeline logic)

### External Integrations Involved
- **Schwab API**: Real-time quotes, 5-min candles, options chains with greeks (client from epic-001)
- **yfinance**: Historical daily OHLC, S&P 500 benchmark, fallback for stocks

### Key Algorithms/Logic
- **Stock exit priority cascade**: Check stop-loss first, then take-profit, then trailing, then breakeven, then time (3 tiers)
- **Options exit priority cascade**: Check expiration first (DTE ≤2), then stop-loss, then take-profit, then trailing, then time
- **Candle iteration**: Fetch all candles since last_check_time, sort chronologically, check each candle's high/low against all active triggers, process first breach
- **Partial exit mechanics**: Update shares/contracts_remaining, INSERT position_exits with quantity_pct, update cash with proceeds
- **Peak tracking**: Update peak_price (stocks) or peak_premium (options) after every check
- **Time extension logic**: Base 5 days, extended 7 days (if +5-15% at Day 5), trailing 10 days (after partial exit)
- **Breakeven promotion**: At +5% gain AND Day 5, set stop_loss_price = entry_price (exit_reason='breakeven_stop' if fires)
- **Simulated fills**: exit_price = trigger level for bracket orders, exit_price = current_price for time exits
- **Tiered gap handling**: Multi-day gap → yfinance daily OHLC for missed days, Schwab 5-min for today, chronological merge

## Dependencies
- Depends on: epic-001 (database + Schwab client), epic-005 (open positions to monitor)
- Blocks: epic-007 Phase 7b (dashboard needs exit data), epic-009 (author trust accuracy updates need closed positions)

**Note:** No more circular dependency with epic-005. Schwab OAuth moved to epic-001 (foundational), so epic-005 and epic-006 both consume the Schwab client from epic-001 independently.

## Risk Assessment

**Complexity:** Very High

**Key Risks:**
1. **Exit strategy complexity**: 7 stock conditions + 5 options conditions with priority ordering and partial exits
   - *Mitigation*: Well-defined pseudocode in PRD Section 3.2.2 Phase 6, unit test each condition independently
2. **Candle iteration edge cases**: Multiple triggers in same candle (e.g., price rises to take-profit, then falls to stop-loss)
   - *Mitigation*: Process first breach chronologically, ignore subsequent triggers in same candle
3. **Multi-day gap handling**: If last run was 3 days ago, need yfinance daily OHLC for gap days + Schwab for today
   - *Mitigation*: Tiered strategy in PIPE-043, chronological merge of candles
4. **Peak tracking state**: Must persist peak_price/peak_premium in positions table, update after every check
   - *Mitigation*: Explicit UPDATE in PIPE-047, test with mock price movements
5. **Partial exit cash calculation**: proceeds-only formula (not including realized_pnl), options include ×100 multiplier
   - *Mitigation*: Test with multiple partial exits, verify cash balances
6. **Expiration protection timing**: DTE countdown may cross threshold between runs (DTE=3 yesterday, DTE=1 today)
   - *Acceptable*: Run at least once per day, worst case exits at DTE=1 (still safe from assignment)

**Overall Risk Level:** Very High (most complex Epic, highest risk of bugs)

**Midpoint Checkpoint:** After stock exit stories (Stories 1-6) are complete, conduct a velocity check before proceeding to options exits. This provides an early signal if the epic is running over budget. [qc-dm-002]

## Implementation Notes

- **Shared Exit Evaluation:** Exit evaluation must use a shared MonitoredInstrument interface/protocol that both positions and predictions satisfy. This enables Phase 6 to process predictions alongside real positions using the same exit condition cascade.

## Estimated Stories

1. **Tiered Price Data Fetching**: Same-day Schwab 5-min candles, multi-day yfinance daily OHLC + Schwab, chronological merge
2. **Stock Exit: Stop-Loss & Take-Profit**: Check stop_loss_price and take_profit_price against candle data
3. **Stock Exit: Partial Take-Profit & Trailing Stop**: 50% exit at +15%, trailing stop at peak × 0.93
4. **Stock Exit: Breakeven Promotion & Time Extension**: Raise stop at +5% Day 5, base/extended/trailing time tiers
5. **Options Exit: Expiration Protection**: DTE countdown, exit 100% at DTE ≤2 (highest priority)
6. **Options Exit: Premium Monitoring**: Stop-loss -50%, take-profit +100%, trailing -30% from peak
7. **Options Exit: Time Stop**: Exit 100% after 10 days hold
8. **Candle Iteration Logic**: Fetch candles since last_check_time, sort chronologically, check triggers, process first breach
9. **Partial Exit Mechanics**: Calculate quantity_pct, INSERT position_exits, UPDATE shares/contracts_remaining, UPDATE portfolio cash
10. **Peak Tracking**: Update peak_price (stocks) and peak_premium (options) after every check
11. **Full Close Finalization**: Set status='closed', exit_date, hold_days, calculate realized_return_pct from SUM(exits.realized_pnl)
12. **Price History UPSERT**: INSERT OR REPLACE price_history on UNIQUE(ticker, date)
13. **Schwab Retry & Fallback**: Exponential backoff (1s, 2s, 4s), yfinance fallback for stocks, skip options on Schwab failure
14. **Token Health Check Endpoint**: GET /auth/status returning token expiration status, warning if <24h to expiry. (~2 pts) [qc-sec-003]
15. **Exit Strategy Unit Tests**: 19 tests: 7 stock exit conditions + 5 options exit conditions + 3 partial exit mechanics + 2 peak tracking + 2 time extension logic. (~8 pts) [qc-qa-002, qc-qa-001]
16. **Concurrency Unit Tests**: 2 tests for concurrent Schwab quote fetches across 40 open positions. (~1 pt) [qc-qa-004]
17. **Prediction Monitoring in Exit Loop**: Phase 6 monitoring loop processes 'tracking' predictions alongside real positions. Real positions have priority. Fetches current premiums from Schwab (batched by ticker, reuse cached data). Runs shared exit evaluation function with full partial exit support. Handles expired-past-expiration (DTE < 0). Inserts prediction_outcomes and prediction_exits. Calculates blended simulated_return_pct. Does NOT update portfolio cash. Testing note: use fixture/mock prediction data for unit testing. (~5 pts) [PIPE-058]
18. **Prediction Monitoring Unit Tests**: 7 tests: prediction expiration protection, stop-loss, take-profit partial exit, trailing stop after partial, time stop, peak tracking on predictions, no-cash-impact verification. Key test: full partial exit flow verifying blended simulated_return_pct = SUM(prediction_exits.simulated_pnl) / (entry_premium × contracts × 100). (~5 pts)
19. **Prediction Edge Case Tests**: 5 tests: missed expiration (DTE < 0 between runs), Schwab outage during monitoring (stale current_premium), zero-premium options, stale peak_premium handling, skip already-resolved predictions. (~3 pts)
