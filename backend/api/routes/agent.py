"""Agent/optimizer routes for the hackathon MVP."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.routes.states import ABBR_TO_FIPS
from models.agent.rl_agent import OptimizerParams, RLAgent
from services.optimizer_store import get_metrics, get_all_plans, set_latest_run, request_cancel

router = APIRouter(prefix="/api/agent", tags=["agent"])


class RunAgentPayload(BaseModel):
    state_abbr: str = Field(min_length=2, max_length=2)
    n_districts: int = Field(default=5, ge=1, le=53)
    n_steps: int = Field(default=700, ge=50, le=5000)
    racial_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    population_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    compactness_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    vra_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    ent_coef: float = Field(default=0.25, ge=0.0, le=1.0)


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
