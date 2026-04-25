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
    remove_plan,
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

    SECTION_SYSTEM = (
        "You are a non-partisan redistricting analysis system composed of three specialist agents. "
        "Given a user request and current optimizer parameters, return ONLY strict JSON — no markdown fences — "
        "with exactly these keys:\n"
        '{\n'
        '  "racial_weight": <float 0-1>,\n'
        '  "population_weight": <float 0-1>,\n'
        '  "compactness_weight": <float 0-1>,\n'
        '  "vra_weight": <float 0-1>,\n'
        '  "n_steps": <int 200-2000>,\n'
        '  "engine_agent": "<plain-English explanation of how the optimization engine works and what '
        'the suggested weight changes will cause the iterative search to do differently. Describe '
        'weights as adjustable policy priorities. No ML jargon. Non-technical audience.>",\n'
        '  "civil_rights_agent": "<equity and fairness analysis of the suggested plan priorities. '
        'Reference voting-rights and minority-opportunity signals. Ground claims only in the provided '
        'metrics. If data is uncertain, say so explicitly instead of guessing.>",\n'
        '  "legislative_agent": "<legal and policy alignment in plain English. Reference one-person-'
        'one-vote, Voting Rights Act considerations, and compactness/population balance norms. '
        'State clearly: this is informational analysis only, not legal advice, and formal counsel '
        'review is required.>",\n'
        '  "summary": "<3-5 sentence plain-language summary for a legislator. Include overall risk '
        'level (low/medium/high) and one-sentence reason. End with a clear practical recommendation: '
        'proceed, revise, or seek legal review first. No partisan framing. Only facts from the input.>"\n'
        '}\n'
        "The four weights must sum to 1.0. No hallucinated numbers or laws. Be concise and decision-oriented."
    )
    user_content = (
        f"State: {state_abbr}\n"
        f"Current optimizer parameters: {json.dumps(payload.current_params)}\n"
        f"User request: {payload.prompt}\n\n"
        "Return the four-section analysis and suggested parameters as JSON."
    )

    if settings.ANTHROPIC_API_KEY:
        try:
            body = {
                "model": settings.LIAISON_MODEL,
                "max_tokens": 900,
                "temperature": 0.2,
                "system": SECTION_SYSTEM,
                "messages": [{"role": "user", "content": user_content}],
            }
            headers = {
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages", json=body, headers=headers
                )
            if resp.status_code == 200:
                text = "".join(
                    c.get("text", "")
                    for c in resp.json().get("content", [])
                    if c.get("type") == "text"
                ).strip()
                if "```" in text:
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                parsed = json.loads(text.strip())

                def clamp(v: Any, lo: float, hi: float) -> float:
                    return max(lo, min(hi, float(v)))

                return {
                    "suggested_params": {
                        "racial_weight":     clamp(parsed.get("racial_weight", 0.35), 0, 1),
                        "population_weight": clamp(parsed.get("population_weight", 0.30), 0, 1),
                        "compactness_weight":clamp(parsed.get("compactness_weight", 0.20), 0, 1),
                        "vra_weight":        clamp(parsed.get("vra_weight", 0.15), 0, 1),
                        "n_steps":           max(200, min(2000, int(parsed.get("n_steps", 700)))),
                    },
                    "engine_agent":       str(parsed.get("engine_agent", "")),
                    "civil_rights_agent": str(parsed.get("civil_rights_agent", "")),
                    "legislative_agent":  str(parsed.get("legislative_agent", "")),
                    "summary":            str(parsed.get("summary", "")),
                    "model": settings.LIAISON_MODEL,
                    "powered_by": "claude",
                }
        except Exception:
            pass  # fall through to rule-based

    # ── Rule-based fallback ───────────────────────────────────────────────────
    p = payload.prompt.lower()

    if any(w in p for w in ["racial", "race", "minority", "diversity", "representation"]):
        r, pop, c, v = 0.50, 0.25, 0.15, 0.10
        engine = (
            "The optimizer runs an iterative county-by-county search. With racial fairness set as "
            "the top priority (weight 0.50), it will strongly favor arrangements where each district "
            "reflects the state's overall racial composition. The other three priorities — population "
            "balance, geographic shape, and voting-rights protection — are reduced to make room."
        )
        civil = (
            "Elevating the racial fairness priority increases the likelihood that minority communities "
            "are proportionally represented across districts. This reduces the risk of cracking or "
            "packing, where minority voters are deliberately diluted or over-concentrated. Exact equity "
            "outcomes depend on the state's demographic distribution, which the optimizer uses as its target."
        )
        leg = (
            "A higher racial fairness weight aligns with principles underlying Section 2 of the Voting "
            "Rights Act, which prohibits maps that dilute minority voting power. Population balance "
            "(one-person-one-vote) remains present but is weighted lower. This is informational analysis "
            "only — it is not legal advice. Formal legal counsel must review any map before adoption."
        )
        summary = (
            "This configuration prioritizes racial fairness above other criteria. Risk level: medium — "
            "while the intent aligns with equity principles, lower compactness weight may draw scrutiny "
            "on geographic grounds. Recommendation: proceed with optimization, then have legal counsel "
            "review the output map for VRA compliance before any official use."
        )
    elif any(w in p for w in ["compact", "geographic", "shape", "contiguous"]):
        r, pop, c, v = 0.25, 0.25, 0.40, 0.10
        engine = (
            "With compactness set as the leading priority (weight 0.40), the optimizer will favor "
            "county groupings that are geographically tight and contiguous. The search penalizes "
            "sprawling, irregular arrangements. Racial fairness and population equality are still "
            "present but carry less influence over which solutions are accepted."
        )
        civil = (
            "Prioritizing compactness can produce cleaner-looking districts, but may reduce the "
            "optimizer's ability to group minority communities that are geographically dispersed. "
            "If the state has spatially concentrated minority populations, compactness and equity "
            "goals may be compatible. If not, equity outcomes could decline. Specific impact depends "
            "on the state's demographic geography, which cannot be assessed without census-level data."
        )
        leg = (
            "Compactness is a recognized redistricting criterion in many state constitutions and "
            "has been cited in court challenges. However, compactness alone is not a legal requirement "
            "under federal law, and overly compact maps can still violate the Voting Rights Act if they "
            "dilute minority representation. This is informational analysis only — not legal advice. "
            "Formal counsel review is required."
        )
        summary = (
            "This configuration emphasizes geographic compactness and tidiness of district shapes. "
            "Risk level: low for gerrymandering challenges based on shape; medium if minority "
            "communities are geographically dispersed. Recommendation: proceed with optimization, "
            "then verify equity metrics in the output before finalizing."
        )
    elif any(w in p for w in ["vra", "voting", "rights", "opportunity", "section 2"]):
        r, pop, c, v = 0.20, 0.20, 0.10, 0.50
        engine = (
            "The voting-rights priority (weight 0.50) now dominates the optimizer's scoring. The "
            "iterative search will strongly favor maps that maximize the number of districts where "
            "minority voters make up a substantial share — often called opportunity districts. "
            "Geographic compactness is reduced significantly to allow this."
        )
        civil = (
            "Maximizing the voting-rights weight directly targets the creation of minority opportunity "
            "districts, which is the primary mechanism for VRA Section 2 compliance. The optimizer "
            "defines an opportunity district as one where minority share reaches or exceeds 45%. "
            "Actual legal sufficiency depends on state-specific demographic thresholds and must be "
            "assessed by qualified legal and demographic experts."
        )
        leg = (
            "This configuration is explicitly oriented toward Section 2 of the Voting Rights Act, "
            "which requires that minority communities have a meaningful opportunity to elect "
            "representatives of their choice. One-person-one-vote remains present (weight 0.20) but "
            "is secondary. This is informational analysis only — it is not legal advice. Compliance "
            "with the VRA requires formal legal and demographic review."
        )
        summary = (
            "This configuration aggressively prioritizes voting-rights protections and minority "
            "opportunity districts. Risk level: low for VRA dilution claims; medium for compactness "
            "challenges due to the reduced shape priority. Recommendation: proceed with optimization, "
            "then seek legal review focused on VRA compliance and compactness before any official use."
        )
    elif any(w in p for w in ["population", "equal", "balance", "fair"]):
        r, pop, c, v = 0.25, 0.50, 0.15, 0.10
        engine = (
            "Population equality is now the dominant optimizer priority (weight 0.50). The iterative "
            "search will strongly favor county arrangements where every district contains roughly the "
            "same number of people. This is the computational expression of the one-person-one-vote "
            "principle. Racial and geographic priorities are reduced to support this goal."
        )
        civil = (
            "High population equality reduces the structural advantage that over- or under-populated "
            "districts give to particular voter groups. However, population balance alone does not "
            "guarantee minority representation — a perfectly population-equal map can still dilute "
            "minority voting power if communities are distributed unfavorably. The optimizer's racial "
            "fairness weight (0.25) provides some protection, but equity outcomes should be verified "
            "in the output."
        )
        leg = (
            "Population equality is the foundational requirement under the Supreme Court's one-person-"
            "one-vote doctrine, established in Reynolds v. Sims (1964). Congressional districts must "
            "be as equal in population as practicable. This configuration directly targets that "
            "standard. However, population equality is necessary but not sufficient — VRA and racial "
            "fairness considerations must also be satisfied. This is informational analysis only, not "
            "legal advice. Formal counsel review is required."
        )
        summary = (
            "This configuration prioritizes equal population across all districts above other criteria. "
            "Risk level: low for one-person-one-vote challenges; medium if racial fairness metrics "
            "decline as a result. Recommendation: proceed with optimization, then review the output "
            "map for equity and VRA compliance before any official use."
        )
    else:
        r, pop, c, v = 0.35, 0.30, 0.20, 0.15
        engine = (
            "The optimizer uses a balanced default configuration, treating racial fairness (0.35), "
            "population equality (0.30), geographic compactness (0.20), and voting-rights protection "
            "(0.15) as its four policy priorities. The iterative search explores county-to-district "
            "assignments and accepts changes that improve the combined score. Try specifying a clearer "
            "priority — for example, 'prioritize minority voting rights' or 'focus on compactness'."
        )
        civil = (
            "With balanced weights, the optimizer will not strongly favor or disadvantage any single "
            "equity dimension. Minority representation signals (voting-rights weight 0.15) are present "
            "but not dominant. If equity is a primary concern for this state, consider increasing the "
            "racial fairness or VRA weights explicitly."
        )
        leg = (
            "The balanced default addresses multiple legal redistricting criteria simultaneously: "
            "population equality (one-person-one-vote), racial fairness (VRA alignment), and "
            "compactness (a common state-level criterion). No single criterion dominates. This is "
            "informational analysis only — it is not legal advice. Formal counsel review is required "
            "before any map is used officially."
        )
        summary = (
            "This is the balanced default configuration. Risk level: medium — no single legal "
            "criterion is neglected, but none is strongly optimized either. Recommendation: specify "
            "a clearer policy priority before running the optimizer to get more targeted results, "
            "then have legal counsel review the output map."
        )

    return {
        "suggested_params": {"racial_weight": r, "population_weight": pop, "compactness_weight": c, "vra_weight": v, "n_steps": 700},
        "engine_agent":       engine,
        "civil_rights_agent": civil,
        "legislative_agent":  leg,
        "summary":            summary,
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


@router.delete("/plans/{state_abbr}")
async def delete_plan(state_abbr: str):
    """Remove a cached optimizer plan so the state resets to real district boundaries."""
    existed = remove_plan(state_abbr)
    if not existed:
        raise HTTPException(status_code=404, detail=f"No plan found for {state_abbr.upper()}")
    return {"status": "deleted", "state_abbr": state_abbr.upper()}


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
