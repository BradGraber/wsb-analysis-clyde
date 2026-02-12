# Phase-b Test Conventions

This document outlines structural decisions made during test creation for phase-b (Data Pipeline + AI Analysis). Implementers should follow these conventions to ensure their code aligns with the test suite.

## Module Structure

Code organization based on task descriptions and functional grouping:

### Reddit Pipeline (Phase 2: Acquisition & Prioritization)
- **`src/reddit.py`** — Main Reddit integration module
  - `get_reddit_client()` — Async PRAW client initialization with OAuth2
  - `fetch_hot_posts()` — Fetch top 10 hot posts from r/wallstreetbets
  - `detect_image_urls()` — 4-level cascade: direct URL, url_overridden_by_dest, media_metadata, preview
  - `analyze_post_images()` — GPT-4o-mini vision analysis with retry, multi-image concatenation
  - `fetch_comments()` — Up to 1000 comments per post, engagement-sorted
  - `build_parent_chains()` — Build parent chain context for nested comments

- **`src/models/reddit_models.py`** — Data models for Reddit entities
  - `ProcessedPost` — 8 fields: reddit_id, title, selftext, upvotes, total_comments, image_urls, image_analysis, comments
  - `ProcessedComment` — 11 fields: reddit_id, post_id, author, body, score, depth, created_utc, priority_score, financial_score, author_trust_score, parent_chain
  - `ParentChainEntry` — 4 fields: id, body, depth, author

- **`src/scoring.py`** — Scoring and prioritization functions
  - `score_financial_keywords()` — Financial keyword density scoring (scaling_factor=10.0)
  - `lookup_author_trust_scores()` — Batch query authors table, default 0.5
  - `calculate_engagement()` — log(upvotes + 1) × reply_count
  - `calculate_depth_penalty()` — min(0.3, depth × 0.05)
  - `normalize_engagement_scores()` — Min-max normalization to [0, 1]
  - `calculate_priority_score()` — (financial × 0.4) + (trust × 0.3) + (engagement × 0.3) - depth_penalty
  - `score_and_select_comments()` — Select top N per post

- **`src/storage.py`** or functions in `src/reddit.py` — Storage operations
  - `check_duplicates()` — Batch query by reddit_id
  - `store_posts_and_comments()` — Atomic transaction per post

### AI Analysis Pipeline (Phase 3: AI Analysis)
- **`src/ai_client.py`** — OpenAI API client
  - `OpenAIClient` class with:
    - `__init__()` — Validates OPENAI_API_KEY from env, raises ValueError if missing
    - `send_chat_completion()` — Sends to gpt-4o-mini, returns {content, usage}
    - `send_vision_analysis()` — Vision API for image analysis
    - Cost tracking: monthly_tokens, current_month, warning at $60 threshold
    - Monthly reset on calendar month change

- **`src/prompts.py`** — Prompt templates
  - `SYSTEM_PROMPT` — Constant defining WSB style, meme definitions, 4 analysis tasks
  - `build_user_prompt()` — Template with placeholders: post_title, image_description, parent_chain_formatted, author, author_trust, comment_body
  - `format_parent_chain()` — Format parent_chain array as readable threaded context

- **`src/ai_parser.py`** — Response parsing and validation
  - `parse_ai_response()` — Strip markdown fences, parse JSON, validate 7 fields
  - `normalize_tickers()` — Uppercase, company name resolution, exclusion list (I, A, CEO, DD, YOLO), dedup
  - `MalformedResponseError` — Custom exception for parse failures
  - Validation: ticker_sentiments count must match tickers count
  - Confidence clamping: [0.0, 1.0] with debug log

- **`src/ai_dedup.py`** or similar — AI deduplication
  - `partition_for_analysis()` — Batch query by reddit_id, partition into skip/analyze lists
  - Skip if: existing with sentiment/ai_confidence populated
  - Analyze if: new OR existing with null annotations
  - Info log: "Deduplicated {n} comments, {m} new"

