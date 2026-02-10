---
id: epic-001
title: Database Foundation & Configuration System
requirements: [DB-CONFIG, DB-AUTHORS, DB-POSTS, DB-SIGNALS, DB-PORTFOLIOS, DB-POSITIONS, DB-PRICE-HISTORY, DB-EVAL-PERIODS, DB-COMMENTS, DB-ANALYSIS-RUNS, DB-SIGNAL-COMMENTS, DB-COMMENT-TICKERS, DB-POSITION-EXITS, DB-PREDICTIONS, DB-PREDICTION-OUTCOMES, DB-PREDICTION-EXITS, DB-FK-ENFORCE, DB-WAL, DB-INIT, DB-SCHEMA-EVOLVE, CFG-SIGNAL-THRESHOLDS, CFG-CONFIDENCE-WEIGHTS, CFG-TRUST-WEIGHTS, CFG-STOCK-EXIT, CFG-OPTIONS-EXIT, CFG-SYSTEM-STATE, CFG-RUNTIME-READ, INT-ENV-VARS, INT-TOKEN-STORAGE, INT-SCHWAB, INT-SCHWAB-SETUP, INT-SCHWAB-REFRESH]
priority: high
estimated_stories: 8
estimated_story_points: 23
---

# Epic: Database Foundation & Configuration System

## Description
Establish the complete SQLite database schema (16 tables), configuration management system (34 system_config entries), initialization scripts, Schwab OAuth setup spike, SQLite concurrency validation, and shared error handling infrastructure. This Epic provides the foundational data layer and cross-cutting utilities for all other system components including foreign key enforcement, WAL mode for concurrent access, environment variable management, and the Schwab API client that epic-005 and epic-006 consume.

## Requirements Traced

### Database Tables (16)
- **DB-CONFIG**: system_config table with key/value pairs (34 entries)
- **DB-AUTHORS**: authors table tracking trust scores and engagement metrics
- **DB-POSTS**: reddit_posts table with image analysis
- **DB-SIGNALS**: signals table with position_opened flag and emergence detection
- **DB-PORTFOLIOS**: portfolios table (4 rows: stocks/options × quality/consensus)
- **DB-POSITIONS**: positions table (28+ columns for stocks + options)
- **DB-PRICE-HISTORY**: price_history with UPSERT pattern
- **DB-EVAL-PERIODS**: evaluation_periods for 30-day performance tracking
- **DB-COMMENTS**: comments with AI annotations and author_trust_score snapshot
- **DB-ANALYSIS-RUNS**: analysis_runs with status tracking and warnings JSON
- **DB-SIGNAL-COMMENTS**: Junction table linking signals to source comments
- **DB-COMMENT-TICKERS**: Junction table linking comments to tickers with sentiment
- **DB-POSITION-EXITS**: Normalized position exit events table
- **DB-PREDICTIONS**: Predictions table for simulated options positions from comment_tickers
- **DB-PREDICTION-OUTCOMES**: Daily premium snapshots for active predictions
- **DB-PREDICTION-EXITS**: Simulated exit events mirroring position_exits structure

### Database Configuration
- **DB-FK-ENFORCE**: PRAGMA foreign_keys = ON on every connection
- **DB-WAL**: PRAGMA journal_mode = WAL for concurrent reads
- **DB-INIT**: Schema initialization with 34 config entries + 4 portfolios at $100k
- **DB-SCHEMA-EVOLVE**: Additive-only migration pattern (no framework)

### Configuration Management (34 entries)
- **CFG-SIGNAL-THRESHOLDS**: 5 entries (quality_min_users, quality_min_confidence, consensus_min_comments, etc.)
- **CFG-CONFIDENCE-WEIGHTS**: 4 weights (volume, alignment, ai_confidence, author_trust) summing to 1.0
- **CFG-TRUST-WEIGHTS**: 6 parameters for author trust calculation
- **CFG-STOCK-EXIT**: 10 stock exit strategy thresholds
- **CFG-OPTIONS-EXIT**: 6 options exit strategy thresholds
- **CFG-SYSTEM-STATE**: 2 entries (system_start_date, phase)
- **CFG-RUNTIME-READ**: All config must be read from DB at runtime (no hardcoded values)

