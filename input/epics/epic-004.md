---
id: epic-004
title: Signal Detection & Confidence Calculation
requirements: [FR-001, FR-015, FR-016, FR-017, FR-019, FR-020, FR-032, FR-033, FR-039, FR-040, PIPE-023, PIPE-024, PIPE-025, PIPE-026, PIPE-027, PIPE-028, PIPE-029, PIPE-030]
priority: high
estimated_stories: 7
estimated_story_points: 21
---

# Epic: Signal Detection & Confidence Calculation

## Description
Implement Quality and Consensus signal detection algorithms that aggregate AI-annotated comments by ticker and signal type. Calculate composite confidence scores using 4-factor weighted formula (volume, alignment, AI confidence, author trust). Detect emergence signals when cold tickers suddenly gain traction. Daily rollup model with UPSERT pattern for iterative refinement within a day.

## Requirements Traced

### Signal Detection Core
- **FR-001**: Signal-Based Trend Detection (Quality + Consensus methods)
- **FR-015**: Quality Signal Detection (≥2 users with reasoning, unanimous direction, AI confidence ≥0.6)
- **FR-016**: Consensus Signal Detection (≥30 comments, ≥8 users, ≥70% alignment)
- **FR-017**: Separate signal tracking (Quality vs Consensus as distinct entities)
- **FR-039**: Daily signal rollup (one signal per ticker/signal_type/day, first run creates, subsequent updates)
- **FR-040**: Signal confidence calculation (volume*0.25 + alignment*0.25 + ai_confidence*0.30 + author_trust*0.20)

### Emergence Detection
- **FR-019**: Emergence flag detection (cold <3 mentions in 7 days → hot ≥13 mentions, ≥8 users)
- **FR-020**: Historical comparison (7-day baseline for emergence)
- **FR-032**: Emergence activation threshold (Days 1-7: is_emergence=NULL, Day 8+: active)
- **FR-033**: Emergence weighting (no effect on position sizing in Phase 1, metadata only)

### Pipeline Implementation (Phase 4)
- **PIPE-023**: Group comments by ticker (JOIN comment_tickers + comments WHERE analysis_run_id = current)
- **PIPE-024**: Group by signal date (current UTC calendar day)
- **PIPE-025**: Quality signal calculation (count distinct users with reasoning, check unanimity)
- **PIPE-026**: Consensus signal calculation (count comments, users, alignment percentage)
- **PIPE-027**: Signal confidence calculation (4-factor weighted formula with config-driven weights)
- **PIPE-028**: Emergence detection (prior 7-day baseline: prior_mentions <3 AND current ≥13 AND users ≥8, NULL during warmup)
- **PIPE-029**: Signal UPSERT (UNIQUE on ticker, signal_type, signal_date; first run creates, subsequent updates)
- **PIPE-030**: Link signal comments (INSERT INTO signal_comments for each contributing comment)

## Technical Scope

### Database Tables Affected
- signals (INSERT/UPDATE via UPSERT)
- signal_comments (INSERT junction records)
- comment_tickers (JOIN for per-ticker sentiment)
- comments (JOIN for AI annotations)
- system_config (READ for thresholds and weights)

### API Endpoints Included
None directly (this is backend pipeline logic)

### External Integrations Involved
None (pure database aggregation logic)

### Key Algorithms/Logic
- **Quality signal aggregation**: Filter for has_reasoning=true, sarcasm_detected=false, ai_confidence≥0.6, check unanimous direction
- **Consensus signal aggregation**: Count comments, distinct users, calculate alignment percentage
- **Confidence calculation**: 4-factor weighted formula with configurable weights from system_config
- **Volume score**: Distinct users for Quality, comment count for Consensus (different formulas per signal type)
- **Alignment score**: 1.0 for Quality (unanimity requirement), percentage for Consensus
- **Emergence detection**: Query prior 7 days per ticker, compare mention/user counts
- **Daily rollup UPSERT**: ON CONFLICT (ticker, signal_type, signal_date) DO UPDATE

## Dependencies
- Depends on: epic-001 (database: signals, signal_comments, system_config), epic-003 (AI-annotated comments)
- Blocks: epic-005 (position management needs qualified signals), epic-007 (dashboard needs signals to display)

## Risk Assessment

**Complexity:** Medium-High

**Key Risks:**
1. **Quality unanimity logic**: Must ensure all reasoning comments agree on direction (bullish/bearish), not just sentiment
   - *Mitigation*: Use comment_tickers.sentiment (per-ticker) as defined in PRD
2. **Consensus alignment calculation**: Neutral comments excluded, must handle division by zero
   - *Mitigation*: Filter neutrals before calculating alignment percentage
3. **Volume score formula divergence**: Quality uses distinct users, Consensus uses comment count
   - *Mitigation*: Document clearly in code, test both paths
4. **Emergence detection edge cases**: Cold tickers with exactly 3 mentions may flicker on/off
   - *Mitigation*: <3 threshold is clear, acceptable for Phase 1
5. **Configuration dependency**: All thresholds and weights must be read from system_config at runtime
   - *Mitigation*: Fail loudly if config keys missing
6. **UPSERT race conditions**: Multiple runs per day updating same signal
   - *Mitigation*: SQLite handles this natively, test with back-to-back runs

**Overall Risk Level:** Medium

## Technology Decisions

Resolved during Phase 1 planning questions:

- **Cold-Start Trust Default:** New/unknown authors use 0.5 trust score as default, consistent with TRUST-COLD-START definition [qc-rm-004]

## Estimated Stories

1. **Comment Aggregation by Ticker**: JOIN comment_tickers + comments WHERE analysis_run_id = current
2. **Quality Signal Detection**: Filter for reasoning, check unanimity, calculate quality_score
3. **Consensus Signal Detection**: Count comments/users, calculate alignment percentage
4. **Confidence Calculation**: 4-factor weighted formula with system_config weights
5. **Emergence Detection**: Query prior 7 days, compare mention/user counts, set is_emergence flag
6. **Daily Signal Rollup**: UPSERT on (ticker, signal_type, signal_date), populate signal_comments junction