- **`src/ai_batch.py`** — Batch processing and transactions
  - `process_comments_in_batches()` — Main orchestrator, batches of 5
  - `process_single_batch()` — ThreadPoolExecutor max_workers=5, 1 comment per API call
  - `process_comment_with_retry()` — Malformed JSON retry (1x), rate limit retry (3x with exponential backoff)
  - `calculate_backoff_delay()` — [1s, 2s, 4s, 8s] max 30s
  - `commit_analysis_batch()` — Single transaction per batch of 5, rollback on failure
  - `store_comment_tickers()` — INSERT OR IGNORE into comment_tickers junction
  - `store_analysis_results()` — Persist comment + annotations, preserve author_trust_score snapshot

## Naming Conventions

### Environment Variables
- `REDDIT_CLIENT_ID` — Reddit OAuth2 client ID
- `REDDIT_CLIENT_SECRET` — Reddit OAuth2 client secret
- `REDDIT_USER_AGENT` — Reddit API user agent
- `OPENAI_API_KEY` — OpenAI API key

### Database Columns (from schema.sql)
- `reddit_posts`: reddit_id, title, selftext, upvotes, total_comments, image_urls, image_analysis, fetched_at
- `comments`: analysis_run_id, post_id, reddit_id, author, body, created_utc, score, depth, prioritization_score, sentiment, sarcasm_detected, has_reasoning, reasoning_summary, ai_confidence, author_trust_score, analyzed_at, parent_comment_id
- `comment_tickers`: comment_id (FK to comments.id), ticker (uppercase VARCHAR), sentiment, created_at

### Function Naming Patterns
- Reddit operations: `fetch_*`, `get_*`, `detect_*`, `analyze_*`
- Scoring operations: `score_*`, `calculate_*`, `normalize_*`, `lookup_*`
- AI operations: `send_*`, `parse_*`, `process_*`, `build_*`, `format_*`
- Storage operations: `store_*`, `check_*`, `commit_*`

### Constants
- `SYSTEM_PROMPT` — AI system prompt (string constant in prompts.py)
- Financial keywords list in `score_financial_keywords()`: calls, puts, options, strike, expiry, DD, due diligence, earnings, revenue, P/E, market cap, short, long, squeeze, gamma, theta, delta, IV, implied volatility
- Exclusion list in `normalize_tickers()`: I, A, CEO, DD, YOLO
- Retry delays: vision API [2s, 5s, 10s], rate limit [1s, 2s, 4s, 8s] max 30s
- Batch size: 5 comments per transaction

## Import Patterns

All imports use absolute paths from `src.` (relative to `project-workspace/`):

```python
from src.reddit import fetch_hot_posts, get_reddit_client
from src.models.reddit_models import ProcessedPost, ProcessedComment, ParentChainEntry
from src.scoring import score_financial_keywords, calculate_priority_score
from src.ai_client import OpenAIClient
from src.prompts import SYSTEM_PROMPT, build_user_prompt
from src.ai_parser import parse_ai_response, normalize_tickers
from src.ai_batch import process_comments_in_batches
from src.storage import store_posts_and_comments
```

**Important:** The FastAPI app is at `src.api.app`, NOT `src.backend.api.main`.

## Fixture Usage

Tests use fixtures from `conftest.py`:

- **`temp_db_path`** — Temporary database file path (auto-cleanup)
- **`db_connection`** — Raw SQLite connection to temp database
- **`schema_initialized_db`** — Database with schema loaded from `src/backend/db/schema.sql`
- **`seeded_db`** — Database with schema + seed data from `src/backend/db/seed.sql`
- **`test_client`** — FastAPI TestClient with temp database (for API tests)

### Schema Loading Pattern
Schema is `.sql` file, NOT a Python module. Tests must load via helper functions:

```python
from conftest import _load_schema, _exec_sql_file
```

**Important:** `executescript()` resets `PRAGMA foreign_keys` — run PRAGMAs separately via `conn.execute()`.

