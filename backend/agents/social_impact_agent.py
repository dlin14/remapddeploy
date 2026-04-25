"""
SocialImpactAgent — LangGraph agentic reasoning layer.

This agent wraps the RL policy with a chain-of-thought reasoning loop
that evaluates proposed district maps against legal, demographic, and
social equity criteria before returning a scored recommendation.

Architecture (LangGraph StateGraph):
    evaluate_proposal → [legal_check, demographic_analysis, equity_analysis]
                      → synthesize_report → return

TODO:
    - Define AgentState TypedDict with map proposal, scores, reasoning trace
    - Implement legal_check node: Voting Rights Act § 2 compliance check
    - Implement demographic_analysis node: racial composition per district
    - Implement equity_analysis node: Gini coefficient on income distribution
    - Implement synthesize_report node: LLM-generated plain-English summary
    - Wire tool calls: GovDataService, StateEnvironment reward function
    - Add human-in-the-loop interrupt for edge cases
"""

from __future__ import annotations

from typing import TypedDict, Annotated
import operator

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END


# ------------------------------------------------------------------
# Agent state schema
# ------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    state_fips: str
    district_map: dict                  # block_geoid → district_id
    legal_ok: bool | None
    demographic_scores: dict | None
    equity_scores: dict | None
    final_report: str | None


# ------------------------------------------------------------------
# Node stubs
# ------------------------------------------------------------------
def evaluate_proposal(state: AgentState) -> AgentState:
    """Entry node — validates input and initialises sub-scores."""
    # TODO: validate district_map structure, check all blocks assigned
    return {**state, "legal_ok": None, "demographic_scores": None, "equity_scores": None}


def legal_check(state: AgentState) -> AgentState:
    """VRA § 2 compliance: check minority opportunity districts."""
    # TODO: query GovDataService for CVAP data, run Gingles factors analysis
    return {**state, "legal_ok": True}


def demographic_analysis(state: AgentState) -> AgentState:
    """Compute racial composition statistics per district."""
    # TODO: join district_map with block_demographics from DuckDB
    return {**state, "demographic_scores": {"placeholder": 0.0}}


def equity_analysis(state: AgentState) -> AgentState:
    """Compute income / education equity scores across districts."""
    # TODO: ACS data → Gini coefficient per district pair
    return {**state, "equity_scores": {"gini": 0.0}}


def synthesize_report(state: AgentState) -> AgentState:
    """LLM-generated plain-English redistricting impact summary."""
    # TODO: call Claude / GPT-4o with structured scores → markdown report
    report = (
        f"[PLACEHOLDER] District map for state {state['state_fips']} analysed. "
        "Full LLM synthesis coming soon."
    )
    return {**state, "final_report": report, "messages": [HumanMessage(content=report)]}


# ------------------------------------------------------------------
# Graph definition
# ------------------------------------------------------------------
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("evaluate_proposal", evaluate_proposal)
    graph.add_node("legal_check", legal_check)
    graph.add_node("demographic_analysis", demographic_analysis)
    graph.add_node("equity_analysis", equity_analysis)
    graph.add_node("synthesize_report", synthesize_report)

    graph.set_entry_point("evaluate_proposal")
    graph.add_edge("evaluate_proposal", "legal_check")
    graph.add_edge("evaluate_proposal", "demographic_analysis")
    graph.add_edge("evaluate_proposal", "equity_analysis")
    # Fan-in: all three parallel nodes feed into synthesis
    graph.add_edge("legal_check", "synthesize_report")
    graph.add_edge("demographic_analysis", "synthesize_report")
    graph.add_edge("equity_analysis", "synthesize_report")
    graph.add_edge("synthesize_report", END)

    return graph


social_impact_graph = build_graph()


class SocialImpactAgent:
    """High-level interface for running the social impact evaluation graph."""

    def __init__(self):
        self._runnable = social_impact_graph.compile()

    def evaluate(self, state_fips: str, district_map: dict) -> dict:
        """Run the full evaluation graph and return the final agent state."""
        initial_state: AgentState = {
            "messages": [],
            "state_fips": state_fips,
            "district_map": district_map,
            "legal_ok": None,
            "demographic_scores": None,
            "equity_scores": None,
            "final_report": None,
        }
        return self._runnable.invoke(initial_state)
