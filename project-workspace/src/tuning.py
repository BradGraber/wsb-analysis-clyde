"""Tuning workbench service module.

Provides reusable functions for prompt tuning experiments:
- Comment loading and search
- Prompt building with configurable params
- OpenAI API calls with full config support
- Tuning run persistence and history queries
- Prompt config management (CRUD + dedup)

Used by both the API routes (src/api/routes/tuning.py) and can be
used by the CLI workbench (scripts/tune_prompt.py).
"""

import hashlib
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

import structlog

from src.prompts import SYSTEM_PROMPT, build_user_prompt
from src.ai_parser import parse_ai_response, normalize_tickers
from src.market_context import fetch_market_context, should_include_context, format_market_context

logger = structlog.get_logger(__name__)

# GPT-4o-mini pricing (per 1M tokens)
COST_PER_1M_INPUT = 0.15
COST_PER_1M_OUTPUT = 0.60


def load_comment(conn: sqlite3.Connection, reddit_id: str) -> Optional[Dict[str, Any]]:
    """Load a comment with its post context from the database.

    Args:
        conn: SQLite connection (must have row_factory = sqlite3.Row)
        reddit_id: Reddit comment ID

    Returns:
        Dict with comment fields or None if not found
    """
    row = conn.execute("""
        SELECT c.id, c.reddit_id, c.body, c.author, c.author_trust_score,
               c.parent_chain, c.sentiment, c.ai_confidence,
               c.sarcasm_detected, c.has_reasoning, c.reasoning_summary,
               c.score, c.created_utc, c.prioritization_score,
               p.title AS post_title, p.image_analysis
        FROM comments c
        JOIN reddit_posts p ON c.post_id = p.id
        WHERE c.reddit_id = ?
    """, (reddit_id,)).fetchone()

    if row is None:
        return None

    return dict(row)


