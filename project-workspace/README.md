# WSB Analysis Tool - Backend API

Reddit sentiment analysis pipeline for r/wallstreetbets. Fetches posts and comments, scores them by financial relevance, and runs GPT-4o-mini sentiment analysis with ticker extraction.

## Quick Start

### 1. Create a virtual environment and install dependencies

```bash
cd project-workspace
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On Windows use `venv\Scripts\activate` instead of `source venv/bin/activate`.

Remember to activate the venv (`source venv/bin/activate`) in any new terminal before running the API, tests, or scripts.

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the credentials you need. See the [Environment Variables](#environment-variables) section below for details on each variable and when it's required.

### 3. Initialize the database

The database file is created automatically at `./data/wsb.db` on first API startup. To populate it with test data:

```bash
# From project-workspace/
python scripts/seed_data.py
```

This creates realistic mock data across all tables (signals, positions, portfolios, etc.). The script is idempotent -- safe to run multiple times.

### 4. Start the API server

```bash
# From project-workspace/
uvicorn src.api.app:app --reload
```

The API runs on `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 5. Run the test suite

```bash
# From project-workspace/
python -m pytest tests/ -v
```

376 tests collected. 3 skip (Schwab OAuth flow requires manual browser interaction).

## API Endpoints

All responses use the standard envelope: `{ "data": ..., "meta": { "timestamp", "version", "total?" } }`.
Errors return: `{ "error": { "code", "message" } }`.

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Root health check |
| GET | `/health` | Health check (returns `{"status": "healthy"}`) |

### Signals

| Method | Path | Description |
|--------|------|-------------|
| GET | `/signals` | List signals with filters and pagination |
| GET | `/signals/history` | Historical confidence by ticker |
| GET | `/signals/{id}` | Single signal detail |
| GET | `/signals/{id}/comments` | Comments with AI annotations |

**Filters on `/signals`:** `ticker`, `signal_type`, `date_from`, `date_to`, `portfolio_id`, `limit`, `offset`

**Params on `/signals/history`:** `ticker`, `signal_type`, `days` (default 14)

### Positions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/positions` | List positions with filters, convenience fields, and nested exits |
| GET | `/positions/{id}` | Single position with exit strategy state and full exit history |

**Filters on `/positions`:** `portfolio_id`, `status`, `ticker`, `instrument_type`, `signal_type`, `limit`, `offset`

**Computed fields:** `current_price`, `unrealized_return_pct`, `nearest_exit_distance_pct`, `hold_days`, `dte` (options), `premium_change_pct` (options)

### Portfolios

| Method | Path | Description |
|--------|------|-------------|
| GET | `/portfolios` | All 4 portfolios with summary stats |
| GET | `/portfolios/{id}` | Single portfolio with allocation breakdown |

**Summary stats:** `value`, `cash`, `open_position_count`, `total_pnl`, `total_pnl_pct`

### Evaluation Periods

| Method | Path | Description |
|--------|------|-------------|
| GET | `/evaluation-periods` | Periods filtered by portfolio (requires `portfolio_id`) |

**Params:** `portfolio_id` (required -- returns 422 if missing)

### Analysis Runs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/runs` | Paginated list of analysis runs |
| GET | `/runs/{id}/status` | Polling-optimized run status |

**Status response fields:** `status`, `current_phase`, `phase_label`, `progress_current`, `progress_total`, `results`, `warnings`

### Prices & System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/prices/{ticker}` | Daily close prices from price_history (returns `[]` for unknown tickers) |
| GET | `/status` | System health dashboard |

**Params on `/prices/{ticker}`:** `days` (default 14, max 90)

**Status fields:** `current_pipeline_phase`, `emergence_active`, `emergence_days_remaining`, `open_position_count`, `last_run_completed_at`, `active_run_id`

## Testing the API

After starting the server and seeding data, try these:

