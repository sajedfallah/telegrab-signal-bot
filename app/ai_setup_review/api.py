from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.market_candles import _admin_auth

from .ai_reviewer import (
    PROMPT_VERSION,
    REVIEWER_VERSION,
    review_setup,
)


router = APIRouter(
    prefix="/miniapp/api/admin/ai-setup-review",
    tags=["NEXUS AI Setup Reviewer"],
)


class AISetupReviewRequest(BaseModel):
    symbol: str = Field(
        default="XAUUSD",
        min_length=1,
        max_length=32,
    )
    direction: str = Field(
        pattern="^(?:BUY|SELL)$",
    )
    trade_mode: str = Field(
        default="INTRADAY",
        pattern="^(?:SWING|INTRADAY|FAST_SCALP)$",
    )


@router.post("")
async def ai_setup_review(
    req: AISetupReviewRequest,
    x_mt5_account: str | None = Header(
        default=None,
        alias="X-MT5-Account",
    ),
    x_admin_mode: str | None = Header(
        default=None,
        alias="X-Admin-Mode",
    ),
    x_admin_token: str | None = Header(
        default=None,
        alias="X-NEXUS-Admin-Token",
    ),
) -> dict[str, Any]:

    account = str(
        x_mt5_account or ""
    ).strip()

    if not account:
        raise HTTPException(
            status_code=400,
            detail="X-MT5-Account is required",
        )

    _admin_auth(
        account,
        x_admin_mode,
        x_admin_token,
    )

    symbol = str(
        req.symbol
    ).strip().upper()

    direction = str(
        req.direction
    ).strip().upper()

    try:
        result = await asyncio.to_thread(
            review_setup,
            symbol=symbol,
            direction=direction,
            trade_mode=req.trade_mode,
        )

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="AI setup reviewer unavailable",
        )

    return {
        "ok": True,
        "reviewer_version": REVIEWER_VERSION,
        "prompt_version": PROMPT_VERSION,
        "symbol": symbol,
        "direction": direction,
        "trade_mode": req.trade_mode,
        "account_number": account,
        "result": result,
        "advisory_only": True,
        "execution_gate": False,
    }
