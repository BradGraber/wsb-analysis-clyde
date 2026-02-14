"""Tests for src/tuning.py — tuning workbench service module."""

import json
import os
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

# Ensure project root is on path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tuning import (
    load_comment,
    search_comments,
    build_prompts,
    calculate_cost,
    resolve_market_context,
    get_or_create_prompt_config,
    get_default_prompt_config,
    get_prompt_config,
    list_prompt_configs,
    create_prompt_config,
    save_tuning_run,
    get_tuning_history,
    config_to_call_kwargs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Create an in-memory DB with schema and seed data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Minimal schema for tests
    conn.executescript("""
        CREATE TABLE reddit_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reddit_id VARCHAR(20) UNIQUE NOT NULL,
            title TEXT,
            selftext TEXT,
            upvotes INT,
            total_comments INT,
            image_urls TEXT,
            image_analysis TEXT,
            fetched_at TIMESTAMP
        );

        CREATE TABLE analysis_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status VARCHAR(20),
            started_at TIMESTAMP
        );

        CREATE TABLE prompt_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            system_prompt TEXT NOT NULL,
            provider VARCHAR(20) NOT NULL DEFAULT 'openai',
            api_base_url VARCHAR(500),
            model VARCHAR(50) NOT NULL DEFAULT 'gpt-4o-mini',
            temperature REAL NOT NULL DEFAULT 0.3,
            top_p REAL NOT NULL DEFAULT 1.0,
            max_tokens INT NOT NULL DEFAULT 500,
            top_k INT,
            frequency_penalty REAL,
            presence_penalty REAL,
            response_format VARCHAR(20),
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            is_fine_tuned BOOLEAN NOT NULL DEFAULT FALSE,
            base_model VARCHAR(50),
            fine_tune_job_id VARCHAR(100),
            fine_tune_suffix VARCHAR(100),
            created_at TIMESTAMP DEFAULT (datetime('now'))
        );

        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_run_id INT NOT NULL,
            post_id INT NOT NULL,
            reddit_id VARCHAR(20) UNIQUE NOT NULL,
            author VARCHAR(50),
            body TEXT,
            created_utc TIMESTAMP,
            score INT,
            parent_comment_id INT,
            depth INT,
            prioritization_score FLOAT,
            sentiment VARCHAR(10),
            sarcasm_detected BOOLEAN,
            has_reasoning BOOLEAN,
            reasoning_summary TEXT,
            ai_confidence FLOAT,
            author_trust_score FLOAT,
            analyzed_at TIMESTAMP,
            parent_chain TEXT,
            prompt_config_id INT,
            FOREIGN KEY (analysis_run_id) REFERENCES analysis_runs(id),
            FOREIGN KEY (post_id) REFERENCES reddit_posts(id),
            FOREIGN KEY (prompt_config_id) REFERENCES prompt_configs(id)
        );

        CREATE TABLE tuning_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id INT NOT NULL,
            prompt_config_id INT NOT NULL,
            market_context_used TEXT,
            user_prompt TEXT,
            sentiment VARCHAR(10),
            ai_confidence FLOAT,
            sarcasm_detected BOOLEAN,
            has_reasoning BOOLEAN,
            reasoning_summary TEXT,
            tickers TEXT,
            ticker_sentiments TEXT,
            prompt_tokens INT,
            completion_tokens INT,
            cost REAL,
            mode VARCHAR(20),
            label VARCHAR(20),
            tag VARCHAR(100),
            created_at TIMESTAMP DEFAULT (datetime('now')),
            FOREIGN KEY (comment_id) REFERENCES comments(id),
            FOREIGN KEY (prompt_config_id) REFERENCES prompt_configs(id)
        );
    """)

    # Seed data
    conn.execute("INSERT INTO analysis_runs (id, status) VALUES (1, 'complete')")
    conn.execute(
        "INSERT INTO reddit_posts (id, reddit_id, title, image_analysis) VALUES (1, 'post1', 'YOLO SPY calls', NULL)"
    )
    conn.execute("""
        INSERT INTO comments (analysis_run_id, post_id, reddit_id, author, body,
            score, prioritization_score, sentiment, ai_confidence, sarcasm_detected,
            has_reasoning, author_trust_score)
        VALUES (1, 1, 'abc123', 'trader1', 'SPY to the moon! Diamond hands!',
            42, 0.85, 'bullish', 0.8, 0, 1, 0.7)
    """)
    conn.execute("""
        INSERT INTO comments (analysis_run_id, post_id, reddit_id, author, body,
            score, prioritization_score, sentiment, ai_confidence, sarcasm_detected,
            has_reasoning, author_trust_score)
        VALUES (1, 1, 'def456', 'bear_guy', 'This market is going to crash hard',
            10, 0.5, 'bearish', 0.9, 0, 1, 0.6)
    """)
    conn.execute("""
        INSERT INTO comments (analysis_run_id, post_id, reddit_id, author, body,
            score, prioritization_score)
        VALUES (1, 1, 'ghi789', 'newbie', 'What does DD mean?',
            2, 0.1)
    """)

    # Seed a default prompt config
    conn.execute("""
        INSERT INTO prompt_configs (name, system_prompt, provider, model,
            temperature, top_p, max_tokens, response_format, is_default)
        VALUES ('default', 'You are a financial analyst.', 'openai', 'gpt-4o-mini',
            0.3, 1.0, 500, 'json_object', 1)
    """)

    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# load_comment
