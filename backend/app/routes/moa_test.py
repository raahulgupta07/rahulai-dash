"""Mixture-of-Agents test endpoint (sidecar, no prod path).

POST /api/llm/moa/test  — runs the MoA consult panel against one question and
returns every advisor's analysis, the assembled peer block, per-model latency,
and a rough cost estimate. Purely a measurement surface: it does NOT touch the
agent loop, reports, dashboards, slides, or Excel. Safe to delete with the
feature.
"""
from __future__ import annotations

import time
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_db, get_current_organization
from app.models.organization import Organization
from app.models.user import User
from app.core.auth import current_user
from app.ai.mixture_of_agents import (
    consult,
    aggregate,
    build_peer_block,
    DEFAULT_PANEL,
    DEFAULT_AGGREGATOR,
)
from app.settings.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["llm"])

# Rough OpenRouter prices ($/1M tokens) for cost estimation only (in, out).
_PRICE = {
    "deepseek/deepseek-v4-pro": (0.43, 0.87),
    "minimax/minimax-m3": (0.30, 1.20),
    "qwen/qwen3.7-plus": (0.32, 1.28),
    "google/gemini-3.1-flash-lite": (0.25, 1.50),
    "z-ai/glm-5.2": (0.95, 3.00),
}


class MoATestRequest(BaseModel):
    question: str
    context: Optional[str] = ""
    models: Optional[List[str]] = None
    aggregate: bool = False          # also produce baseline vs MoA final answers
    aggregator: Optional[str] = None  # override writer model (default glm-5.2)


def _est_tokens(text: str) -> int:
    # ~4 chars/token, good enough for a cost ballpark.
    return max(1, int(len(text or "") / 4))


@router.post("/llm/moa/test")
async def moa_test(
    body: MoATestRequest,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_db),
    organization: Organization = Depends(get_current_organization),
):
    panel = body.models or DEFAULT_PANEL
    started = time.monotonic()
    analyses = await consult(
        db, organization, body.question,
        context=body.context or "", models=panel,
        usage_scope="moa_test",
    )
    total_ms = int((time.monotonic() - started) * 1000)
    peer_block = build_peer_block(analyses)

    prompt_tokens_est = _est_tokens(body.question) + _est_tokens(body.context or "")
    est_cost = 0.0
    for a in analyses:
        slug = a.get("model")
        pin, pout = _PRICE.get(slug, (0.5, 1.5))
        out_tok = _est_tokens(a.get("analysis", ""))
        est_cost += (prompt_tokens_est * pin + out_tok * pout) / 1_000_000

    ok = [a for a in analyses if a.get("ok")]
    aggregator = body.aggregator or DEFAULT_AGGREGATOR

    ab = None
    if body.aggregate:
        # Honest A/B: same writer model, with vs without the peer block.
        baseline = await aggregate(
            db, organization, body.question, peer_block="",
            context=body.context or "", model=aggregator, usage_scope="moa_test_baseline",
        )
        moa = await aggregate(
            db, organization, body.question, peer_block=peer_block,
            context=body.context or "", model=aggregator, usage_scope="moa_test_moa",
        )
        ab = {"baseline": baseline, "moa": moa}

    return {
        "question": body.question,
        "panel": panel,
        "aggregator": aggregator,
        "analyses": analyses,
        "peer_block": peer_block,
        "succeeded": len(ok),
        "total": len(analyses),
        "total_ms": total_ms,
        "est_cost_usd": round(est_cost, 5),
        "ab": ab,
    }
