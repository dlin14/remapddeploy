"""Policy copilot routes for non-technical legislator queries."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.routes.states import ABBR_TO_FIPS
from services.policy_copilot import PolicyCopilotService

router = APIRouter(prefix="/api/policy", tags=["policy"])
copilot = PolicyCopilotService()


class PolicyQueryPayload(BaseModel):
    state_abbr: str = Field(min_length=2, max_length=2)
    question: str = Field(min_length=6, max_length=2000)


@router.post("/query")
async def policy_query(payload: PolicyQueryPayload):
    state_abbr = payload.state_abbr.upper()
    state_fips = ABBR_TO_FIPS.get(state_abbr)
    if not state_fips:
        raise HTTPException(status_code=404, detail=f"Unknown state: {payload.state_abbr}")
    result = await copilot.run_query(
        state_fips=state_fips,
        state_abbr=state_abbr,
        question=payload.question,
    )
    return result
