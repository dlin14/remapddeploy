"""Agent/optimizer routes for the hackathon MVP."""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

from api.routes.states import ABBR_TO_FIPS
from agents.social_impact_agent import SocialImpactAgent
from core.config import Settings, settings
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


class SuggestParamsPayload(BaseModel):
    state_abbr: str = Field(min_length=2, max_length=2)
    prompt: str = Field(min_length=1, max_length=600)
    current_params: dict[str, float] = Field(default_factory=dict)


@router.post("/suggest-params")
async def suggest_params(payload: SuggestParamsPayload):
    """Use Claude to translate a natural-language request into RL weight suggestions."""
    state_abbr = payload.state_abbr.upper()

    system = (
        "You are an expert redistricting optimization assistant helping policymakers "
        "understand how algorithmic parameters shape district maps. "
        "Translate the user's plain-English request into RL optimizer parameters. "
        "Return ONLY strict JSON — no markdown, no extra keys — with exactly these keys:\n"
        '{"racial_weight": <0-1>, "population_weight": <0-1>, '
        '"compactness_weight": <0-1>, "vra_weight": <0-1>, '
        '"n_steps": <200-2000>, "rationale": "<one concise sentence>", '
        '"explanation": "<2-3 sentences in plain English: what will the optimizer do differently, '
        'what might the resulting map look like, and what real-world fairness impact does this have>"}\n'
        "The four weights must sum to 1.0. Adjust them to reflect the user's stated priorities. "
        "Write the explanation for a general audience — no jargon, no math notation."
    )
    user_content = (
        f"State: {state_abbr}\n"
        f"Current parameters: {json.dumps(payload.current_params)}\n"
        f"User request: {payload.prompt}\n\n"
        "Return suggested RL optimizer parameters as JSON."
    )

    if settings.ANTHROPIC_API_KEY:
        try:
            body = {
                "model": settings.LIAISON_MODEL,
                "max_tokens": 350,
                "temperature": 0.2,
                "system": system,
                "messages": [{"role": "user", "content": user_content}],
            }
            headers = {
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages", json=body, headers=headers
                )
            if resp.status_code == 200:
                text = "".join(
                    c.get("text", "")
                    for c in resp.json().get("content", [])
                    if c.get("type") == "text"
                ).strip()
                # Strip optional markdown code fences
                if "```" in text:
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                parsed = json.loads(text.strip())

                def clamp(v: Any, lo: float, hi: float) -> float:
                    return max(lo, min(hi, float(v)))

                return {
                    "suggested_params": {
                        "racial_weight": clamp(parsed.get("racial_weight", 0.35), 0, 1),
                        "population_weight": clamp(parsed.get("population_weight", 0.30), 0, 1),
                        "compactness_weight": clamp(parsed.get("compactness_weight", 0.20), 0, 1),
                        "vra_weight": clamp(parsed.get("vra_weight", 0.15), 0, 1),
                        "n_steps": max(200, min(2000, int(parsed.get("n_steps", 700)))),
                    },
                    "rationale": str(parsed.get("rationale", "Parameters adjusted to reflect your priorities.")),
                    "explanation": str(parsed.get("explanation", "")),
                    "model": settings.LIAISON_MODEL,
                    "powered_by": "claude",
                }
        except Exception:
            pass  # fall through to rule-based

    # Rule-based fallback (no API key or parse error)
    p = payload.prompt.lower()
    if any(w in p for w in ["racial", "race", "minority", "diversity", "representation"]):
        r, pop, c, v = 0.50, 0.25, 0.15, 0.10
        note = "Boosted racial fairness weight to prioritize minority representation."
        explanation = (
            "The optimizer will work much harder to keep each district's racial composition "
            "proportional to the state's overall demographics. Expect districts that closely mirror "
            "the minority share of the population — this may produce slightly less geographically "
            "tidy shapes, but communities of color are more likely to have meaningful representation."
        )
    elif any(w in p for w in ["compact", "geographic", "shape", "contiguous"]):
        r, pop, c, v = 0.25, 0.25, 0.40, 0.10
        note = "Boosted compactness weight for more geographically coherent districts."
        explanation = (
            "The optimizer will strongly prefer districts that are geographically tight and "
            "contiguous — think fewer oddly-shaped, sprawling boundaries. The resulting map will "
            "look cleaner and be easier to explain to constituents, though racial and population "
            "balance may take a back seat."
        )
    elif any(w in p for w in ["vra", "voting", "rights", "opportunity", "section 2"]):
        r, pop, c, v = 0.20, 0.20, 0.10, 0.50
        note = "Boosted VRA weight to maximize minority opportunity districts."
        explanation = (
            "The optimizer will try to create as many 'opportunity districts' as possible — "
            "districts where minority voters have a realistic chance of electing their preferred "
            "candidate. This directly addresses Section 2 of the Voting Rights Act. Shape and "
            "pure population balance matter less here; what counts is giving underrepresented "
            "communities real political power."
        )
    elif any(w in p for w in ["population", "equal", "balance", "fair"]):
        r, pop, c, v = 0.25, 0.50, 0.15, 0.10
        note = "Boosted population equality for more balanced district sizes."
        explanation = (
            "Each district will be pushed toward having the same number of people, minimizing "
            "the advantage that comes from packing voters into unusually large or small districts. "
            "This is the 'one person, one vote' principle — every citizen's vote carries roughly "
            "equal weight regardless of which district they live in."
        )
    else:
        r, pop, c, v = 0.35, 0.30, 0.20, 0.15
        note = "No clear priority detected — using balanced default weights."
        explanation = (
            "These are the default balanced weights. The optimizer will consider racial fairness, "
            "population equality, geographic compactness, and voting rights roughly in proportion. "
            "Try being more specific — for example, 'prioritize minority voting rights' or "
            "'make districts as compact as possible'."
        )

    return {
        "suggested_params": {"racial_weight": r, "population_weight": pop, "compactness_weight": c, "vra_weight": v, "n_steps": 700},
        "rationale": note,
        "explanation": explanation,
        "model": "rule-based",
        "powered_by": "fallback",
    }


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
