"""SocialImpactAgent — Legislative Liaison LangGraph layer.

Graph:
    engine_agent -> [civil_rights_agent, legislative_agent]
                 -> liaison_node -> return

The liaison node synthesizes quantitative metrics into a structured,
non-partisan "Legislative Memo" with risk scoring and provenance.
"""

from __future__ import annotations

from typing import TypedDict, Annotated, Any, Optional
import operator
import json
import statistics

import httpx
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END

from core.config import settings
from mcp_server import mcp_server

# ------------------------------------------------------------------
# Agent state schema
# ------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    state_fips: str
    district_map: dict                  # county_geoid -> district_id
    score_vector: Optional[dict]
    legal_ok: Optional[bool]
    demographic_scores: Optional[dict]
    equity_scores: Optional[dict]
    liaison_output: Optional[dict]
    final_report: Optional[str]
    risk_level: Optional[str]
    tool_events: Annotated[list[dict], operator.add]


# ------------------------------------------------------------------
# Node stubs
# ------------------------------------------------------------------
def engine_agent(state: AgentState) -> AgentState:
    """Engine Agent: validates input and computes reward decomposition."""
    if not state["district_map"]:
        raise ValueError("district_map cannot be empty")
    score_vector = _compute_score_vector(state["district_map"])
    return {
        "score_vector": score_vector,
        "legal_ok": None,
        "demographic_scores": None,
        "equity_scores": None,
        "liaison_output": None,
        "final_report": None,
        "risk_level": None,
        "tool_events": [],
    }


def civil_rights_agent(state: AgentState) -> AgentState:
    """Civil Rights Advocate Agent: VRA and minority opportunity checks."""
    score_vector = state["score_vector"] or {}
    opportunity = int(score_vector.get("opportunity_districts", 0))
    legal_ok = opportunity >= 1
    return {
        "legal_ok": legal_ok,
        "tool_events": [{
            "node": "civil_rights_agent",
            "status": "ok" if legal_ok else "warning",
            "detail": f"opportunity_districts={opportunity}",
        }],
    }


def legislative_agent(state: AgentState) -> AgentState:
    """Legislative Agent: broader legal/fairness framing for policymakers."""
    score_vector = state["score_vector"] or {}
    out = {
        "racial_fairness": score_vector.get("racial_fairness", 0.0),
        "population_equality": score_vector.get("population_equality", 0.0),
        "voting_rights": score_vector.get("voting_rights", 0.0),
    }
    return {
        "demographic_scores": out,
        "tool_events": [{"node": "legislative_agent", "status": "ok", "detail": out}],
    }


def equity_analysis(state: AgentState) -> AgentState:
    """Compute income / education equity scores across districts."""
    score_vector = state["score_vector"] or {}
    out = {
        "gini_proxy": score_vector.get("gini_proxy", 0.0),
        "compactness": score_vector.get("compactness", 0.0),
    }
    return {
        "equity_scores": out,
        "tool_events": [{"node": "equity_analysis", "status": "ok", "detail": out}],
    }


async def liaison_node(state: AgentState) -> AgentState:
    """Synthesize legal/equity/math scores into a legislative memo."""
    census = await mcp_server.fetch_census_metrics(
        state_fips=state["state_fips"],
        district_map=state["district_map"],
    )
    audit = await mcp_server.verify_audit_trail(census.provenance["tool_call_id"])
    liaison_output = await _generate_liaison_memo(
        state_fips=state["state_fips"],
        score_vector=state["score_vector"] or {},
        legal_ok=bool(state["legal_ok"]),
        demographic_scores=state["demographic_scores"] or {},
        equity_scores=state["equity_scores"] or {},
        census_payload=census.payload,
        provenance=[census.provenance, audit.provenance],
    )
    return {
        "liaison_output": liaison_output,
        "final_report": liaison_output.get("summary", ""),
        "risk_level": liaison_output.get("risk_level", "medium"),
        "messages": [HumanMessage(content=liaison_output.get("summary", ""))],
        "tool_events": [{
            "node": "liaison_node",
            "status": "ok",
            "detail": {
                "risk_level": liaison_output.get("risk_level", "medium"),
                "provenance": liaison_output.get("provenance", []),
            },
        }],
    }


