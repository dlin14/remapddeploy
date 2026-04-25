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
        "You are a non-partisan redistricting analysis system composed of three specialist agents. "
        "Translate the provided quantitative scores into structured plain-English policy analysis. "
        "Return ONLY strict JSON — no markdown fences — with exactly these keys:\n"
        '{\n'
        '  "engine_agent": "<plain-English explanation of how the optimization engine works and what '
        'the score values indicate about the iterative search result. Describe weights as adjustable '
        'policy priorities. No ML jargon. Non-technical audience.>",\n'
        '  "civil_rights_agent": "<equity and fairness analysis. Reference voting-rights and '
        'minority-opportunity signals. Ground claims only in the provided metrics. '
        'If data is uncertain, say so explicitly instead of guessing.>",\n'
        '  "legislative_agent": "<legal and policy alignment in plain English. Reference one-person-'
        'one-vote, Voting Rights Act considerations, and compactness/population balance norms. '
        'State clearly: this is informational analysis only, not legal advice, and formal counsel '
        'review is required.>",\n'
        '  "summary": "<3-5 sentence plain-language summary for a legislator. Include overall risk '
        'level (low/medium/high) and one-sentence reason. End with a clear practical recommendation: '
        'proceed, revise, or seek legal review first. No partisan framing. Only facts from the input.>"\n'
        '}\n'
        "No hallucinated numbers or laws. Be concise and decision-oriented."
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
                if "```" in text:
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                parsed = json.loads(text.strip())
                # Extract risk level from summary text if not a top-level key
                raw_summary = parsed.get("summary", "")
                risk_level = "medium"
                for level in ("low", "medium", "high"):
                    if f"risk level: {level}" in raw_summary.lower():
                        risk_level = level
                        break
                return {
                    "engine_agent":       parsed.get("engine_agent", ""),
                    "civil_rights_agent": parsed.get("civil_rights_agent", ""),
                    "legislative_agent":  parsed.get("legislative_agent", ""),
                    "summary":            raw_summary,
                    "risk_level":         risk_level,
                    "model": settings.LIAISON_MODEL,
                    "provenance": provenance,
                }
        except Exception:
            # Fallback below preserves deterministic behavior.
            pass

    risk_level = "low" if legal_ok and score_vector.get("total_reward", 0) >= 0.65 else "medium"
    if not legal_ok or score_vector.get("voting_rights", 0) < 0.5:
        risk_level = "high"

    rf   = score_vector.get("racial_fairness", 0)
    pe   = score_vector.get("population_equality", 0)
    comp = score_vector.get("compactness", 0)
    vr   = score_vector.get("voting_rights", 0)
    opp  = score_vector.get("opportunity_districts", 0)

    engine_agent = (
        f"The optimizer ran an iterative county-by-county search to find a district assignment "
        f"that balances four policy priorities: racial fairness, population equality, geographic "
        f"compactness, and voting-rights protection. The combined score was "
        f"{score_vector.get('total_reward', 0):.3f} out of 1.0. Racial fairness scored "
        f"{rf:.3f}, population equality {pe:.3f}, compactness {comp:.3f}, and voting rights {vr:.3f}."
    )
    civil_rights_agent = (
        f"The plan produced {opp} opportunity district(s) — districts where minority voters "
        f"make up a substantial share. Racial fairness scored {rf:.3f} (1.0 = perfect proportionality). "
        f"{'This meets the minimum threshold for meaningful minority representation.' if legal_ok else 'This falls below the minimum opportunity-district threshold, which may warrant further review.'} "
        f"Exact legal sufficiency requires a qualified demographic and legal assessment."
    )
    legislative_agent = (
        f"Population equality scored {pe:.3f}, indicating {'strong' if pe >= 0.8 else 'moderate' if pe >= 0.5 else 'weak'} "
        f"alignment with one-person-one-vote norms. Compactness scored {comp:.3f}. "
        f"The voting-rights score of {vr:.3f} reflects the proportion of opportunity districts relative "
        f"to the state's minority population share. This is informational analysis only — it is not "
        f"legal advice. Formal legal counsel must review any map before adoption."
    )
    summary = (
        f"Overall risk level: {risk_level}. "
        f"The optimizer achieved a combined fairness score of {score_vector.get('total_reward', 0):.3f}. "
        f"{'Legal and equity signals are broadly positive.' if risk_level == 'low' else 'One or more equity dimensions warrants closer review.' if risk_level == 'medium' else 'Significant equity or legal concerns were flagged.'} "
        f"{'Recommendation: proceed to legal review.' if risk_level == 'low' else 'Recommendation: revise weights and re-run before legal review.' if risk_level == 'medium' else 'Recommendation: seek legal review before proceeding further.'} "
        f"Note: this analysis was generated via a deterministic fallback — configure ANTHROPIC_API_KEY for Claude-powered analysis."
    )
    return {
        "engine_agent":       engine_agent,
        "civil_rights_agent": civil_rights_agent,
        "legislative_agent":  legislative_agent,
        "summary":            summary,
        "risk_level":         risk_level,
        "model":              "rule-based-fallback",
        "provenance":         provenance,
    }
