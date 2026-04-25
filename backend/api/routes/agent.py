"""Agent/optimizer routes for the hackathon MVP."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

from api.routes.states import ABBR_TO_FIPS
from agents.social_impact_agent import SocialImpactAgent
from core.config import Settings
from models.agent.rl_agent import OptimizerParams, RLAgent
from services.optimizer_store import (
    get_all_plans,
    get_metrics,
    get_plan,
    request_cancel,
    set_latest_run,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])
liaison_agent = SocialImpactAgent()


class RunAgentPayload(BaseModel):
    state_abbr: str = Field(min_length=2, max_length=2)
    n_districts: int = Field(default=5, ge=1, le=53)
    n_steps: int = Field(default=700, ge=50, le=5000)
    racial_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    population_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    compactness_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    vra_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    ent_coef: float = Field(default=0.25, ge=0.0, le=1.0)


class LiaisonEvaluatePayload(BaseModel):
    state_abbr: str = Field(min_length=2, max_length=2)
    district_map: Optional[dict[str, int]] = None


@router.post("/run")
async def run_agent(payload: RunAgentPayload):
    state_abbr = payload.state_abbr.upper()
    state_fips = ABBR_TO_FIPS.get(state_abbr)
    if not state_fips:
        raise HTTPException(status_code=404, detail=f"Unknown state: {payload.state_abbr}")

    params = OptimizerParams(
        n_districts=payload.n_districts,
        iterations=min(2000, payload.n_steps),
        exploration_rate=payload.ent_coef,
        racial_weight=payload.racial_weight,
        population_weight=payload.population_weight,
        compactness_weight=payload.compactness_weight,
        vra_weight=payload.vra_weight,
    )
    try:
        result = RLAgent(state_fips=state_fips, params=params).run()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    set_latest_run(
        state_abbr=state_abbr,
        state_fips=state_fips,
        assignment=result["assignment"],
        district_metrics=result["district_metrics"],
        rewards=result["reward_history"],
        explorations=result["exploration_history"],
        score_breakdown=result["score_breakdown"],
        baseline_score_breakdown=result["baseline_score_breakdown"],
        baseline_reward=result["baseline_reward"],
        optimized_reward=result["best_reward"],
        baseline_label=result["baseline_label"],
        improvement=result["improvement"],
    )
    return {
        "status": "ok",
        "state_abbr": state_abbr,
        "state_fips": state_fips,
        "best_reward": result["best_reward"],
        "baseline_reward": result["baseline_reward"],
        "iterations": len(result["reward_history"]),
        "baseline_label": result["baseline_label"],
        "improvement": result["improvement"],
        "baseline_score_breakdown": result["baseline_score_breakdown"],
        "score_breakdown": result["score_breakdown"],
    }


@router.post("/stop")
async def stop_agent():
    """Signal the running optimizer to stop and save best-so-far."""
    request_cancel()
    return {"status": "stop_requested"}


@router.get("/metrics")
async def metrics():
    return get_metrics()


@router.get("/all-plans")
async def all_plans():
    """All cached district plans keyed by state_abbr — used by the home map."""
    return get_all_plans()


@router.get("/liaison/model")
async def liaison_model():
    # Fresh read so edits to backend/.env show up without relying on import-time cwd.
    cfg = Settings()
    return {
        "provider": "anthropic",
        "model": cfg.LIAISON_MODEL,
        "using_api_key": bool(cfg.ANTHROPIC_API_KEY),
    }


@router.post("/evaluate-liaison")
async def evaluate_liaison(payload: LiaisonEvaluatePayload):
    state_abbr = payload.state_abbr.upper()
    state_fips = ABBR_TO_FIPS.get(state_abbr)
    if not state_fips:
        raise HTTPException(status_code=404, detail=f"Unknown state: {payload.state_abbr}")
    district_map = payload.district_map
    if not district_map:
        plan = get_plan(state_abbr)
        if not plan or not plan.get("assignment"):
            raise HTTPException(
                status_code=400,
                detail="No district_map provided and no optimizer plan exists for this state yet.",
            )
        district_map = plan["assignment"]

    result = await liaison_agent.evaluate(state_fips=state_fips, district_map=district_map)
    return {
        "state_abbr": state_abbr,
        "state_fips": state_fips,
        "liaison_output": result.get("liaison_output"),
        "risk_level": result.get("risk_level"),
        "final_report": result.get("final_report"),
        "tool_events": result.get("tool_events", []),
    }


@router.post("/stream-evaluate-liaison")
async def stream_evaluate_liaison(payload: LiaisonEvaluatePayload):
    state_abbr = payload.state_abbr.upper()
    state_fips = ABBR_TO_FIPS.get(state_abbr)
    if not state_fips:
        raise HTTPException(status_code=404, detail=f"Unknown state: {payload.state_abbr}")
    district_map = payload.district_map
    if not district_map:
        plan = get_plan(state_abbr)
        if not plan or not plan.get("assignment"):
            raise HTTPException(
                status_code=400,
                detail="No district_map provided and no optimizer plan exists for this state yet.",
            )
        district_map = plan["assignment"]

    async def event_stream():
        yield "event: node_started\ndata: " + json.dumps({"node": "social_impact_graph"}) + "\n\n"
        stream_result = await liaison_agent.stream_evaluate(state_fips=state_fips, district_map=district_map)
        for event in stream_result.get("events", []):
            yield "event: graph_event\ndata: " + json.dumps(event, default=str) + "\n\n"
        final_state: dict[str, Any] = stream_result.get("final_state", {})
        yield "event: liaison_final\ndata: " + json.dumps(
            {
                "liaison_output": final_state.get("liaison_output"),
                "risk_level": final_state.get("risk_level"),
                "final_report": final_state.get("final_report"),
                "tool_events": final_state.get("tool_events", []),
            },
            default=str,
        ) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