### External Configuration
- **INT-ENV-VARS**: Environment variables for API credentials (.env file)
- **INT-TOKEN-STORAGE**: Schwab token JSON file storage pattern

### Schwab API Foundation
- **INT-SCHWAB**: OAuth 2.0 Authorization Code Grant, token storage ./data/schwab_token.json, access 30-min TTL, refresh 7-day TTL, graceful degradation
- **INT-SCHWAB-SETUP**: CLI setup script (opens browser, user consents, exchanges code for tokens, saves JSON)
- **INT-SCHWAB-REFRESH**: Proactive refresh before expiration, 401 → immediate refresh + retry, refresh token expired (7+ days) → log error + re-auth instructions

## Technology Decisions

Resolved during Phase 1 planning questions:

- **Project Layout:** Flat layout + pip + Makefile (no Poetry, no monorepo) [qc-sd-003]
- **Logging:** structlog for JSON-formatted structured logging [qc-sd-004]
- **Credential Security:** chmod 600 on `.env` and `schwab_token.json` at creation time [qc-sec-001]
- **Pipeline Orchestration:** Phase registry pattern with discrete entry points per pipeline phase [qc-arch-001]
- **Concurrency Model:** ThreadPoolExecutor for OpenAI batch-of-5 and Schwab concurrent fetches [qc-sd-002]

## Technical Scope

### Database Tables Affected
All 16 tables created in this Epic

### Key Algorithms/Logic
- UNIQUE constraints on junction tables and signals (ticker, signal_type, signal_date)
- Foreign key cascade relationships
- UPSERT pattern for price_history
- Default values for nullable columns
- SQLite connection factory with thread-safe isolation

### External Integrations
- **Schwab API**: OAuth 2.0 setup, basic quote + options chain verification (spike)

## Dependencies
- Depends on: None (this is the foundation)
- Blocks: All other Epics (everything depends on database schema). Schwab OAuth now foundational; epic-005 and epic-006 consume Schwab client from this epic.

## Risk Assessment

**Complexity:** Low-Medium

**Key Risks:**
1. **Schema evolution strategy**: Additive-only migrations may require full rebuild for structural changes
2. **Configuration completeness**: Must ensure all 34 entries are seeded with correct defaults
3. **Junction table performance**: May require indexing after load testing
4. **WAL mode compatibility**: Ensure all connections use WAL consistently
5. **Schwab API availability**: OAuth setup requires funded brokerage account and Schwab developer app approval

**Mitigation:**
- Well-defined schema in PRD Appendix B (detailed column definitions)
- Configuration defaults documented in PRD Section 3.3.4
- SQLite is proven technology for this scale (single user, <10k records/day)
- Schwab spike is time-boxed (2-3 days) to limit blast radius

## Estimated Stories

1. **Database Schema Creation**: Create all 16 table DDL statements with constraints
2. **Configuration Seed Data**: Insert 34 system_config entries with default values
3. **Portfolio Initialization**: Seed 4 portfolios at $100k starting capital
4. **Connection Management**: Implement DB connection factory with FK enforcement + WAL mode
5. **Schema Validation Script**: Create validation script to verify schema integrity and config completeness
6. **Schwab OAuth Spike**: CLI setup script, token storage (chmod 600), basic quote + options chain verification. Time-boxed 2-3 days. (~5 pts) [qc-arch-004, qc-sd-001, qc-sec-001]
7. **SQLite Concurrency Validation Spike**: Background thread write + main thread read test to validate WAL mode isolation. (~1 pt) [qc-arch-002]
8. **Error Handling Shared Module**: `retry_with_backoff()` utility, `WarningsCollector` class, structlog JSON configuration. (~2 pts) [qc-arch-005]
