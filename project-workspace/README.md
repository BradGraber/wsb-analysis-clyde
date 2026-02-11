# WSB Analysis Tool - Backend API

Phase A (Foundation) implementation: database schema, REST API, Schwab OAuth spike, and seed data.

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

### 2. Initialize the database

The database file is created automatically at `./data/wsb.db` on first API startup. To populate it with test data:

```bash
# From project-workspace/
python scripts/seed_data.py
```

This creates realistic mock data across all tables (signals, positions, portfolios, etc.). The script is idempotent -- safe to run multiple times.

### 3. Start the API server

```bash
# From project-workspace/
uvicorn src.api.app:app --reload
```

The API runs on `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 4. Run the test suite

```bash
# From project-workspace/
python -m pytest tests/ -v
```

209 tests pass. 6 skip (Schwab integration tests that require API credentials).

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

## Project Structure

```
project-workspace/
  data/wsb.db              # SQLite database (auto-created)
  scripts/seed_data.py     # Seed test data for development
  src/
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
  tests/                   # 209 behavioral tests
```

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `DB_PATH` | `./data/wsb.db` | SQLite database file path |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