```bash
# Health check
curl http://localhost:8000/health

# List all portfolios with summary stats
curl http://localhost:8000/portfolios

# Get signals filtered by ticker
curl "http://localhost:8000/signals?ticker=NVDA"

# Get positions for a portfolio
curl "http://localhost:8000/positions?portfolio_id=1&status=open"

# Get price history for sparklines
curl "http://localhost:8000/prices/AAPL?days=7"

# System status
curl http://localhost:8000/status

# Single signal with details
curl http://localhost:8000/signals/1

# Comments with AI annotations for a signal
curl http://localhost:8000/signals/1/comments

# Analysis run polling status
curl http://localhost:8000/runs/1/status

# Evaluation periods (portfolio_id required)
curl "http://localhost:8000/evaluation-periods?portfolio_id=1"

# Portfolio detail with allocation breakdown
curl http://localhost:8000/portfolios/1

# Position detail with exit history
curl http://localhost:8000/positions/1
```

## Data Pipeline

The analysis pipeline runs in four stages:

1. **Fetch** (`reddit.py`) — Connects to Reddit via Async PRAW and pulls the top 10 hot posts from r/wallstreetbets with up to 1,000 comments each. Detects image posts and analyzes them with GPT-4o-mini vision.

2. **Score** (`scoring.py`) — Ranks comments by financial relevance using keyword matching, author trust scores, and engagement metrics (upvotes, reply count). Selects the top 50 comments per post for AI analysis.

3. **Store** (`storage.py`) — Writes posts and scored comments to SQLite in atomic transactions. Deduplicates by `reddit_id` so re-runs skip already-stored content.

4. **Analyze** (`ai_client.py`, `ai_batch.py`, `ai_parser.py`, `prompts.py`, `ai_dedup.py`) — Sends comments to GPT-4o-mini for sentiment analysis and ticker extraction. Processes in concurrent batches of 5 with retry logic. Skips comments that already have annotations (dedup). Normalizes tickers and maps WSB slang to symbols (e.g., "the mouse" to DIS).

The pipeline orchestrator that chains these stages together is not yet built — individual modules can be called programmatically.

## Project Structure

```
project-workspace/
  data/wsb.db              # SQLite database (auto-created)
  scripts/seed_data.py     # Seed test data for development
  src/
    reddit.py              # Async PRAW client — fetch posts, comments, image detection
    scoring.py             # Comment priority scoring (financial keywords, engagement, trust)
    storage.py             # Atomic post/comment storage with deduplication
    ai_client.py           # OpenAI GPT-4o-mini wrapper with cost tracking
    ai_dedup.py            # Skip AI calls for already-annotated comments
    ai_parser.py           # Parse AI JSON responses, normalize tickers
    ai_batch.py            # Concurrent batch processing with retry
    prompts.py             # WSB-tuned sentiment analysis prompt templates
    models/
      reddit_models.py     # ProcessedPost, ProcessedComment, ParentChainEntry
    api/
      app.py               # FastAPI app (lifespan, CORS, exception handlers)
      models.py            # Pydantic models (ResponseEnvelope, PaginationParams, etc.)
      responses.py         # wrap_response(), raise_api_error(), error codes
      routes/
        signals.py         # /signals endpoints
        positions.py       # /positions endpoints
        portfolios.py      # /portfolios and /evaluation-periods endpoints
        runs.py            # /runs endpoints
        system.py          # /prices and /status endpoints
        auth.py            # /auth/schwab OAuth endpoints
    backend/
      db/
        schema.sql         # 16 table definitions
        seed.sql           # System config (34 keys) and 4 portfolios
        connection.py      # get_connection() context manager (WAL + FK)
      integrations/
        schwab.py          # Schwab OAuth client (ready for credentials)
      scripts/
        schwab_setup.py    # CLI OAuth setup flow
        schwab_verify.py   # Verify Schwab API connectivity
        validate_schema.py # Schema validation script
      utils/
        errors.py          # retry_with_backoff(), WarningsCollector
        logging_config.py  # Structlog JSON logging setup
  tests/                   # 376 behavioral tests
```

