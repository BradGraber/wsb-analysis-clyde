---
id: epic-002
title: Reddit Data Acquisition Pipeline
requirements: [FR-010, FR-011, FR-038, FR-046, PIPE-001, PIPE-002, PIPE-003, PIPE-004, PIPE-005, PIPE-006, PIPE-007, PIPE-008, PIPE-009, PIPE-010, PIPE-011, PIPE-012, PIPE-013, PIPE-014, INT-REDDIT, ERR-REDDIT-OUTAGE, ERR-IMAGE-FAIL, CFG-INTERNAL-DATA]
priority: high
estimated_stories: 9
estimated_story_points: 34
---

# Epic: Reddit Data Acquisition Pipeline

## Description
Implement Async PRAW integration for fetching top 10 hot posts from r/wallstreetbets, extracting up to 1000 comments per post, prioritizing top 50 comments per post using composite scoring (financial keywords, author trust, engagement, depth penalty), building parent chain context, and performing image analysis on post images. Includes comment deduplication to prevent redundant AI costs.

## Requirements Traced

### Core Reddit Integration
- **FR-010**: Reddit API Integration vian Async PRAW (top 10 hot posts, 1000 comments/post, prioritize 50)
- **FR-011**: On-demand analysis (not scheduled)
- **FR-038**: Comment deduplication by reddit_id (reuse stored annotations)
- **FR-046**: Post image analysis via GPT-4o-mini vision (3 URL patterns, 3x retry with backoff)
- **INT-REDDIT**: OAuth2 via env vars (60 req/min rate limit vian Async PRAW)

### Pipeline Implementation (Phase 1-2)
- **PIPE-001**: Reddit authentication (Async PRAW OAuth2 from env vars)
- **PIPE-002**: Fetch top 10 hot posts from r/wallstreetbets
- **PIPE-003**: Image detection (i.redd.it, imgur, preview.redd.it)
- **PIPE-004**: Image analysis synchronously via GPT-4o-mini vision (charts, earnings, tickers)
- **PIPE-005**: Fetch 1000 comments per post sorted by engagement
- **PIPE-006**: Build parent chain arrays for threaded context
- **PIPE-007**: Store posts and comments in database

### Comment Prioritization (Phase 2)
- **PIPE-008**: Priority scoring formula: (financial*0.4) + (trust*0.3) + (engagement*0.3) - depth_penalty
- **PIPE-009**: Financial keyword detection (calls, puts, options, strike, expiry, DD, etc.)
- **PIPE-010**: Author trust lookup from authors table (0-1 scale)
- **PIPE-011**: Engagement score: log(upvotes + 1) × reply_count
- **PIPE-012**: Depth penalty for nested comments
- **PIPE-013**: Select top 50 per post (~500 total for AI analysis)
- **PIPE-014**: Attach parent chain context to selected comments

### Error Handling
- **ERR-REDDIT-OUTAGE**: Async PRAW exception during fetch → log + return HTTP 503 (Tier 1)
- **ERR-IMAGE-FAIL**: Retry 3x (2s, 5s, 10s), then log warning + set NULL + continue (Tier 3)

### Data Structures
- **CFG-INTERNAL-DATA**: ProcessedComment (11 fields), ProcessedPost (8 fields), ParentChainEntry (4 fields)

## Technical Scope

### Database Tables Affected
- reddit_posts (INSERT)
- comments (INSERT with deduplication check)
- authors (LOOKUP for trust scores)

### API Endpoints Included
None directly (this is backend pipeline logic)

### External Integrations Involved
- **Reddit API** vian Async PRAW (OAuth2, rate limiting)
- **OpenAI GPT-4o-mini Vision** for image analysis (synchronous, retry logic)

### Key Algorithms/Logic
- Priority scoring with 4-factor weighted formula
- Parent chain reconstruction for threaded comments
- Comment deduplication by reddit_id (check before fetch/AI)
- Image URL pattern detection across 3 domains
- Engagement score logarithmic formula

## Dependencies
- Depends on: epic-001 (database schema: reddit_posts, comments, authors)
- Blocks: epic-003 (AI analysis needs comments), epic-004 (signals need processed comments)

## Risk Assessment

**Complexity:** Medium-High

**Key Risks:**
1. **Async PRAW rate limiting**: 60 req/min may throttle 10 posts × 1000 comments (10k comments)
   - *Mitigation*: Async PRAW handles rate limiting automatically with built-in backoff
2. **Image analysis latency**: Synchronous vision API calls add 2-5s per post with image
   - *Mitigation*: Only 10 posts max, acceptable for 30-minute total runtime
3. **Parent chain complexity**: Recursive logic for threaded comments may be error-prone
   - *Mitigation*: Well-defined in PRD pseudocode, test with deeply nested threads
4. **Comment deduplication timing**: Must check before AI analysis (not just DB insert)
   - *Mitigation*: Explicit check in Phase 3 (PIPE-015)
5. **Financial keyword calibration**: Keyword list may miss WSB slang or over-match
   - *Mitigation*: Start with PRD-defined keywords, tune based on signal quality

**Overall Risk Level:** Medium

## Technology Decisions

Resolved during Phase 1 planning questions:

- **API Mocking:** VCR.py for recording/replaying Async PRAW API responses as cassettes in tests [qc-qa-003]

## Estimated Stories

1. **Async PRAW Authentication & Hot Posts Fetching**: OAuth2 setup, fetch top 10 hot posts
2. **Image Detection & Vision Analysis**: Detect 3 image URL patterns, GPT-4o-mini vision with retry logic
3. **Comment Fetching & Parent Chain Building**: Fetch 1000 comments/post, build parent chain arrays
4. **Financial Keyword Scoring**: Implement keyword detection with density calculation
5. **Author Trust Lookup**: Query authors table for trust scores (default 0.5 if not found)
6. **Engagement & Depth Scoring**: Log-based engagement score + depth penalty calculation
7. **Priority Scoring & Selection**: Composite scoring formula, select top 50 per post
8. **Comment Deduplication & Storage**: Check reddit_id uniqueness, store posts + comments with metadata
