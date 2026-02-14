"""Tuning workbench API routes.

Provides endpoints for browsing comments, running prompt experiments,
comparing configs, and viewing tuning history.

Router prefix: /api/tuning
"""

import json
from collections import Counter
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.responses import wrap_response, raise_api_error, NOT_FOUND, VALIDATION_ERROR
from src.tuning import (
    load_comment,
    search_comments,
    build_prompts,
    run_analysis,
    resolve_market_context,
    calculate_cost,
    get_default_prompt_config,
    get_prompt_config,
    list_prompt_configs,
    create_prompt_config,
    save_tuning_run,
    get_tuning_history,
    config_to_call_kwargs,
)

router = APIRouter(prefix="/api/tuning", tags=["tuning"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AnalysisRequest(BaseModel):
    reddit_id: str
    prompt_config_id: Optional[int] = None
    market_context: Optional[Union[bool, str]] = None
    tag: Optional[str] = None
    no_log: bool = False


class MultiRunRequest(AnalysisRequest):
    runs: int = Field(default=5, ge=2, le=20)


class CompareRequest(BaseModel):
    reddit_id: str
    config_ids: List[int] = Field(min_length=2, max_length=5)
    market_context: Optional[Union[bool, str]] = None
    tag: Optional[str] = None


class PromptConfigCreate(BaseModel):
    name: str = Field(max_length=100)
    system_prompt: str
    provider: str = "openai"
    api_base_url: Optional[str] = None
    model: str = "gpt-4o-mini"
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: int = Field(default=500, ge=100, le=2000)
    top_k: Optional[int] = None
    frequency_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    response_format: Optional[str] = None
    is_fine_tuned: bool = False
    base_model: Optional[str] = None
    fine_tune_job_id: Optional[str] = None
    fine_tune_suffix: Optional[str] = None


class DryRunRequest(BaseModel):
    reddit_id: str
    prompt_config_id: Optional[int] = None
    market_context: Optional[Union[bool, str]] = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_db(request: Request):
    return request.app.state.db


def _resolve_config(db, config_id: Optional[int]) -> Dict[str, Any]:
    """Resolve a prompt config by ID or return default."""
    if config_id:
        config = get_prompt_config(db, config_id)
        if not config:
            raise_api_error(NOT_FOUND, f"Prompt config {config_id} not found")
        return config

    config = get_default_prompt_config(db)
    if not config:
        raise_api_error(NOT_FOUND, "No default prompt config found. Run the migration first.")
    return config


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@router.get("/comments")
async def browse_comments(
    request: Request,
    q: Optional[str] = None,
    sentiment: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Browse/search comments with optional filters."""
    db = _get_db(request)
    items, total = search_comments(db, q=q, sentiment=sentiment, limit=limit, offset=offset)
    return wrap_response(items, total=total)


@router.get("/comments/{reddit_id}")
async def get_comment(request: Request, reddit_id: str):
    """Get full comment detail."""
    db = _get_db(request)
    comment = load_comment(db, reddit_id)
    if not comment:
        raise_api_error(NOT_FOUND, f"Comment {reddit_id} not found")
    return wrap_response(comment)


# ---------------------------------------------------------------------------
# Prompt Configs
# ---------------------------------------------------------------------------

@router.get("/configs")
async def get_configs(request: Request):
    """List all prompt configs."""
    db = _get_db(request)
    configs = list_prompt_configs(db)
    return wrap_response(configs, total=len(configs))


@router.post("/configs")
async def create_config(request: Request, body: PromptConfigCreate):
    """Create a new prompt config."""
    db = _get_db(request)
    config = create_prompt_config(db, **body.model_dump(exclude_none=True))
    return wrap_response(config)


@router.get("/configs/{config_id}")
async def get_config(request: Request, config_id: int):
    """Get a single prompt config."""
    db = _get_db(request)
    config = get_prompt_config(db, config_id)
    if not config:
        raise_api_error(NOT_FOUND, f"Prompt config {config_id} not found")
    return wrap_response(config)


# ---------------------------------------------------------------------------
# Dry Run
# ---------------------------------------------------------------------------

@router.post("/dry-run")
async def dry_run(request: Request, body: DryRunRequest):
    """Preview prompts without calling the API."""
    db = _get_db(request)

    comment = load_comment(db, body.reddit_id)
    if not comment:
        raise_api_error(NOT_FOUND, f"Comment {body.reddit_id} not found")

    config = _resolve_config(db, body.prompt_config_id)
    market_ctx = resolve_market_context(body.market_context)

    sys_prompt, user_prompt = build_prompts(
        comment, market_ctx, config["system_prompt"]
    )

    return wrap_response({
        "system_prompt": sys_prompt,
        "user_prompt": user_prompt,
        "config": config,
        "market_context": market_ctx,
    })


# ---------------------------------------------------------------------------
# Analyze (single)
# ---------------------------------------------------------------------------

@router.post("/analyze")
async def analyze(request: Request, body: AnalysisRequest):
    """Run a single analysis and optionally save the tuning run."""
    db = _get_db(request)

    comment = load_comment(db, body.reddit_id)
    if not comment:
        raise_api_error(NOT_FOUND, f"Comment {body.reddit_id} not found")

    config = _resolve_config(db, body.prompt_config_id)
    market_ctx = resolve_market_context(body.market_context)

    call_kwargs = config_to_call_kwargs(config)
    call_kwargs["market_context"] = market_ctx

    parsed, usage = run_analysis(comment, call_kwargs)
    cost = calculate_cost(usage)

    # Build user prompt for logging
    _, user_prompt = build_prompts(comment, market_ctx, config["system_prompt"])

    run_id = None
    if not body.no_log:
        run_id = save_tuning_run(
            db,
            comment_id=comment["id"],
            prompt_config_id=config["id"],
            parsed=parsed,
            usage=usage,
            cost=cost,
            mode="single",
            tag=body.tag,
            market_context_used=market_ctx,
            user_prompt=user_prompt,
        )

    return wrap_response({
        "result": parsed,
        "usage": usage,
        "cost": cost,
        "tuning_run_id": run_id,
        "config_id": config["id"],
    })


# ---------------------------------------------------------------------------
# Multi-Run (SSE)
# ---------------------------------------------------------------------------

@router.post("/multi-run")
async def multi_run(request: Request, body: MultiRunRequest):
    """Run N analyses with SSE streaming."""
    db = _get_db(request)

    comment = load_comment(db, body.reddit_id)
    if not comment:
        raise_api_error(NOT_FOUND, f"Comment {body.reddit_id} not found")

    config = _resolve_config(db, body.prompt_config_id)
    market_ctx = resolve_market_context(body.market_context)

    call_kwargs = config_to_call_kwargs(config)
    call_kwargs["market_context"] = market_ctx

    _, user_prompt = build_prompts(comment, market_ctx, config["system_prompt"])

    async def generate():
        total_cost = 0.0
        sentiments = []
        confidences = []

        for i in range(body.runs):
            try:
                parsed, usage = run_analysis(comment, call_kwargs)
                cost = calculate_cost(usage)
                total_cost += cost
                sentiments.append(parsed["sentiment"])
                confidences.append(parsed["confidence"])

                run_id = None
                if not body.no_log:
                    run_id = save_tuning_run(
                        db,
                        comment_id=comment["id"],
                        prompt_config_id=config["id"],
                        parsed=parsed,
                        usage=usage,
                        cost=cost,
                        mode="multi",
                        label=f"run-{i + 1}",
                        tag=body.tag,
                        market_context_used=market_ctx,
                        user_prompt=user_prompt,
                    )

                event_data = json.dumps({
                    "run": i + 1,
                    "total": body.runs,
                    "result": parsed,
                    "usage": usage,
                    "cost": cost,
                    "tuning_run_id": run_id,
                })
                yield f"data: {event_data}\n\n"

            except Exception as e:
                error_data = json.dumps({
                    "run": i + 1,
                    "total": body.runs,
                    "error": str(e),
                })
                yield f"data: {error_data}\n\n"

        # Summary event
        counts = Counter(sentiments)
        summary = {
            "type": "summary",
            "total_runs": body.runs,
            "sentiment_counts": dict(counts),
            "avg_confidence": sum(confidences) / len(confidences) if confidences else 0,
            "total_cost": total_cost,
        }
        yield f"data: {json.dumps(summary)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Compare (SSE)
# ---------------------------------------------------------------------------

@router.post("/compare")
async def compare(request: Request, body: CompareRequest):
    """Compare multiple configs on the same comment via SSE."""
    db = _get_db(request)

    comment = load_comment(db, body.reddit_id)
    if not comment:
        raise_api_error(NOT_FOUND, f"Comment {body.reddit_id} not found")

    market_ctx = resolve_market_context(body.market_context)

    # Validate all config IDs exist
    configs = []
    for cid in body.config_ids:
        config = get_prompt_config(db, cid)
        if not config:
            raise_api_error(NOT_FOUND, f"Prompt config {cid} not found")
        configs.append(config)

    async def generate():
        for i, config in enumerate(configs):
            try:
                call_kwargs = config_to_call_kwargs(config)
                call_kwargs["market_context"] = market_ctx

                _, user_prompt = build_prompts(
                    comment, market_ctx, config["system_prompt"]
                )

                parsed, usage = run_analysis(comment, call_kwargs)
                cost = calculate_cost(usage)

                label = chr(65 + i)  # A, B, C...
                save_tuning_run(
                    db,
                    comment_id=comment["id"],
                    prompt_config_id=config["id"],
                    parsed=parsed,
                    usage=usage,
                    cost=cost,
                    mode="compare",
                    label=label,
                    tag=body.tag,
                    market_context_used=market_ctx,
                    user_prompt=user_prompt,
                )

                event_data = json.dumps({
                    "config_id": config["id"],
                    "config_name": config["name"],
                    "label": label,
                    "result": parsed,
                    "usage": usage,
                    "cost": cost,
                })
                yield f"data: {event_data}\n\n"

            except Exception as e:
                error_data = json.dumps({
                    "config_id": config["id"],
                    "config_name": config["name"],
                    "label": chr(65 + i),
                    "error": str(e),
                })
                yield f"data: {error_data}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/history")
async def history(
    request: Request,
    reddit_id: Optional[str] = None,
    config_id: Optional[int] = None,
    tag: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Browse tuning run history with filters."""
    db = _get_db(request)
    items, total = get_tuning_history(
        db, reddit_id=reddit_id, config_id=config_id, tag=tag,
        limit=limit, offset=offset,
    )
    return wrap_response(items, total=total)


# ---------------------------------------------------------------------------
# Market Context
# ---------------------------------------------------------------------------

@router.get("/market-context")
async def market_context():
    """Get current market context."""
    from src.market_context import fetch_market_context, should_include_context, format_market_context

    try:
        data = fetch_market_context()
        if data:
            included = should_include_context(data)
            formatted = format_market_context(data) if included else None
            return wrap_response({
                "raw": data,
                "included": included,
                "formatted": formatted,
            })
        return wrap_response({"raw": None, "included": False, "formatted": None})
    except Exception as e:
        return wrap_response({
            "raw": None,
            "included": False,
            "formatted": None,
            "error": str(e),
        })
