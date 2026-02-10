---
id: epic-009
title: Author Trust & Evaluation Systems
requirements: [FR-047, PIPE-052, PIPE-057, PIPE-059, PIPE-054, TRUST-SCORE, TRUST-QUALITY, TRUST-ACCURACY, TRUST-TENURE, TRUST-CONVICTION, TRUST-SENTIMENT-ACCURACY, TRUST-COLD-START, TRUST-FLAGGED, NFR-001, NFR-002, NFR-003]
priority: medium
estimated_stories: 7
estimated_story_points: 23
---

# Epic: Author Trust & Evaluation Systems

## Description
Implement author trust scoring system (quality ratio × 0.40 + accuracy × 0.50 + tenure × 0.10) with prediction-based accuracy — creates simulated options predictions (call/put) from ALL comment_tickers, evaluated by Phase 6 using same exit logic as real positions via MonitoredInstrument interface, with Schwab options premium data and per-prediction HITL overrides. Maintain 30-day rolling evaluation periods for all 4 portfolios in lockstep, calculating portfolio return vs S&P 500 benchmark. Includes cold start period handling (new authors default to 0.5 accuracy), EMA-based accuracy updates, and conviction score tracking.

## Requirements Traced

### Author Trust System (Appendix F)
- **FR-047**: Author trust database (authors table: first_seen, total_comments, high_quality_comments, total_upvotes, avg_conviction_score, avg_sentiment_accuracy, last_active)
- **TRUST-SCORE**: Trust score formula (quality*0.40 + accuracy*0.50 + tenure*0.10, weights from system_config)
- **TRUST-QUALITY**: Quality ratio (high_quality_comments / max(total_comments, 1))
- **TRUST-ACCURACY**: Accuracy component (avg_sentiment_accuracy if not NULL, else 0.5 default)
- **TRUST-TENURE**: Tenure factor (min(1.0, days_active / 30.0), saturates at 30 days)
- **TRUST-CONVICTION**: Conviction score per-comment ((length*0.20) + (reasoning*0.20) + (ai_confidence*0.60), running average)
- **TRUST-SENTIMENT-ACCURACY**: Sentiment accuracy calculation (uses simulated options prediction outcomes (call/put), evaluated by same exit logic as real positions, with HITL override support, EMA: 70% old + 30% new)
- **TRUST-COLD-START**: Cold start period (new authors: avg_sentiment_accuracy=NULL, trust uses 0.5 default, predictions resolve within option lifecycle (~17-30 DTE), accuracy data available within 2-4 weeks)
- **TRUST-FLAGGED**: Flagged comments column (populated but not used in Phase 1, Phase 2 may add penalties)

### Pipeline Implementation (Phase 3.5, 7)
- **PIPE-052**: Author trust update (per unique author: increment total_comments, high_quality_comments, total_upvotes, recalculate avg_conviction_score, update last_active)
- **PIPE-057**: Prediction creation — after Phase 3, for each comment_ticker: determine option_type (bullish→call, bearish→put), select strike via Schwab options chain (reuse epic-005 logic), fetch entry premium, create prediction record. Status = 'tracking'. If Schwab unavailable, status = 'expired' + append warning
- **PIPE-059**: Prediction resolution & accuracy update — when exit condition triggers: calculate blended simulated_return_pct from prediction_exits, set is_correct = (return > 0). Apply HITL override if present. Update author.avg_sentiment_accuracy via EMA (70% old + 30% new). Excluded predictions don't affect accuracy
- **PIPE-054**: Evaluation period management (4 rows in lockstep per portfolio, create active periods, complete expired periods, calculate metrics: portfolio_return_pct, sp500_return_pct, relative_performance, win_rate, avg_return, signal_accuracy)

### Performance Evaluation
- **NFR-001**: Benchmark-relative performance (measure as portfolio vs S&P 500, target: beat by 10% per 30-day period)
- **NFR-002**: 3-10 day prediction window (evaluate predictions over 3-10 trading days)
- **NFR-003**: 30-day evaluation periods (rolling 30-day windows for assessment)

## Technical Scope

### Database Tables Affected
- authors (UPDATE trust metrics after each run, accuracy updates from resolved predictions)
- predictions (INSERT during Phase 3.5, READ during Phase 7a accuracy updates)
- prediction_exits (READ for blended simulated_return_pct)
- evaluation_periods (INSERT new periods, UPDATE completed periods with metrics)
- comment_tickers (READ to create predictions)
- comments (JOIN for author attribution)

### API Endpoints Included
None directly (this is backend pipeline logic in Phase 7)

### External Integrations Involved
- **yfinance**: S&P 500 (^GSPC) historical prices for benchmark comparison

