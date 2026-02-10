---
id: epic-005
title: Position Management & Portfolio Limits
requirements: [FR-023, FR-024, FR-025, FR-035, FR-036, FR-037, PIPE-031, PIPE-032, PIPE-033, PIPE-034, PIPE-035, PIPE-036, PIPE-037, PIPE-038, PIPE-039, PIPE-040, PIPE-041]
priority: high
estimated_stories: 9
estimated_story_points: 37
---

# Epic: Position Management & Portfolio Limits

## Description
Implement position opening logic for 4 portfolios (stocks/options × quality/consensus) with confidence-weighted sizing, portfolio limits (10 positions max), replacement logic when at capacity, cash guards, and options strike selection with delta targeting. Includes market hours check, stocks long-only rule, and stop-loss/take-profit calculation at entry. Full scope — no options deferral. [qc-rm-002]

## Requirements Traced

### Position Sizing & Portfolio Structure
- **FR-023**: Confidence-weighted position sizing (stocks: 0.5×/0.75×/1.0× on base_allocation=portfolio/20, options: fixed 2%, min 2%, max 15%)
- **FR-024**: Separate dual-signal positions (both Quality + Consensus open in all 4 portfolios)
- **FR-025**: Maximum concurrent positions (10 per portfolio, replacement: new exceeds lowest by >0.1 confidence, safeguard: never replace >+5% unrealized gain)
- **FR-035**: Four-portfolio structure (stocks_quality, stocks_consensus, options_quality, options_consensus, $100k each, independent tracking)
- **FR-036**: Instrument type selection (stock long only Phase 1, options: call for bullish, put for bearish)
- **FR-037**: Options parameters (delta ~0.30 strike, 14-21 DTE, 2% portfolio per position, premium-based exit)

### Pipeline Implementation (Phase 5)
- **PIPE-031**: Market hours check (if outside 9:30-16:00 ET, skip position opens, log warning, signals still recorded)
- **PIPE-032**: Identify qualified signals (confidence ≥0.5 AND position_opened=false)
- **PIPE-033**: Determine target portfolios (Quality → stocks_quality + options_quality, Consensus → stocks_consensus + options_consensus)
- **PIPE-034**: Stocks long-only rule (bearish signal: skip stock portfolio, log, options still opens puts)
- **PIPE-035**: Fetch real-time quote (Schwab API for entry pricing: last trade for stocks, mark for options)
- **PIPE-036**: Position count check (query open positions WHERE portfolio_id = X)
- **PIPE-037**: Cash guard (if cash_available < position_size, skip position, log warning, continue)
- **PIPE-038**: Calculate stop/take-profit at entry (stocks: price × (1 + pct), options: premium-percentage monitoring)
- **PIPE-039**: Position replacement flow (close-then-open: fetch price, INSERT position_exits, UPDATE position closed, UPDATE portfolio cash, open new)
- **PIPE-040**: Set position_opened flag (TRUE when at least one position opened for signal)
- **PIPE-041**: Portfolio value update (current_value = cash + SUM(stock MTM) + SUM(option MTM))

## Technical Scope

### Database Tables Affected
- signals (UPDATE position_opened=true)
- positions (INSERT new positions)
- portfolios (UPDATE cash_available, current_value)
- position_exits (INSERT for replacement close-then-open)
- system_config (READ for sizing multipliers and thresholds)

### API Endpoints Included
None directly (this is backend pipeline logic)

### External Integrations Involved
- **Schwab API**: Real-time stock quotes (last trade), options chains with greeks (mark price), delta filtering (client from epic-001)

### Key Algorithms/Logic
- **Confidence-weighted sizing**: 3-tier multipliers based on confidence buckets (0.5-0.7, 0.7-0.9, 0.9-1.0)
- **Base allocation calculation**: stocks: portfolio_value / 20, options: portfolio_value × 0.02
- **Position limits enforcement**: Check count before open, trigger replacement if at capacity
- **Replacement logic**: Find lowest confidence position in THIS portfolio, check >0.1 delta, check <+5% unrealized gain
- **Options strike selection**: Fetch Schwab options chain, filter DTE (14-21), sort by delta distance from 0.30, check tolerance ([+0.15, +0.50] calls, [-0.50, -0.15] puts)
- **Stop-loss/take-profit calculation**: stocks: entry_price × (1 + stop_loss_pct), options: monitored as premium percentage
- **Cash guard**: position_size ≤ cash_available, skip if insufficient
- **Market hours check**: 9:30-16:00 ET (client-side calculation), skip opens if outside

## Dependencies
- Depends on: epic-001 (database + Schwab client), epic-004 (qualified signals)
- Blocks: epic-006 (exit monitoring needs open positions)

**Note:** epic-006 dependency removed. Schwab client now provided by epic-001, eliminating the circular reference between epic-005 and epic-006.

## Risk Assessment

**Complexity:** High

**Key Risks:**
1. **Options strike selection complexity**: Iterating options chains, filtering by DTE and delta, checking tolerance ranges
   - *Mitigation*: Well-defined fallback scenarios (no valid strike → skip, log warning)
2. **Replacement logic edge cases**: What if all positions have >+5% unrealized gain? (Answer: no replacement, skip new signal)
   - *Mitigation*: Explicit safeguard in PRD, test with mock portfolio at capacity with all winners
3. **Cash guard timing**: Must check BEFORE opening position, not after (prevents overdraft)
   - *Mitigation*: Explicit check in PIPE-037, fail gracefully with log
4. **position_opened flag granularity**: Signal-level (not per-portfolio) means partial failures (stock opens, options fails) blocks retry
   - *Known limitation*: Documented in PRD Phase 3c (SD-014), acceptable for Phase 1
5. **Market hours check timezone**: ET calculation on server (potential DST issues)
   - *Mitigation*: Use pytz for ET timezone handling
6. **Schwab API real-time quote availability**: If Schwab unavailable, position opening fails
   - *Mitigation*: Retry with backoff (Tier 2), skip if all retries fail (signal remains position_opened=false)

**Overall Risk Level:** High (options strike selection + replacement logic are complex)

## Implementation Notes

- **Shared Strike Selection Function:** Strike selection logic (DTE filtering, delta targeting, tolerance checking) must be implemented as a standalone, importable function (or MonitoredInstrument interface method) — reused by epic-009 for prediction creation. Design for reuse from the start.

## Estimated Stories

1. **Market Hours Check**: ET timezone handling, skip opens if outside 9:30-16:00
2. **Qualified Signal Filtering**: confidence ≥0.5 AND position_opened=false
3. **Confidence-Weighted Sizing**: 3-tier multipliers for stocks, fixed 2% for options, min/max enforcement
4. **Position Count & Replacement Logic**: Check 10-position limit, find lowest confidence, check >0.1 delta + <+5% unrealized gain
5. **Stocks Long-Only Rule**: Bearish signals skip stock portfolio, options still open puts
6. **Options Strike Selection**: Fetch Schwab chains, filter DTE (14-21), sort by delta distance, check tolerance
7. **Cash Guard & Position Opening**: Check cash_available, fetch Schwab quote, INSERT position, UPDATE portfolio cash
8. **Stop-Loss/Take-Profit Calculation**: Compute at entry for stocks (price-based), set premium monitoring for options
9. **Position Management Unit Tests**: Basic concurrency tests for Schwab quote fetches during position opening. (~3 pts) [qc-qa-004]