### Database Test Pattern
```python
def test_something(seeded_db):
    """Test description."""
    # seeded_db is already connected with schema + seed loaded

    # Insert test data
    seeded_db.execute("INSERT INTO table ...")
    seeded_db.commit()

    # Call function under test
    result = some_function(seeded_db, args)

    # Verify results
    row = seeded_db.execute("SELECT * FROM table WHERE ...").fetchone()
    assert row['column'] == expected
```

### API Test Pattern
```python
def test_api_endpoint(test_client):
    """Test description."""
    # test_client is FastAPI TestClient with temp DB

    response = test_client.post("/endpoint", json={...})

    assert response.status_code == 200
    assert response.json()['data']['field'] == expected
```

## Mocking Strategies

### External API Mocking
All tests mock external APIs — no real network calls:

#### Async PRAW (Reddit)
```python
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_reddit_fetch():
    mock_reddit = AsyncMock()
    mock_subreddit = AsyncMock()
    mock_reddit.subreddit.return_value = mock_subreddit

    # Mock async iteration
    async def async_iter(limit):
        for item in items:
            yield item

    mock_subreddit.hot.return_value = async_iter(10)

    result = await fetch_hot_posts(mock_reddit)
```

#### OpenAI Client
```python
with patch('src.ai_client.OpenAI') as mock_openai:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = 'Response text'
    mock_response.usage.total_tokens = 100

    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client

    client = OpenAIClient()
    result = await client.send_chat_completion("System", "User")
```

#### Structlog Logging
```python
with patch('structlog.get_logger') as mock_logger:
    logger_instance = MagicMock()
    mock_logger.return_value = logger_instance

    # Call function
    some_function()

    # Verify logging
    logger_instance.info.assert_called()
    logger_instance.error.assert_called_with(...)
```

### Environment Variable Mocking
```python
with patch.dict('os.environ', {
    'REDDIT_CLIENT_ID': 'test_id',
    'OPENAI_API_KEY': 'test_key'
}, clear=True):
    # Test code
```

### Async Sleep Mocking
```python
with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
    await function_with_retry()

    # Verify backoff delays
    sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
    assert sleep_calls == [2, 5, 10]
```

## Test Organization

Tests are organized by functional domain:

- **`test_reddit_client.py`** — Async PRAW authentication, hot posts fetching (story-002-001)
- **`test_image_detection.py`** — Image URL patterns, vision API retry (story-002-002)
- **`test_comment_fetching.py`** — Comment fetching, parent chains (story-002-003)
- **`test_scoring.py`** — Financial keywords, author trust, engagement, priority (stories 002-004 through 002-007)
- **`test_reddit_storage.py`** — Deduplication, storage, data models (story-002-008)
- **`test_ai_client.py`** — OpenAI client, cost tracking (story-003-001)
- **`test_ai_prompts.py`** — System/user prompts, JSON structure (story-003-002)
- **`test_ai_dedup_and_batch.py`** — AI dedup, concurrent batching, batch-of-5 commits (stories 003-003, 003-004, 003-007, 003-008)
- **`test_ai_parsing.py`** — JSON parsing, ticker normalization, retry logic (stories 003-005, 003-006)
- **`test_comment_tickers.py`** — Junction table inserts (story-003-009)

## Test Runner Command

Execute all phase-b tests from the project root:

```bash
(cd project-workspace && python -m pytest tests/test_reddit_client.py tests/test_image_detection.py tests/test_comment_fetching.py tests/test_scoring.py tests/test_reddit_storage.py tests/test_ai_client.py tests/test_ai_prompts.py tests/test_ai_dedup_and_batch.py tests/test_ai_parsing.py tests/test_comment_tickers.py -v)
```

**Note:** Use subshell syntax `(cd ... && command)` to prevent working directory drift across Bash calls.

### Run Specific Story Tests

