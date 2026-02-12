# Data Pipeline

The WSB Analysis pipeline fetches posts and comments from r/wallstreetbets, scores them by financial relevance, stores them in SQLite, and runs GPT-4o-mini sentiment analysis with ticker extraction.

## Pipeline Overview

```
Stage 1        Stage 2       Stage 3         Stage 4
FETCH    -->   SCORE   -->   STORE     -->   ANALYZE
Reddit API     Local         SQLite          OpenAI API
~30s           instant       instant         ~1s/comment

Output:        Output:       Output:         Output:
fetched.json   scored.json   to_analyze.json DB updated
```

| Stage | Script | API Costs | What It Does |
|-------|--------|-----------|--------------|
| 1. Fetch | `fetch.py` | Reddit (free) + OpenAI vision (optional) | Pull hot posts + comments from r/wallstreetbets |
| 2. Score | `score.py` | None | Rank comments by financial keyword density, author trust, engagement |
| 3. Store | `store.py` | None | Write posts + comments to SQLite, create analysis run |
| 4. Analyze | `analyze.py` | OpenAI chat (~$0.01/100 comments) | GPT-4o-mini sentiment analysis + ticker extraction |

## Prerequisites

### Python Environment

```bash
cd project-workspace
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "create another app..." at the bottom
3. Select "script" as the app type
4. Note the client ID (under the app name) and secret

### OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new key
3. Only needed for Stage 1 image analysis and Stage 4 sentiment analysis

### Environment Configuration

```bash
cp .env.example .env
```

Add your credentials to `.env`:

```
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_secret
REDDIT_USER_AGENT=wsb-analysis/1.0
OPENAI_API_KEY=your_openai_key    # optional for fetch --skip-images
```

## Quick Start

Run all 4 stages in sequence. This example fetches 3 posts with 50 comments each, skipping image analysis to avoid OpenAI costs in the fetch stage:

```bash
cd project-workspace
source venv/bin/activate

# 1. Fetch (Reddit creds required, ~30s)
python scripts/pipeline/fetch.py --limit 3 --comments 50 --skip-images

# 2. Score (no creds needed, instant)
python scripts/pipeline/score.py --top-n 10

# 3. Store (no creds needed, instant)
python scripts/pipeline/store.py

