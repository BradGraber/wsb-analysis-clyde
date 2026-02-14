"""Tests for tuning API routes (src/api/routes/tuning.py)."""

import json
import os
import sqlite3
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is on path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_DB_DIR = Path(__file__).parent.parent / "src" / "backend" / "db"
SCHEMA_SQL_PATH = _DB_DIR / "schema.sql"


@pytest.fixture
def tuning_client():
    """TestClient with seeded comment and prompt config data for tuning tests."""
    try:
        from src.api.app import app
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI app not available yet")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    old_db_path = os.environ.get("DB_PATH")
    os.environ["DB_PATH"] = db_path

    # Initialize schema
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    sql = SCHEMA_SQL_PATH.read_text()
    lines = [line for line in sql.splitlines()
             if not line.strip().upper().startswith("PRAGMA")]
    conn.executescript("\n".join(lines))
    conn.execute("PRAGMA foreign_keys = ON")

    # Seed test data
    conn.execute("INSERT INTO analysis_runs (id, status) VALUES (1, 'complete')")
    conn.execute(
        "INSERT INTO reddit_posts (id, reddit_id, title) VALUES (1, 'post1', 'YOLO SPY calls')"
    )
    conn.execute("""
        INSERT INTO comments (analysis_run_id, post_id, reddit_id, author, body,
            score, prioritization_score, sentiment, ai_confidence, sarcasm_detected,
            has_reasoning, author_trust_score, reasoning_summary)
        VALUES (1, 1, 'abc123', 'trader1', 'SPY to the moon! Diamond hands!',
            42, 0.85, 'bullish', 0.8, 0, 1, 0.7, 'Good DD with targets')
    """)
    conn.execute("""
        INSERT INTO comments (analysis_run_id, post_id, reddit_id, author, body,
            score, prioritization_score, sentiment, ai_confidence, sarcasm_detected,
            has_reasoning, author_trust_score)
        VALUES (1, 1, 'def456', 'bear_guy', 'Market is crashing tomorrow',
            10, 0.5, 'bearish', 0.9, 0, 1, 0.6)
    """)

    # Default prompt config
    conn.execute("""
        INSERT INTO prompt_configs (name, system_prompt, provider, model,
            temperature, top_p, max_tokens, response_format, is_default)
        VALUES ('default', 'You are a financial analyst.', 'openai', 'gpt-4o-mini',
            0.3, 1.0, 500, 'json_object', 1)
    """)
    conn.commit()
    conn.close()

    with TestClient(app) as client:
        yield client

    # Cleanup
    if old_db_path is not None:
        os.environ["DB_PATH"] = old_db_path
    elif "DB_PATH" in os.environ:
        del os.environ["DB_PATH"]

    os.unlink(db_path)
    for suffix in ["-wal", "-shm"]:
        p = db_path + suffix
        if os.path.exists(p):
            os.unlink(p)


# ---------------------------------------------------------------------------
# Comments endpoints
# ---------------------------------------------------------------------------