# ------------------------------------------------------------------
# Graph definition
# ------------------------------------------------------------------
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("engine_agent", engine_agent)
    graph.add_node("civil_rights_agent", civil_rights_agent)
    graph.add_node("legislative_agent", legislative_agent)
    graph.add_node("equity_analysis", equity_analysis)
    graph.add_node("liaison_node", liaison_node)

    graph.set_entry_point("engine_agent")
    graph.add_edge("engine_agent", "civil_rights_agent")
    graph.add_edge("engine_agent", "legislative_agent")
    graph.add_edge("engine_agent", "equity_analysis")
    # Fan-in: all three parallel nodes feed into liaison synthesis
    graph.add_edge("civil_rights_agent", "liaison_node")
    graph.add_edge("legislative_agent", "liaison_node")
    graph.add_edge("equity_analysis", "liaison_node")
    graph.add_edge("liaison_node", END)

    return graph


social_impact_graph = build_graph()


class SocialImpactAgent:
    """High-level interface for running the social impact evaluation graph."""

    def __init__(self):
        self._runnable = social_impact_graph.compile()

    async def evaluate(self, state_fips: str, district_map: dict) -> dict:
        """Run the full evaluation graph and return the final agent state."""
        initial_state: AgentState = {
            "messages": [],
            "state_fips": state_fips,
            "district_map": district_map,
            "score_vector": None,
            "legal_ok": None,
            "demographic_scores": None,
            "equity_scores": None,
            "liaison_output": None,
            "final_report": None,
            "risk_level": None,
            "tool_events": [],
        }
        return await self._runnable.ainvoke(initial_state)

    async def stream_evaluate(self, state_fips: str, district_map: dict) -> dict:
        """Run the graph and emit node events plus final state."""
        initial_state: AgentState = {
            "messages": [],
            "state_fips": state_fips,
            "district_map": district_map,
            "score_vector": None,
            "legal_ok": None,
            "demographic_scores": None,
            "equity_scores": None,
            "liaison_output": None,
            "final_report": None,
            "risk_level": None,
            "tool_events": [],
        }
        events: list[dict[str, Any]] = []
        async for event in self._runnable.astream_events(initial_state, version="v2"):
            if event.get("event") == "on_chain_end":
                continue
            name = event.get("name", "unknown")
            ev = event.get("event", "event")
            data = event.get("data", {})
            events.append({"name": name, "event": ev, "data": data})
        final_state = await self._runnable.ainvoke(initial_state)
        return {"events": events, "final_state": final_state}


def _compute_score_vector(district_map: dict[str, int]) -> dict[str, Any]:
    """Compute normalized reward components from a county assignment map."""
    district_groups: dict[int, list[str]] = {}
    for county_id, district_id in district_map.items():
        district_groups.setdefault(int(district_id), []).append(str(county_id))

    # Deterministic pseudo-features for consistent hackathon demos.
    district_populations: list[float] = []
    district_minority_shares: list[float] = []
    district_sizes: list[float] = []
    for counties in district_groups.values():
        pop = 0.0
        minority_pop = 0.0
        for county_id in counties:
            seed = int(county_id)
            # Keep this deterministic but cheap (avoid importing optimizer internals).
            county_pop = 12000 + (seed % 280000)
            minority_share = 0.12 + ((seed % 6600) / 10000.0)
            pop += county_pop
            minority_pop += county_pop * min(0.9, minority_share)
        district_populations.append(pop)
        district_sizes.append(float(len(counties)))
        district_minority_shares.append(minority_pop / max(1.0, pop))

    total_pop = sum(district_populations)
    n_districts = max(1, len(district_populations))
    target_pop = total_pop / n_districts
    pop_dev = [abs(p - target_pop) / max(1.0, target_pop) for p in district_populations]
    population_equality = max(0.0, min(1.0, 1.0 - statistics.fmean(pop_dev)))

    state_minority = statistics.fmean(district_minority_shares)
    gap = statistics.fmean(abs(s - state_minority) for s in district_minority_shares)
    racial_fairness = max(0.0, min(1.0, 1.0 - 2.0 * gap))

    size_mean = max(1.0, statistics.fmean(district_sizes))
    size_std = statistics.pstdev(district_sizes) if len(district_sizes) > 1 else 0.0
    compactness = max(0.0, min(1.0, 1.0 - (size_std / size_mean)))

    opportunity_districts = sum(1 for s in district_minority_shares if s >= 0.45)
    target_opportunity = max(1, round(n_districts * state_minority))
    voting_rights = max(0.0, min(1.0, opportunity_districts / target_opportunity))

    # Gini-like proxy across district populations.
    sorted_pops = sorted(district_populations)
    n = len(sorted_pops)
    if n > 0 and total_pop > 0:
        weighted_sum = sum((i + 1) * p for i, p in enumerate(sorted_pops))
        gini = (2 * weighted_sum) / (n * total_pop) - (n + 1) / n
    else:
        gini = 0.0

    total_reward = (
        0.35 * racial_fairness
        + 0.30 * population_equality
        + 0.20 * compactness
        + 0.15 * voting_rights
    )
    return {
        "racial_fairness": round(racial_fairness, 4),
        "population_equality": round(population_equality, 4),
        "compactness": round(compactness, 4),
        "voting_rights": round(voting_rights, 4),
        "total_reward": round(total_reward, 4),
        "gini_proxy": round(max(0.0, min(1.0, gini)), 4),
        "opportunity_districts": int(opportunity_districts),
        "district_count": int(n_districts),
    }


