"""MCP tool endpoints for Legislative Liaison."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.routes.states import ABBR_TO_FIPS
from mcp_server import mcp_server

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class CensusMetricsPayload(BaseModel):
    state_abbr: str = Field(min_length=2, max_length=2)
    district_map: dict[str, int]
    year: int = Field(default=2022, ge=2010, le=2030)


class VerifyAuditPayload(BaseModel):
    tool_call_id: str = Field(min_length=4)


@router.post("/tools/fetch_census_metrics")
async def fetch_census_metrics(payload: CensusMetricsPayload):
    state_abbr = payload.state_abbr.upper()
    state_fips = ABBR_TO_FIPS.get(state_abbr)
    if not state_fips:
        raise HTTPException(status_code=404, detail=f"Unknown state: {payload.state_abbr}")
    result = await mcp_server.fetch_census_metrics(
        state_fips=state_fips,
        district_map=payload.district_map,
        year=payload.year,
    )
    return {
        "tool_name": result.tool_name,
        "success": result.success,
        "payload": result.payload,
        "provenance": result.provenance,
    }


@router.post("/tools/verify_audit_trail")
async def verify_audit_trail(payload: VerifyAuditPayload):
    result = await mcp_server.verify_audit_trail(tool_call_id=payload.tool_call_id)
    return {
        "tool_name": result.tool_name,
        "success": result.success,
        "payload": result.payload,
        "provenance": result.provenance,
    }