```bash
# Reddit pipeline (Phase 2)
(cd project-workspace && python -m pytest tests/test_reddit_client.py tests/test_image_detection.py tests/test_comment_fetching.py tests/test_scoring.py tests/test_reddit_storage.py -v)

# AI analysis (Phase 3)
(cd project-workspace && python -m pytest tests/test_ai_client.py tests/test_ai_prompts.py tests/test_ai_dedup_and_batch.py tests/test_ai_parsing.py tests/test_comment_tickers.py -v)
```

## Exit Criteria Verification

Tests verify phase-b exit criteria as follows:

1. **PRAW authentication & hot posts** — `test_reddit_client.py`
2. **Image detection & vision analysis** — `test_image_detection.py`
3. **1000 comments with parent chains** — `test_comment_fetching.py`
4. **Priority scoring & top 50 selection** — `test_scoring.py`
5. **Comment deduplication** — `test_reddit_storage.py`, `test_ai_dedup_and_batch.py`
6. **Concurrent batch-of-5** — `test_ai_dedup_and_batch.py`
7. **AI response parsing** — `test_ai_parsing.py`, `test_ai_prompts.py`
8. **Batch-of-5 transactions** — `test_ai_dedup_and_batch.py`
9. **comment_tickers junction** — `test_comment_tickers.py`
10. **Cost tracking $60 warning** — `test_ai_client.py`

### Exit Criteria Requiring Manual Verification

The following exit criteria cannot be fully automated in unit tests:

- **Vue scaffold (story-008-001)** — Verify by running `npm run dev` in Vue app directory, check localhost:5173 for 4 portfolio tabs
- **Portfolio tabs/sub-tabs (story-008-002)** — Manual verification of tab navigation, shared composables functional
- **Sparkline spike (story-008-004)** — Recommendation document should exist at `project-workspace/docs/sparkline-recommendation.md` or similar

## Data Model Contracts

### ProcessedPost (8 fields)
```python
@dataclass
class ProcessedPost:
    reddit_id: str
    title: str
    selftext: str
    upvotes: int
    total_comments: int
    image_urls: List[str] = field(default_factory=list)
    image_analysis: Optional[str] = None
    comments: List[ProcessedComment] = field(default_factory=list)
```

### ProcessedComment (11 fields)
```python
@dataclass
class ProcessedComment:
    reddit_id: str
    post_id: str  # reddit_id of parent post
    author: str
    body: str
    score: int
    depth: int
    created_utc: int
    priority_score: float = 0.0
    financial_score: float = 0.0
    author_trust_score: float = 0.0
    parent_chain: List[ParentChainEntry] = field(default_factory=list)
```

### ParentChainEntry (4 fields)
```python
@dataclass
class ParentChainEntry:
    id: str
    body: str
    depth: int
    author: str
```

### AI Response JSON (7 required fields)
```json
{
    "tickers": ["AAPL", "MSFT"],
    "ticker_sentiments": ["bullish", "neutral"],
    "sentiment": "bullish",
    "sarcasm_detected": false,
    "has_reasoning": true,
    "confidence": 0.8,
    "reasoning_summary": "Strong DD with price targets"
}
```

## Notes for Implementers

1. **Async/await everywhere** — Reddit and OpenAI operations are async
2. **Error handling via structlog** — Use `structlog.get_logger()` for all logging
3. **Retry with backoff** — Vision API [2s, 5s, 10s], rate limit [1s, 2s, 4s, 8s]
4. **Batch size = 5** — ThreadPoolExecutor max_workers=5, commit batches of 5
5. **Author trust snapshot** — Persist from Phase 2, don't re-lookup in Phase 3
6. **Ticker normalization** — Uppercase, exclude (I, A, CEO, DD, YOLO), dedup
7. **Parent chain order** — Immediate parent first, root last
8. **Confidence clamping** — [0.0, 1.0] with debug log if out of range
9. **Cost tracking** — Monthly reset on calendar month change, warning at $60
10. **Financial keywords** — Case-insensitive, word boundary, multi-word phrases
11. **Priority formula** — (financial × 0.4) + (trust × 0.3) + (engagement × 0.3) - depth_penalty
12. **All tests should FAIL initially** — No implementation exists yet