## Scripts

### `scripts/seed_data.py` -- Seed Development Data

Populates the database with realistic mock data across all tables. Idempotent -- safe to run multiple times.

```bash
python scripts/seed_data.py
```

### Schwab OAuth Setup

Two options for authenticating with Schwab. Both require `SCHWAB_CLIENT_ID`, `SCHWAB_CLIENT_SECRET`, and `SCHWAB_REDIRECT_URI` in your `.env`.

**Option A: Web-based (recommended)** -- The server handles the callback automatically.

1. Generate a self-signed certificate (one-time):

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -keyout certs/key.pem \
  -out certs/cert.pem -days 365 -nodes -subj "/CN=127.0.0.1"
```

2. Set your redirect URI in `.env`:

```
SCHWAB_REDIRECT_URI=https://127.0.0.1:8000/auth/schwab/callback
```

Register this same URL in the Schwab Developer Portal.

3. Start the server with HTTPS:

```bash
uvicorn src.api.app:app --reload --ssl-keyfile=./certs/key.pem --ssl-certfile=./certs/cert.pem
```

4. Visit `https://127.0.0.1:8000/auth/schwab/login` in your browser (accept the certificate warning). After granting consent, the server exchanges the code for tokens automatically.

**Option B: CLI script** -- Manual paste flow.

```bash
python3 src/backend/scripts/schwab_setup.py
```

Opens your browser for OAuth consent. After granting access, copy the callback URL from the browser and paste it into the terminal.

Access tokens refresh automatically (~30 min TTL). If the refresh token expires after 7 days of inactivity, re-authenticate using either method.

### `src/backend/scripts/schwab_verify.py` -- Verify Schwab Connection

Verifies that Schwab API credentials are working by fetching an AAPL stock quote and an AAPL options chain (14-21 DTE). Run this after `schwab_setup.py` to confirm everything is connected.

```bash
python3 src/backend/scripts/schwab_verify.py
```

### `src/backend/scripts/validate_schema.py` -- Validate DB Schema

Checks that the SQLite database schema matches the expected table definitions.

```bash
python3 src/backend/scripts/validate_schema.py
```

## Environment Variables

Copy `.env.example` to `.env` and fill in the values you need. Not all variables are required immediately -- each group is needed when its corresponding feature is used.

### Reddit API (Phase B: Data Pipeline)

| Variable | Required | Description |
|----------|----------|-------------|
| `REDDIT_CLIENT_ID` | Yes | OAuth2 client ID from your Reddit app |
| `REDDIT_CLIENT_SECRET` | Yes | OAuth2 secret from your Reddit app |
| `REDDIT_USER_AGENT` | Yes | User agent string (e.g. `wsb-analysis/1.0`) |

Create a Reddit "script" app at https://www.reddit.com/prefs/apps to get these credentials.

### OpenAI API (Phase B: AI Analysis)

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | API key for GPT-4o-mini analysis calls |

Get your key at https://platform.openai.com/api-keys. Monthly spend is tracked; the system warns above $60/month.

### Schwab API (Price Data)

| Variable | Required | Description |
|----------|----------|-------------|
| `SCHWAB_CLIENT_ID` | Yes | OAuth2 client ID from Schwab Developer Portal |
| `SCHWAB_CLIENT_SECRET` | Yes | OAuth2 client secret |
| `SCHWAB_REDIRECT_URI` | Yes | Callback URL (default: `https://127.0.0.1:8000/auth/schwab/callback`) |

Register at https://developer.schwab.com. See [Schwab OAuth Setup](#schwab-oauth-setup) for authentication options. Tokens are stored in `data/schwab_token.json` (git-ignored).

### Application Settings (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `./data/wsb.db` | SQLite database file path |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