def search_comments(
    conn: sqlite3.Connection,
    q: Optional[str] = None,
    sentiment: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Search comments with optional text and sentiment filters.

    Args:
        conn: SQLite connection
        q: Text search (LIKE on body, author, reddit_id)
        sentiment: Filter by sentiment value
        limit: Max results
        offset: Skip N results

    Returns:
        Tuple of (items list, total count)
    """
    where_clauses = []
    params: list = []

    if q:
        where_clauses.append(
            "(c.body LIKE ? OR c.author LIKE ? OR c.reddit_id LIKE ?)"
        )
        like = f"%{q}%"
        params.extend([like, like, like])

    if sentiment:
        where_clauses.append("c.sentiment = ?")
        params.append(sentiment)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Count total
    count_row = conn.execute(
        f"SELECT COUNT(*) as total FROM comments c {where_sql}", params
    ).fetchone()
    total = count_row["total"] if count_row else 0

    # Fetch page
    rows = conn.execute(f"""
        SELECT c.id, c.reddit_id, c.author, c.body, c.sentiment,
               c.ai_confidence, c.prioritization_score, c.score,
               c.sarcasm_detected, c.has_reasoning,
               p.title AS post_title
        FROM comments c
        JOIN reddit_posts p ON c.post_id = p.id
        {where_sql}
        ORDER BY c.id DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()

    items = [dict(row) for row in rows]
    return items, total


def build_prompts(
    comment: Dict[str, Any],
    market_context_str: Optional[str] = None,
    system_prompt_override: Optional[str] = None,
) -> Tuple[str, str]:
    """Build system and user prompts for a comment.

    Args:
        comment: Comment dict (from load_comment)
        market_context_str: Formatted market context or None
        system_prompt_override: Custom system prompt or None for default

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    sys_prompt = system_prompt_override or SYSTEM_PROMPT
    user_prompt = build_user_prompt(
        post_title=comment.get("post_title", "WSB Discussion"),
        image_description=comment.get("image_analysis"),
        parent_chain_formatted=comment.get("parent_chain") or "",
        author=comment.get("author", "unknown"),
        author_trust=comment.get("author_trust_score") or 0.5,
        comment_body=comment.get("body", ""),
        market_context=market_context_str,
    )
    return sys_prompt, user_prompt


def call_openai(
    system_prompt: str,
    user_prompt: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    top_p: float = 1.0,
    max_tokens: int = 500,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    response_format: Optional[str] = "json_object",
    api_base_url: Optional[str] = None,
) -> Tuple[str, Dict[str, int]]:
    """Make a direct OpenAI API call with full config support.

    Args:
        system_prompt: System message
        user_prompt: User message
        model: Model name
        temperature: Sampling temperature
        top_p: Top-p sampling
        max_tokens: Max completion tokens
        frequency_penalty: Frequency penalty (None to omit)
        presence_penalty: Presence penalty (None to omit)
        response_format: Response format type (e.g. 'json_object') or None
        api_base_url: Custom API base URL or None for default

    Returns:
        Tuple of (raw content string, usage dict with prompt_tokens/completion_tokens)
    """
    import openai

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    if api_base_url:
        client_kwargs["base_url"] = api_base_url

    client = openai.OpenAI(**client_kwargs)

    create_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }

    if frequency_penalty is not None:
        create_kwargs["frequency_penalty"] = frequency_penalty
    if presence_penalty is not None:
        create_kwargs["presence_penalty"] = presence_penalty
    if response_format:
        create_kwargs["response_format"] = {"type": response_format}

    response = client.chat.completions.create(**create_kwargs)

    content = response.choices[0].message.content
    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }
    return content, usage


def run_analysis(
    comment: Dict[str, Any],
    config: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Run a single analysis with the given config.

    Args:
        comment: Comment dict from load_comment
        config: Dict with keys: system_prompt, market_context, model,
                temperature, top_p, max_tokens, frequency_penalty,
                presence_penalty, response_format, api_base_url

    Returns:
        Tuple of (parsed result dict, usage dict)
    """
    sys_prompt, user_prompt = build_prompts(
        comment,
        config.get("market_context"),
        config.get("system_prompt"),
    )

    raw_content, usage = call_openai(
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        model=config.get("model", "gpt-4o-mini"),
        temperature=config.get("temperature", 0.3),
        top_p=config.get("top_p", 1.0),
        max_tokens=config.get("max_tokens", 500),
        frequency_penalty=config.get("frequency_penalty"),
        presence_penalty=config.get("presence_penalty"),
        response_format=config.get("response_format", "json_object"),
        api_base_url=config.get("api_base_url"),
    )

    parsed = parse_ai_response(raw_content)
    tickers, ticker_sentiments = normalize_tickers(
        parsed["tickers"], parsed["ticker_sentiments"]
    )
    parsed["tickers"] = tickers
    parsed["ticker_sentiments"] = ticker_sentiments

    return parsed, usage


def get_market_context() -> Optional[str]:
    """Fetch live market context with gate check.

    Returns:
        Formatted market context string, or None if flat day or unavailable
    """
    try:
        data = fetch_market_context()
        if data and should_include_context(data):
            return format_market_context(data)
    except Exception:
        pass
    return None


def resolve_market_context(param: Optional[Union[bool, str]]) -> Optional[str]:
    """Resolve market context from API parameter.

    Args:
        param: None=auto (fetch live), False=off, str=use as-is

    Returns:
        Market context string or None
    """
    if param is None:
        return get_market_context()
    if param is False:
        return None
    if isinstance(param, str):
        return param
    return get_market_context()


def calculate_cost(usage: Dict[str, int]) -> float:
    """Calculate cost from token usage.

    Args:
        usage: Dict with prompt_tokens and completion_tokens

    Returns:
        Cost in dollars
    """
    input_cost = usage.get("prompt_tokens", 0) * COST_PER_1M_INPUT / 1_000_000
    output_cost = usage.get("completion_tokens", 0) * COST_PER_1M_OUTPUT / 1_000_000
    return input_cost + output_cost


def _config_content_hash(
    system_prompt: str,
    provider: str,
    model: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    api_base_url: Optional[str] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    response_format: Optional[str] = None,
) -> str:
    """Generate a content hash for dedup of prompt configs."""
    parts = [
        system_prompt, provider, model,
        str(temperature), str(top_p), str(max_tokens),
        str(api_base_url), str(frequency_penalty),
        str(presence_penalty), str(response_format),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def get_or_create_prompt_config(
    conn: sqlite3.Connection,
    name: str,
    system_prompt: str,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    top_p: float = 1.0,
    max_tokens: int = 500,
    api_base_url: Optional[str] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    response_format: Optional[str] = None,
    is_default: bool = False,
) -> int:
    """Get existing prompt config by content hash, or create new one.

    Returns:
        prompt_config_id
    """
    # Check for exact match by key fields
    row = conn.execute("""
        SELECT id FROM prompt_configs
        WHERE system_prompt = ? AND provider = ? AND model = ?
          AND temperature = ? AND top_p = ? AND max_tokens = ?
          AND api_base_url IS ? AND frequency_penalty IS ?
          AND presence_penalty IS ? AND response_format IS ?
        LIMIT 1
    """, (
        system_prompt, provider, model, temperature, top_p, max_tokens,
        api_base_url, frequency_penalty, presence_penalty, response_format,
    )).fetchone()

    if row:
        return row["id"]

    conn.execute("""
        INSERT INTO prompt_configs (name, system_prompt, provider, model,
            temperature, top_p, max_tokens, api_base_url,
            frequency_penalty, presence_penalty, response_format, is_default)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name, system_prompt, provider, model, temperature, top_p, max_tokens,
        api_base_url, frequency_penalty, presence_penalty, response_format,
        is_default,
    ))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_default_prompt_config(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """Get the default prompt config.

    Returns:
        Config dict or None if no default exists
    """
    row = conn.execute(
        "SELECT * FROM prompt_configs WHERE is_default = 1 LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def get_prompt_config(conn: sqlite3.Connection, config_id: int) -> Optional[Dict[str, Any]]:
    """Get a prompt config by ID.

    Returns:
        Config dict or None
    """
    row = conn.execute(
        "SELECT * FROM prompt_configs WHERE id = ?", (config_id,)
    ).fetchone()
    return dict(row) if row else None


def list_prompt_configs(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """List all prompt configs.

    Returns:
        List of config dicts
    """
    rows = conn.execute(
        "SELECT * FROM prompt_configs ORDER BY is_default DESC, id ASC"
    ).fetchall()
    return [dict(row) for row in rows]


def create_prompt_config(conn: sqlite3.Connection, **kwargs) -> Dict[str, Any]:
    """Create a new prompt config.

    Args:
        conn: SQLite connection
        **kwargs: Fields for prompt_configs table

    Returns:
        Created config dict
    """
    fields = [
        "name", "system_prompt", "provider", "api_base_url", "model",
        "temperature", "top_p", "max_tokens", "top_k",
        "frequency_penalty", "presence_penalty", "response_format",
        "is_fine_tuned", "base_model", "fine_tune_job_id", "fine_tune_suffix",
    ]

    cols = []
    vals = []
    for f in fields:
        if f in kwargs:
            cols.append(f)
            vals.append(kwargs[f])

    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)

    conn.execute(
        f"INSERT INTO prompt_configs ({col_names}) VALUES ({placeholders})",
        vals,
    )
    conn.commit()

    config_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return get_prompt_config(conn, config_id)


def save_tuning_run(
    conn: sqlite3.Connection,
    comment_id: int,
    prompt_config_id: int,
    parsed: Dict[str, Any],
    usage: Dict[str, int],
    cost: float,
    mode: str = "single",
    label: Optional[str] = None,
    tag: Optional[str] = None,
    market_context_used: Optional[str] = None,
    user_prompt: Optional[str] = None,
) -> int:
    """Save a tuning run to the database.

    Returns:
        tuning_run id
    """
    conn.execute("""
        INSERT INTO tuning_runs (
            comment_id, prompt_config_id, market_context_used, user_prompt,
            sentiment, ai_confidence, sarcasm_detected, has_reasoning,
            reasoning_summary, tickers, ticker_sentiments,
            prompt_tokens, completion_tokens, cost, mode, label, tag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        comment_id,
        prompt_config_id,
        market_context_used,
        user_prompt,
        parsed.get("sentiment"),
        parsed.get("confidence"),
        parsed.get("sarcasm_detected", False),
        parsed.get("has_reasoning", False),
        parsed.get("reasoning_summary"),
        json.dumps(parsed.get("tickers", [])),
        json.dumps(parsed.get("ticker_sentiments", [])),
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        cost,
        mode,
        label,
        tag,
    ))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_tuning_history(
    conn: sqlite3.Connection,
    reddit_id: Optional[str] = None,
    config_id: Optional[int] = None,
    tag: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Query tuning runs with filters and joins.

    Returns:
        Tuple of (items list, total count)
    """
    where_clauses = []
    params: list = []

    if reddit_id:
        where_clauses.append("c.reddit_id = ?")
        params.append(reddit_id)

    if config_id:
        where_clauses.append("tr.prompt_config_id = ?")
        params.append(config_id)

    if tag:
        where_clauses.append("tr.tag = ?")
        params.append(tag)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    count_row = conn.execute(f"""
        SELECT COUNT(*) as total
        FROM tuning_runs tr
        JOIN comments c ON tr.comment_id = c.id
        {where_sql}
    """, params).fetchone()
    total = count_row["total"] if count_row else 0

    rows = conn.execute(f"""
        SELECT tr.*, c.reddit_id, c.body AS comment_body,
               c.author AS comment_author,
               pc.name AS config_name, pc.model AS config_model,
               pc.temperature AS config_temperature
        FROM tuning_runs tr
        JOIN comments c ON tr.comment_id = c.id
        JOIN prompt_configs pc ON tr.prompt_config_id = pc.id
        {where_sql}
        ORDER BY tr.id DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()

    items = [dict(row) for row in rows]
    return items, total


def config_to_call_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a prompt_config row dict to kwargs for call_openai / run_analysis."""
    return {
        "system_prompt": config["system_prompt"],
        "model": config.get("model", "gpt-4o-mini"),
        "temperature": config.get("temperature", 0.3),
        "top_p": config.get("top_p", 1.0),
        "max_tokens": config.get("max_tokens", 500),
        "frequency_penalty": config.get("frequency_penalty"),
        "presence_penalty": config.get("presence_penalty"),
        "response_format": config.get("response_format", "json_object"),
        "api_base_url": config.get("api_base_url"),
    }