# 4. Analyze (OpenAI key required, ~$0.002 for 30 comments)
python scripts/pipeline/analyze.py
```

After running, you can view the results through the API:

```bash
uvicorn src.api.app:app --reload &
curl http://localhost:8000/runs/1/status
```

## Script Reference

All scripts are in `scripts/pipeline/` and should be run from the `project-workspace/` directory.

### fetch.py — Stage 1: Reddit Data Acquisition

Connects to Reddit via Async PRAW and pulls hot posts with their comment trees.

```bash
python scripts/pipeline/fetch.py [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | 10 | Number of hot posts to fetch |
| `--comments N` | 1000 | Max comments per post |
| `--skip-images` | off | Skip GPT-4o-mini image analysis (saves ~$0.01/image) |
| `-o PATH` | `data/pipeline/fetched.json` | Output file path |

**Required env vars:** `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`
**Optional env var:** `OPENAI_API_KEY` (required unless `--skip-images`)

**Example — minimal fetch, no OpenAI costs:**
```bash
python scripts/pipeline/fetch.py --limit 3 --comments 50 --skip-images
```

**Example — full fetch with image analysis:**
```bash
python scripts/pipeline/fetch.py --limit 10 --comments 1000
```

### score.py — Stage 2: Comment Scoring

Scores each comment using financial keyword matching, author trust lookups, and engagement metrics. Selects the top N highest-scoring comments per post.

```bash
python scripts/pipeline/score.py [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-i PATH` | `data/pipeline/fetched.json` | Input file from fetch stage |
| `--top-n N` | 50 | Comments to keep per post |
| `-o PATH` | `data/pipeline/scored.json` | Output file path |

**No API keys required.** Uses the database for author trust scores if available, otherwise defaults to 0.5.

**Example:**
```bash
python scripts/pipeline/score.py --top-n 25
```

### store.py — Stage 3: SQLite Storage

Persists posts and comments to the database, creates an analysis run record, and prepares the input file for the AI analysis stage.

```bash
python scripts/pipeline/store.py [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-i PATH` | `data/pipeline/scored.json` | Input file from score stage |
| `-o PATH` | `data/pipeline/to_analyze.json` | Output file for analyze stage |
| `--db-path PATH` | `$DB_PATH` or `./data/wsb.db` | SQLite database path |

**No API keys required.** Creates the database and schema automatically if they don't exist.

**Example:**
```bash
python scripts/pipeline/store.py --db-path ./data/test.db
```

### analyze.py — Stage 4: AI Sentiment Analysis

Sends comments to GPT-4o-mini for sentiment analysis and ticker extraction. Shows a cost estimate before proceeding.

```bash
python scripts/pipeline/analyze.py [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-i PATH` | `data/pipeline/to_analyze.json` | Input file from store stage |
| `--db-path PATH` | `$DB_PATH` or `./data/wsb.db` | SQLite database path |
| `--yes` | off | Skip cost confirmation prompt |

**Required env var:** `OPENAI_API_KEY`

**Example — interactive (shows cost, asks to confirm):**
```bash
python scripts/pipeline/analyze.py
```

**Example — non-interactive (for scripting):**
```bash
python scripts/pipeline/analyze.py --yes
```

## Data Format

Each stage reads and writes JSON files in `data/pipeline/`. Here are abbreviated examples of the data structures.

### fetched.json (fetch output)

```json
{
  "metadata": {
    "subreddit": "wallstreetbets",
    "fetched_at": "2026-02-12T10:00:00+00:00",
    "post_count": 3,
    "total_comments": 150,
    "images_found": 1,
    "images_analyzed": 0,
    "skip_images": true
  },
  "posts": [
    {
      "reddit_id": "1abc123",
      "title": "NVDA earnings play",
      "selftext": "...",
      "upvotes": 1234,
      "total_comments": 567,
      "image_urls": [],
      "image_analysis": null,
      "comments": [
        {
          "reddit_id": "comment1",
          "post_id": "1abc123",
          "author": "trader99",
          "body": "Bought calls at 150 strike",
          "score": 42,
          "depth": 0,
          "created_utc": 1707735000,
          "priority_score": 0.0,
          "financial_score": 0.0,
          "author_trust_score": 0.0,
          "parent_chain": []
        }
      ]
    }
  ]
}
```

### to_analyze.json (store output)

```json
{
  "metadata": {
    "run_id": 1,
    "comment_count": 30,
    "created_at": "2026-02-12T10:01:00+00:00",
    "db_path": "./data/wsb.db"
  },
  "comments": [
    {
      "reddit_id": "comment1",
      "body": "Bought calls at 150 strike",
      "author": "trader99",
      "author_trust_score": 0.5,
      "post_id": "1abc123",
      "post_db_id": 1,
      "post_title": "NVDA earnings play",
      "image_description": null,
      "parent_chain_formatted": ""
    }
  ]
}
```

## Cost Guide

### Fetch Stage (image analysis)

- **Without `--skip-images`:** ~$0.01 per image (GPT-4o-mini vision)
- **With `--skip-images`:** Free (Reddit API only)
- Typically 1-3 image posts in a batch of 10

### Analyze Stage (sentiment)

- **Per comment:** ~$0.000075 (500 input + 100 output tokens at GPT-4o-mini rates)
- **100 comments:** ~$0.01
- **1,000 comments:** ~$0.08

The analyze script shows an estimate before proceeding and asks for confirmation.

### Minimizing Costs

- Use `--skip-images` on fetch to avoid vision API calls
- Use `--limit 3 --comments 50` for testing (150 comments max)
- Use `--top-n 10` on score to reduce the comment count before analysis
- Re-run analyze on the same data: deduplication skips already-analyzed comments

## Troubleshooting

### Missing environment variables

```
Error: Missing environment variables: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET
```

Make sure your `.env` file is in the `project-workspace/` directory (where you run the scripts from) and contains the required variables.

### Reddit rate limiting

```
prawcore.exceptions.TooManyRequests
```

Reddit limits API requests. Wait a minute and try again, or reduce `--limit` and `--comments`.

### Database not found (analyze stage)

```
Error: Database not found: ./data/wsb.db
```

Run `store.py` first to create the database, or specify a different path with `--db-path`.

### Input file not found

```
Error: Input file not found: data/pipeline/fetched.json
```

Each stage depends on the previous stage's output. Run them in order: fetch, score, store, analyze.

### OpenAI API errors

If you see rate limit or API errors during the analyze stage, the script has built-in retry logic (1 retry for malformed JSON, 3 retries with exponential backoff for rate limits). Persistent failures are skipped and logged.