class TestBrowseComments:
    def test_list_comments(self, tuning_client):
        resp = tuning_client.get("/api/tuning/comments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["total"] == 2
        assert len(data["data"]) == 2

    def test_search_by_text(self, tuning_client):
        resp = tuning_client.get("/api/tuning/comments?q=moon")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["total"] == 1
        assert data["data"][0]["reddit_id"] == "abc123"

    def test_filter_by_sentiment(self, tuning_client):
        resp = tuning_client.get("/api/tuning/comments?sentiment=bearish")
        assert resp.status_code == 200
        assert data_total(resp) == 1

    def test_pagination(self, tuning_client):
        resp = tuning_client.get("/api/tuning/comments?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["meta"]["total"] == 2


class TestGetComment:
    def test_existing_comment(self, tuning_client):
        resp = tuning_client.get("/api/tuning/comments/abc123")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["reddit_id"] == "abc123"
        assert data["post_title"] == "YOLO SPY calls"

    def test_missing_comment_404(self, tuning_client):
        resp = tuning_client.get("/api/tuning/comments/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Configs endpoints
# ---------------------------------------------------------------------------

class TestConfigs:
    def test_list_configs(self, tuning_client):
        resp = tuning_client.get("/api/tuning/configs")
        assert resp.status_code == 200
        configs = resp.json()["data"]
        assert len(configs) >= 1
        assert configs[0]["is_default"] == 1

    def test_get_config(self, tuning_client):
        resp = tuning_client.get("/api/tuning/configs/1")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "default"

    def test_get_missing_config_404(self, tuning_client):
        resp = tuning_client.get("/api/tuning/configs/999")
        assert resp.status_code == 404

    def test_create_config(self, tuning_client):
        resp = tuning_client.post("/api/tuning/configs", json={
            "name": "hot-temp",
            "system_prompt": "You are an aggressive trader.",
            "model": "gpt-4o",
            "temperature": 0.9,
        })
        assert resp.status_code == 200
        config = resp.json()["data"]
        assert config["name"] == "hot-temp"
        assert config["model"] == "gpt-4o"
        assert config["temperature"] == 0.9


# ---------------------------------------------------------------------------
# Dry Run
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_returns_prompts(self, tuning_client):
        resp = tuning_client.post("/api/tuning/dry-run", json={
            "reddit_id": "abc123",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "system_prompt" in data
        assert "user_prompt" in data
        assert "SPY to the moon" in data["user_prompt"]

    def test_dry_run_missing_comment(self, tuning_client):
        resp = tuning_client.post("/api/tuning/dry-run", json={
            "reddit_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_dry_run_with_market_context_off(self, tuning_client):
        resp = tuning_client.post("/api/tuning/dry-run", json={
            "reddit_id": "abc123",
            "market_context": False,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["market_context"] is None


# ---------------------------------------------------------------------------
# Analyze (mocked OpenAI)
# ---------------------------------------------------------------------------

MOCK_AI_RESPONSE = json.dumps({
    "tickers": ["SPY"],
    "ticker_sentiments": ["bullish"],
    "sentiment": "bullish",
    "sarcasm_detected": False,
    "has_reasoning": True,
    "confidence": 0.85,
    "reasoning_summary": "Strong conviction call",
})


class TestAnalyze:
    @patch("src.tuning.call_openai")
    def test_single_analysis(self, mock_call, tuning_client):
        mock_call.return_value = (
            MOCK_AI_RESPONSE,
            {"prompt_tokens": 500, "completion_tokens": 100},
        )
        resp = tuning_client.post("/api/tuning/analyze", json={
            "reddit_id": "abc123",
            "market_context": False,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["result"]["sentiment"] == "bullish"
        assert data["cost"] > 0
        assert data["tuning_run_id"] is not None
        mock_call.assert_called_once()

    @patch("src.tuning.call_openai")
    def test_no_log(self, mock_call, tuning_client):
        mock_call.return_value = (
            MOCK_AI_RESPONSE,
            {"prompt_tokens": 500, "completion_tokens": 100},
        )
        resp = tuning_client.post("/api/tuning/analyze", json={
            "reddit_id": "abc123",
            "market_context": False,
            "no_log": True,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["tuning_run_id"] is None


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class TestHistory:
    @patch("src.tuning.call_openai")
    def test_history_after_analysis(self, mock_call, tuning_client):
        mock_call.return_value = (
            MOCK_AI_RESPONSE,
            {"prompt_tokens": 500, "completion_tokens": 100},
        )
        # Run an analysis first
        tuning_client.post("/api/tuning/analyze", json={
            "reddit_id": "abc123",
            "market_context": False,
            "tag": "test-history",
        })

        # Query history
        resp = tuning_client.get("/api/tuning/history?tag=test-history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["total"] == 1
        assert data["data"][0]["sentiment"] == "bullish"

    def test_empty_history(self, tuning_client):
        resp = tuning_client.get("/api/tuning/history")
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# Market Context
# ---------------------------------------------------------------------------

class TestMarketContext:
    @patch("src.market_context.fetch_market_context", return_value=None)
    def test_market_context_unavailable(self, mock_fetch, tuning_client):
        resp = tuning_client.get("/api/tuning/market-context")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["included"] is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def data_total(resp):
    return resp.json()["meta"]["total"]
