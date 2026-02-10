---
id: epic-003
title: AI Sentiment Analysis & Ticker Extraction
requirements: [FR-002, FR-021, FR-034, PIPE-015, PIPE-016, PIPE-017, PIPE-018, PIPE-019, PIPE-020, PIPE-021, PIPE-022, INT-OPENAI, ERR-OPENAI-RATE, ERR-MALFORMED-JSON, AI-SYSTEM-PROMPT, AI-USER-PROMPT, AI-RESPONSE-FORMAT, AI-CONFIDENCE-SCORING, AI-TICKER-RULES, AI-INDIVIDUAL, NFR-009]
priority: high
estimated_stories: 11
estimated_story_points: 40
---

# Epic: AI Sentiment Analysis & Ticker Extraction

## Description
Implement OpenAI GPT-4o-mini integration for analyzing ~500 prioritized WSB comments per run. Extract tickers, assess sentiment with sarcasm detection, identify substantive reasoning, and calculate AI confidence. Individual comment analysis (not batched) with batch-of-5 commits for cost protection. Includes retry logic for rate limits and malformed JSON responses.

## Requirements Traced

### Core AI Functionality
- **FR-002**: Sentiment analysis with sarcasm handling (OpenAI GPT-4o-mini)
- **FR-021**: Comment annotation storage (sentiment, sarcasm, reasoning, confidence)
- **FR-034**: AI-based ticker extraction (not regex, handles WSB slang)
- **INT-OPENAI**: Bearer token via OPENAI_API_KEY env var, rate limit handling with backoff
- **NFR-009**: Cost awareness (~$45/month, log warnings if >$60/month)

### Pipeline Implementation (Phase 3)
- **PIPE-015**: Comment deduplication check (query reddit_id, skip AI if exists, UPDATE analysis_run_id)
- **PIPE-016**: Build AI prompt (post title, image analysis, parent chain, comment body, author trust)
- **PIPE-017**: Concurrent AI calls (5 concurrent via asyncio/ThreadPoolExecutor, batches of 5)
- **PIPE-018**: Parse AI JSON response (tickers, ticker_sentiments, sentiment, sarcasm, reasoning, confidence, reasoning_summary)
- **PIPE-019**: Author trust snapshot (lookup current trust score, set on comment record)
- **PIPE-020**: Batch-of-5 commits (single transaction per batch, max loss 5 comments on crash)
- **PIPE-021**: Insert comment_tickers (comment_id, ticker, sentiment) for each extracted ticker
- **PIPE-022**: Malformed JSON retry (retry once, skip comment on failure, log and continue)

### Error Handling
- **ERR-OPENAI-RATE**: OpenAI 429 → exponential backoff (1s, 2s, 4s, 8s, max 30s), retry (Tier 2)
- **ERR-MALFORMED-JSON**: Retry once, skip comment on failure, log and continue (Tier 3)

### AI Specification (Appendix E)
- **AI-SYSTEM-PROMPT**: WSB communication style context (sarcasm, memes, inverse statements)
- **AI-USER-PROMPT**: Template with post context + parent chain + author trust + comment body
- **AI-RESPONSE-FORMAT**: JSON with 7 fields (tickers, ticker_sentiments, sentiment, sarcasm, reasoning, confidence, reasoning_summary)
- **AI-CONFIDENCE-SCORING**: Base 0.5 with modifiers (+0.2 clear statement, +0.2 reasoning, +0.1 high trust, -0.2 ambiguous sarcasm, etc.)
- **AI-TICKER-RULES**: Explicit tickers, uppercase normalization, resolve common names (DIS, META), exclude non-tickers (I, A, CEO), include crypto
- **AI-INDIVIDUAL**: 1 comment per API call (not batched) for accuracy

## Technology Decisions

Resolved during Phase 1 planning questions:

- **Concurrency Model:** ThreadPoolExecutor for 5 concurrent OpenAI requests [qc-sd-002]
- **API Mocking:** VCR.py for recording/replaying OpenAI API responses in tests [qc-qa-003]

## Technical Scope

### Database Tables Affected
- comments (INSERT or UPDATE if dedup)
- comment_tickers (INSERT per extracted ticker)
- authors (LOOKUP for trust snapshot)

### API Endpoints Included
None directly (this is backend pipeline logic)

### External Integrations Involved
- **OpenAI API** (GPT-4o-mini text model)
  - Endpoint: POST /v1/chat/completions
  - Auth: Bearer token
  - Rate limits: 429 responses with exponential backoff
  - Cost: ~$0.10 per 500 comments

### Key Algorithms/Logic
- Concurrent request batching (5 concurrent, batches of 5)
- Batch-of-5 transaction commits (cost protection)
- Malformed JSON retry logic (1 retry, then skip)
- AI confidence scoring with modifier rules
- Ticker extraction and normalization (uppercase, slang resolution)
- Author trust point-in-time snapshot

## Dependencies
- Depends on: epic-001 (database: comments, comment_tickers), epic-002 (prioritized comments ready)
- Blocks: epic-004 (signal detection needs AI-annotated comments)

## Risk Assessment

**Complexity:** High

**Key Risks:**
1. **AI cost overruns**: 500 comments × 3 runs/day × 30 days = 45k comments/month
   - *Mitigation*: Comment deduplication saves ~60-80% on reruns. Log warnings at $60/month threshold
2. **Rate limit throttling**: OpenAI 429 responses may slow pipeline
   - *Mitigation*: Exponential backoff (1s, 2s, 4s, 8s, max 30s) with retry logic
3. **Malformed JSON responses**: GPT-4o-mini may return invalid JSON under load
   - *Mitigation*: Retry once, skip comment on failure, log for review
4. **Ticker extraction accuracy**: AI may miss tickers or extract false positives (e.g., "I" as ticker)
   - *Mitigation*: AI-TICKER-RULES provides clear guidelines, but manual review may be needed
5. **Concurrency race conditions**: 5 concurrent requests with shared state (batch counter)
   - *Mitigation*: Use thread-safe data structures, test with load simulation
6. **Batch-of-5 data loss**: Crash at comment 448 loses last 3 comments' AI cost (~$0.03)
   - *Acceptable*: Cost-benefit tradeoff for simpler logic vs per-comment commits

**Overall Risk Level:** Medium-High (AI reliability is external dependency)

## Estimated Stories

1. **OpenAI Client Setup**: Bearer auth, request/response handling, base error handling
2. **AI Prompt Engineering**: System prompt + user prompt template with context injection
3. **Comment Deduplication Logic**: Check reddit_id before AI call, reuse annotations if exists
4. **Concurrent AI Request Batching**: 5 concurrent requests via ThreadPoolExecutor, batch management
5. **AI Response Parsing**: JSON extraction + validation, handle 7-field structure
6. **Malformed JSON Retry**: Retry logic with skip-on-failure, logging
7. **Author Trust Snapshot**: Lookup trust score at analysis time, store with comment
8. **Batch-of-5 Commit Transaction**: Transaction boundary per 5 comments, rollback on failure
9. **Comment Tickers Junction Population**: INSERT INTO comment_tickers for each ticker-sentiment pair
10. **Concurrency Unit Tests**: 3 tests for batch-of-5: all-succeed, 1-of-5-fails, commit timing verification. (~3 pts) [qc-qa-004]
11. **AI Parsing and Deduplication Unit Tests**: 8 tests for response parsing edge cases (malformed JSON, extra fields, missing fields), ticker normalization, confidence clamping, and Phase 3 dedup logic. (~3 pts) [QA review gap]