### Key Algorithms/Logic
- **Trust score calculation**: 3-component weighted formula with configurable weights from system_config
- **Quality ratio**: high_quality_comments (has_reasoning=true) / total_comments
- **Accuracy component**: avg_sentiment_accuracy (NULL for new authors → default 0.5)
- **Tenure factor**: days since first_seen, saturates at 30 days
- **Conviction score**: Per-comment calculation with running average update
- **Sentiment accuracy EMA**: 70% old + 30% new on each update
- **Accuracy matching**: Bullish prediction + positive realized_return = correct, bearish + negative = correct, neutral (within ±1% threshold) excluded
- **Evaluation period lifecycle**: Create at system start, complete after 30 days, calculate metrics (portfolio return vs S&P 500), create next period
- **Benchmark comparison**: Fetch S&P 500 close prices for period start and end dates, calculate return percentage

## Dependencies
- Depends on: epic-001 (database: authors, predictions, evaluation_periods), epic-003 (AI annotations for quality), epic-005 (strike selection function), epic-006 (exit evaluation via MonitoredInstrument)
- Blocks: None (post-run analytics)

## Risk Assessment

**Complexity:** Medium

**Key Risks:**
1. **Schwab rate limiting for predictions**: ~50-100 unique tickers per cycle may stress API limits
   - *Mitigation*: Ticker batching (one Schwab call per unique ticker), real positions have priority access
2. **Strike selection for illiquid tickers**: Some WSB tickers may have thin options chains
   - *Mitigation*: Graceful degradation (status='expired', append warning), no accuracy impact for unavailable tickers
3. **Expired-past-expiration**: If system not run for 20+ days, predictions with DTE < 0 resolved immediately on next run
   - *Acceptable*: Same handling as real positions (Phase 6 checks)
4. **EMA calculation complexity**: 70% old + 30% new requires loading old value, updating, storing
   - *Mitigation*: Straightforward SQL UPDATE, test with multiple updates
5. **Cold start period improvement**: Accuracy data within ~17-30 DTE (vs 30-60 days under position-based system)
   - *Acceptable*: Major improvement, Phase 1 is experimental
6. **Evaluation period lockstep management**: 4 portfolios must have synchronized period boundaries
   - *Mitigation*: Create all 4 periods in single transaction, use same start_date
7. **S&P 500 benchmark fetch**: yfinance availability for ^GSPC
   - *Mitigation*: Cache S&P 500 prices in price_history table, retry on failure

**Overall Risk Level:** Medium (prediction creation adds Schwab API dependency, but reuses existing patterns)

## Implementation Notes

- **End-of-timeline placement confirmed:** Epic-009 remains at end of implementation order. Author trust accuracy updates depend on resolved predictions from Phase 6 exit monitoring. [qc-rm-004]
- **Backfill consideration:** If initial analysis runs occur before epic-009 is implemented, author trust metrics may need a one-time backfill from historical comments. Predictions created retroactively would need Schwab options data for the original dates (may not be available).
- **Prediction creation is Phase 3.5:** After AI analysis (Phase 3), before signal detection (Phase 4). Batched by unique ticker for Schwab API efficiency.

## Estimated Stories

1. **Author Trust Calculation**: Implement 3-component formula (quality, accuracy, tenure) with system_config weights (~2 pts)
2. **Author Metrics Update (Phase 7a)**: Increment counters (total_comments, high_quality_comments, upvotes), recalculate avg_conviction_score, update last_active (~2 pts)
3. **Prediction Creation & Strike Selection (Phase 3.5)**: For each comment_ticker (batched by unique ticker), create prediction record with option_type (call/put), select strike via epic-005's shared function, fetch entry premium from Schwab, contracts = max(1, floor(2000/(premium×100))). INSERT OR IGNORE for dedup. Append warnings for unavailable data. Handle graceful degradation. (~5 pts) [PIPE-057]
4. **Prediction Resolution & Accuracy Update (Phase 7a)**: Read predictions resolved by Phase 6 (blended simulated_return_pct from prediction_exits), determine is_correct, apply HITL overrides, EMA update to author.avg_sentiment_accuracy. (~4 pts) [PIPE-059]
5. **Evaluation Period Creation**: Create 4 periods (one per portfolio) at system start, synchronized start_date (~3 pts)
6. **Evaluation Period Completion**: After 30 days, calculate portfolio_return_pct, sp500_return_pct, relative_performance, win_rate, avg_return, signal_accuracy, set status='completed' (~3 pts)
7. **Prediction-Based Accuracy Tests**: 7 tests: basic positive/negative accuracy flow, HITL override reversing auto-resolution, HITL 'excluded' skipping EMA, cold start (NULL accuracy), sequential EMA across multiple predictions, neutral handling. (~4 pts)