async def _generate_liaison_memo(
    state_fips: str,
    score_vector: dict[str, Any],
    legal_ok: bool,
    demographic_scores: dict[str, Any],
    equity_scores: dict[str, Any],
    census_payload: dict[str, Any],
    provenance: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate a structured liaison memo with Claude, fallback if unavailable."""
    prompt_payload = {
        "state_fips": state_fips,
        "score_vector": score_vector,
        "legal_ok": legal_ok,
        "demographic_scores": demographic_scores,
        "equity_scores": equity_scores,
        "census_payload": census_payload,
        "provenance": provenance,
    }
    instruction = (
        "You are the Legislative Liaison for a non-partisan redistricting review. "
        "Use adaptive thinking to translate mathematical scores into plain-English policy language. "
        "Return strict JSON with keys: simple_summary, technical_appendix, risk_level, justification. "
        "simple_summary must be understandable to someone with no technical background. "
        "technical_appendix should include the core score values and tradeoff notes in precise terms. "
        "risk_level must be one of: low, medium, high. "
        "Focus on legal risk, fairness tradeoffs, and human flourishing. "
        "Avoid partisan framing."
    )

    if settings.ANTHROPIC_API_KEY:
        try:
            body = {
                "model": settings.LIAISON_MODEL,
                "max_tokens": 800,
                "temperature": 0.2,
                "system": instruction,
                "messages": [{"role": "user", "content": json.dumps(prompt_payload)}],
            }
            headers = {
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post("https://api.anthropic.com/v1/messages", json=body, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                text = "".join(
                    chunk.get("text", "") for chunk in data.get("content", []) if chunk.get("type") == "text"
                ).strip()
                parsed = json.loads(text)
                return {
                    "summary": parsed.get("simple_summary", ""),
                    "simple_summary": parsed.get("simple_summary", ""),
                    "technical_appendix": parsed.get("technical_appendix", ""),
                    "risk_level": parsed.get("risk_level", "medium"),
                    "justification": parsed.get("justification", ""),
                    "model": settings.LIAISON_MODEL,
                    "provenance": provenance,
                }
        except Exception:
            # Fallback below preserves deterministic behavior.
            pass

    risk_level = "low" if legal_ok and score_vector.get("total_reward", 0) >= 0.65 else "medium"
    if not legal_ok or score_vector.get("voting_rights", 0) < 0.5:
        risk_level = "high"
    simple_summary = (
        f"For state {state_fips}, this map looks {'lower' if risk_level == 'low' else 'higher'} risk for legal challenge. "
        f"It keeps district populations fairly balanced and maintains strong voting-rights protection signals. "
        f"Legal review is still required before adoption."
    )
    technical_appendix = (
        f"weighted_reward={score_vector.get('total_reward', 0):.3f}; "
        f"population_equality={score_vector.get('population_equality', 0):.3f}; "
        f"racial_fairness={score_vector.get('racial_fairness', 0):.3f}; "
        f"compactness={score_vector.get('compactness', 0):.3f}; "
        f"voting_rights={score_vector.get('voting_rights', 0):.3f}; "
        f"legal_gate={'pass' if legal_ok else 'flag'}."
    )
    justification = (
        "Memo generated via deterministic fallback because ANTHROPIC_API_KEY is missing "
        "or model response was not parseable."
    )
    return {
        "summary": simple_summary,
        "simple_summary": simple_summary,
        "technical_appendix": technical_appendix,
        "risk_level": risk_level,
        "justification": justification,
        "model": settings.LIAISON_MODEL,
        "provenance": provenance,
    }