# ---------------------------------------------------------------------------

class TestLoadComment:
    def test_loads_existing_comment(self, db):
        result = load_comment(db, "abc123")
        assert result is not None
        assert result["reddit_id"] == "abc123"
        assert result["author"] == "trader1"
        assert result["post_title"] == "YOLO SPY calls"

    def test_returns_none_for_missing(self, db):
        result = load_comment(db, "nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# search_comments
# ---------------------------------------------------------------------------

class TestSearchComments:
    def test_returns_all_comments(self, db):
        items, total = search_comments(db)
        assert total == 3
        assert len(items) == 3

    def test_text_search(self, db):
        items, total = search_comments(db, q="moon")
        assert total == 1
        assert items[0]["reddit_id"] == "abc123"

    def test_sentiment_filter(self, db):
        items, total = search_comments(db, sentiment="bearish")
        assert total == 1
        assert items[0]["reddit_id"] == "def456"

    def test_pagination(self, db):
        items, total = search_comments(db, limit=2, offset=0)
        assert total == 3
        assert len(items) == 2

        items2, _ = search_comments(db, limit=2, offset=2)
        assert len(items2) == 1

    def test_combined_filters(self, db):
        items, total = search_comments(db, q="crash", sentiment="bearish")
        assert total == 1


# ---------------------------------------------------------------------------
# build_prompts
# ---------------------------------------------------------------------------

class TestBuildPrompts:
    def test_builds_default_prompts(self, db):
        comment = load_comment(db, "abc123")
        sys_prompt, user_prompt = build_prompts(comment)
        assert "financial sentiment" in sys_prompt.lower() or len(sys_prompt) > 0
        assert "SPY to the moon" in user_prompt

    def test_custom_system_prompt(self, db):
        comment = load_comment(db, "abc123")
        sys_prompt, user_prompt = build_prompts(comment, system_prompt_override="Custom prompt")
        assert sys_prompt == "Custom prompt"

    def test_includes_market_context(self, db):
        comment = load_comment(db, "abc123")
        _, user_prompt = build_prompts(comment, market_context_str="SPY: -2.5%")
        assert "SPY: -2.5%" in user_prompt


# ---------------------------------------------------------------------------
# calculate_cost
# ---------------------------------------------------------------------------

class TestCalculateCost:
    def test_basic_cost(self):
        usage = {"prompt_tokens": 1000, "completion_tokens": 200}
        cost = calculate_cost(usage)
        expected = (1000 * 0.15 + 200 * 0.60) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_zero_tokens(self):
        cost = calculate_cost({})
        assert cost == 0.0


# ---------------------------------------------------------------------------
# resolve_market_context
# ---------------------------------------------------------------------------

class TestResolveMarketContext:
    def test_false_returns_none(self):
        assert resolve_market_context(False) is None

    def test_string_returns_as_is(self):
        assert resolve_market_context("SPY: +1.0%") == "SPY: +1.0%"

    @patch("src.tuning.get_market_context", return_value="Auto context")
    def test_none_fetches_auto(self, mock):
        result = resolve_market_context(None)
        assert result == "Auto context"
        mock.assert_called_once()


# ---------------------------------------------------------------------------
# Prompt Config CRUD
# ---------------------------------------------------------------------------

class TestPromptConfigs:
    def test_get_default(self, db):
        config = get_default_prompt_config(db)
        assert config is not None
        assert config["is_default"] == 1
        assert config["name"] == "default"

    def test_get_by_id(self, db):
        config = get_prompt_config(db, 1)
        assert config is not None
        assert config["name"] == "default"

    def test_get_missing_returns_none(self, db):
        assert get_prompt_config(db, 999) is None

    def test_list_configs(self, db):
        configs = list_prompt_configs(db)
        assert len(configs) >= 1
        # Default should be first (sorted by is_default DESC)
        assert configs[0]["is_default"] == 1

    def test_create_config(self, db):
        config = create_prompt_config(
            db,
            name="test-config",
            system_prompt="Test system prompt",
            model="gpt-4o",
            temperature=0.7,
        )
        assert config["name"] == "test-config"
        assert config["model"] == "gpt-4o"
        assert config["temperature"] == 0.7

    def test_get_or_create_dedup(self, db):
        # First call: creates
        id1 = get_or_create_prompt_config(
            db, name="dedup-test", system_prompt="Test prompt",
            provider="openai", model="gpt-4o-mini",
            temperature=0.3, top_p=1.0, max_tokens=500,
        )
        # Second call: should return same ID
        id2 = get_or_create_prompt_config(
            db, name="dedup-test", system_prompt="Test prompt",
            provider="openai", model="gpt-4o-mini",
            temperature=0.3, top_p=1.0, max_tokens=500,
        )
        assert id1 == id2

    def test_get_or_create_different_params(self, db):
        id1 = get_or_create_prompt_config(
            db, name="a", system_prompt="prompt",
            temperature=0.3,
        )
        id2 = get_or_create_prompt_config(
            db, name="b", system_prompt="prompt",
            temperature=0.7,
        )
        assert id1 != id2


# ---------------------------------------------------------------------------
# Tuning Runs
# ---------------------------------------------------------------------------

class TestTuningRuns:
    def test_save_and_query(self, db):
        parsed = {
            "sentiment": "bullish",
            "confidence": 0.85,
            "sarcasm_detected": False,
            "has_reasoning": True,
            "reasoning_summary": "Good DD",
            "tickers": ["SPY"],
            "ticker_sentiments": ["bullish"],
        }
        usage = {"prompt_tokens": 500, "completion_tokens": 100}

        run_id = save_tuning_run(
            db,
            comment_id=1,
            prompt_config_id=1,
            parsed=parsed,
            usage=usage,
            cost=0.0001,
            mode="single",
            tag="test-tag",
        )
        assert run_id > 0

        # Query it back
        items, total = get_tuning_history(db, tag="test-tag")
        assert total == 1
        assert items[0]["sentiment"] == "bullish"
        assert items[0]["config_name"] == "default"

    def test_history_filters(self, db):
        # Save two runs with different tags
        parsed = {"sentiment": "neutral", "confidence": 0.5, "tickers": [], "ticker_sentiments": []}
        usage = {"prompt_tokens": 100, "completion_tokens": 50}

        save_tuning_run(db, 1, 1, parsed, usage, 0.0, tag="tag-a")
        save_tuning_run(db, 1, 1, parsed, usage, 0.0, tag="tag-b")

        items_a, total_a = get_tuning_history(db, tag="tag-a")
        assert total_a == 1

        items_all, total_all = get_tuning_history(db)
        assert total_all == 2

    def test_history_reddit_id_filter(self, db):
        parsed = {"sentiment": "bullish", "confidence": 0.8, "tickers": [], "ticker_sentiments": []}
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        save_tuning_run(db, 1, 1, parsed, usage, 0.0)

        items, total = get_tuning_history(db, reddit_id="abc123")
        assert total == 1

        items, total = get_tuning_history(db, reddit_id="nonexistent")
        assert total == 0


# ---------------------------------------------------------------------------
# config_to_call_kwargs
# ---------------------------------------------------------------------------

class TestConfigToCallKwargs:
    def test_maps_fields(self):
        config = {
            "system_prompt": "Test",
            "model": "gpt-4o",
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 1000,
            "frequency_penalty": 0.5,
            "presence_penalty": None,
            "response_format": "json_object",
            "api_base_url": None,
        }
        kwargs = config_to_call_kwargs(config)
        assert kwargs["system_prompt"] == "Test"
        assert kwargs["model"] == "gpt-4o"
        assert kwargs["temperature"] == 0.7
        assert kwargs["frequency_penalty"] == 0.5
        assert kwargs["presence_penalty"] is None
