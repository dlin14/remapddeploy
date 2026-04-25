"""Policy copilot backend service.

Translates legislator goals into candidate optimizer configurations,
evaluates options, and returns ranked recommendations with legal-risk
summaries and provenance metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any

from agents.social_impact_agent import SocialImpactAgent
from mcp_server import mcp_server
from models.agent.rl_agent import OptimizerParams, RLAgent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CandidateConfig:
    name: str
    rationale: str
    params: OptimizerParams
    method: str = "search_sa"


class PolicyCopilotService:
    """Runs a small candidate sweep and returns policy recommendations."""

    def __init__(self):
        self._liaison = SocialImpactAgent()

    async def run_query(self, state_fips: str, state_abbr: str, question: str) -> dict[str, Any]:
        goals = self._parse_goals(question)
        candidates = self._build_candidates(goals)
        trials: list[dict[str, Any]] = []

        for cfg in candidates:
            result = RLAgent(state_fips=state_fips, params=cfg.params).run()
            legal = self._legal_risk_assessment(result)
            policy_score = self._policy_utility(result=result, legal=legal, goals=goals)
            census_tool = await mcp_server.fetch_census_metrics(
                state_fips=state_fips,
                district_map=result["assignment"],
            )
            trials.append(
                {
                    "candidate_name": cfg.name,
                    "method": cfg.method,
                    "rationale": cfg.rationale,
                    "params": {
                        "n_districts": cfg.params.n_districts,
                        "iterations": cfg.params.iterations,
                        "exploration_rate": cfg.params.exploration_rate,
                        "weights": {
                            "racial_weight": cfg.params.racial_weight,
                            "population_weight": cfg.params.population_weight,
                            "compactness_weight": cfg.params.compactness_weight,
                            "vra_weight": cfg.params.vra_weight,
                        },
                    },
                    "best_reward": result["best_reward"],
                    "baseline_reward": result["baseline_reward"],
                    "improvement": result["improvement"],
                    "score_breakdown": result["score_breakdown"],
                    "district_metrics": result["district_metrics"],
                    "legal_risk": legal,
                    "policy_utility": round(policy_score, 4),
                    "provenance": [census_tool.provenance],
                    "assignment": result["assignment"],
                }
            )

        ranked = sorted(trials, key=lambda t: t["policy_utility"], reverse=True)
        top = ranked[0]
        liaison = await self._liaison.evaluate(
            state_fips=state_fips,
            district_map=top["assignment"],
        )

        alternatives = [
            self._without_assignment(item) for item in ranked[1:3]
        ]
        recommended = self._without_assignment(top)
        response = {
            "state_abbr": state_abbr,
            "state_fips": state_fips,
            "question": question,
            "interpreted_goals": goals,
            "plain_language_summary": {
                "recommendation_in_one_line": self._one_line_recommendation(recommended),
                "why_this_option": self._why_this_option(recommended),
                "what_to_watch": recommended.get("legal_risk", {}).get("flags", []),
            },
            "agent_breakdown": self._agent_breakdown(recommended, liaison),
            "recommendation": recommended,
            "alternatives": alternatives,
            "liaison_summary": {
                "summary": liaison.get("final_report"),
                "simple_summary": (liaison.get("liaison_output") or {}).get("simple_summary", liaison.get("final_report")),
                "technical_appendix": (liaison.get("liaison_output") or {}).get("technical_appendix", ""),
                "risk_level": liaison.get("risk_level"),
                "justification": (liaison.get("liaison_output") or {}).get("justification", ""),
                "model": (liaison.get("liaison_output") or {}).get("model"),
            },
            "formatted_output": self._formatted_output(recommended, liaison),
            "guardrails": {
                "advisory_only": True,
                "requires_human_legal_review": True,
                "non_partisan_intent": True,
            },
            "provenance": {
                "generated_at": _utc_now(),
                "trace_id": self._trace_id(state_fips, question),
            },
        }
        return response

    def _parse_goals(self, question: str) -> dict[str, Any]:
        q = question.lower()
        goals = {
            "prioritize_legal_safety": any(k in q for k in ("legal", "vra", "safe", "risk")),
            "prioritize_fairness": any(k in q for k in ("fair", "equity", "justice", "racial")),
            "prioritize_compactness": any(k in q for k in ("compact", "shape", "gerrymander")),
            "prioritize_speed": any(k in q for k in ("fast", "quick", "seconds", "speed")),
            "prefer_rl_model": any(k in q for k in ("ppo", "sac", "a2c", "rl model")),
        }
        if not any(goals.values()):
            goals["prioritize_fairness"] = True
            goals["prioritize_legal_safety"] = True
        return goals

    def _build_candidates(self, goals: dict[str, Any]) -> list[CandidateConfig]:
        base = OptimizerParams(n_districts=6, iterations=700, exploration_rate=0.22)
        fair = OptimizerParams(
            n_districts=6,
            iterations=850,
            exploration_rate=0.20,
            racial_weight=0.42,
            population_weight=0.28,
            compactness_weight=0.15,
            vra_weight=0.15,
        )
        legal = OptimizerParams(
            n_districts=6,
            iterations=900,
            exploration_rate=0.18,
            racial_weight=0.25,
            population_weight=0.25,
            compactness_weight=0.20,
            vra_weight=0.30,
        )
        compact = OptimizerParams(
            n_districts=6,
            iterations=750,
            exploration_rate=0.20,
            racial_weight=0.22,
            population_weight=0.23,
            compactness_weight=0.40,
            vra_weight=0.15,
        )
        fast = OptimizerParams(
            n_districts=6,
            iterations=450,
            exploration_rate=0.25,
            racial_weight=0.30,
            population_weight=0.30,
            compactness_weight=0.20,
            vra_weight=0.20,
        )
        candidates = [
            CandidateConfig("balanced_baseline", "Balanced tradeoff profile.", base),
            CandidateConfig("equity_heavy", "Increases racial fairness emphasis.", fair),
            CandidateConfig("legal_safety", "Prioritizes voting-rights safeguards.", legal),
        ]
        if goals.get("prioritize_compactness"):
            candidates.append(CandidateConfig("compactness_guardrail", "Boost compactness weight.", compact))
        if goals.get("prioritize_speed"):
            candidates.append(CandidateConfig("quick_turnaround", "Faster runtime, lower iteration budget.", fast))
        return candidates[:5]

    def _legal_risk_assessment(self, result: dict[str, Any]) -> dict[str, Any]:
        scores = result.get("score_breakdown", {})
        district_metrics = result.get("district_metrics", [])
        pop_values = [float(d.get("population", 0)) for d in district_metrics]
        max_dev = 0.0
        if pop_values:
            mean_pop = sum(pop_values) / len(pop_values)
            if mean_pop > 0:
                max_dev = max(abs(v - mean_pop) / mean_pop for v in pop_values)

        flags: list[str] = []
        if scores.get("voting_rights", 0.0) < 0.5:
            flags.append("Low voting-rights proxy score.")
        if max_dev > 0.12:
            flags.append("Population deviation exceeds 12% max district threshold.")
        if scores.get("compactness", 0.0) < 0.45:
            flags.append("Compactness proxy indicates fragmented district structure.")
        if not flags:
            risk_level = "low"
        elif len(flags) == 1:
            risk_level = "medium"
        else:
            risk_level = "high"
        return {
            "risk_level": risk_level,
            "flags": flags,
            "max_population_deviation": round(max_dev, 4),
        }

    def _policy_utility(self, result: dict[str, Any], legal: dict[str, Any], goals: dict[str, Any]) -> float:
        scores = result.get("score_breakdown", {})
        utility = (
            0.33 * float(scores.get("racial_fairness", 0.0))
            + 0.27 * float(scores.get("population_equality", 0.0))
            + 0.20 * float(scores.get("compactness", 0.0))
            + 0.20 * float(scores.get("voting_rights", 0.0))
        )
        risk_level = legal.get("risk_level", "medium")
        if risk_level == "high":
            utility -= 0.20
        elif risk_level == "medium":
            utility -= 0.08

        if goals.get("prioritize_legal_safety"):
            utility += 0.08 * float(scores.get("voting_rights", 0.0))
        if goals.get("prioritize_compactness"):
            utility += 0.08 * float(scores.get("compactness", 0.0))
        if goals.get("prioritize_fairness"):
            utility += 0.08 * float(scores.get("racial_fairness", 0.0))
        return utility

    def _trace_id(self, state_fips: str, question: str) -> str:
        source = f"{state_fips}|{question}|{_utc_now()}".encode("utf-8")
        return hashlib.sha256(source).hexdigest()[:16]

    def _without_assignment(self, payload: dict[str, Any]) -> dict[str, Any]:
        out = dict(payload)
        out.pop("assignment", None)
        return out

    def _one_line_recommendation(self, recommended: dict[str, Any]) -> str:
        risk = (recommended.get("legal_risk") or {}).get("risk_level", "unknown")
        name = recommended.get("candidate_name", "recommended option")
        return f"Use {name}: it delivers the best overall score while keeping legal risk at {risk}."

    def _why_this_option(self, recommended: dict[str, Any]) -> str:
        scores = recommended.get("score_breakdown", {})
        return (
            "It balances legal safety and fairness using strong voting-rights and population-balance results "
            f"(voting_rights={scores.get('voting_rights', 0):.2f}, "
            f"population_equality={scores.get('population_equality', 0):.2f})."
        )

    def _agent_breakdown(self, recommended: dict[str, Any], liaison: dict[str, Any]) -> dict[str, Any]:
        scores = recommended.get("score_breakdown", {})
        legal_risk = recommended.get("legal_risk", {})
        return {
            "engine_agent": {
                "role": "RL optimization and quantitative metrics",
                "plain_text": (
                    "Checks map math quality: fairness, population balance, shape quality, and total score."
                ),
                "technical": {
                    "weighted_reward": recommended.get("best_reward"),
                    "baseline_reward": recommended.get("baseline_reward"),
                    "improvement": recommended.get("improvement"),
                    "score_breakdown": scores,
                },
            },
            "civil_rights_advocate_agent": {
                "role": "VRA and fairness/equity risk review",
                "plain_text": (
                    "Flags potential legal/fairness concerns, including minority representation and population deviation."
                ),
                "technical": legal_risk,
            },
            "legislative_agent": {
                "role": "Legal/policy translator for legislators",
                "plain_text": (
                    "Converts technical results into a short recommendation legislators can use in briefings."
                ),
                "technical": {
                    "simple_summary": (liaison.get("liaison_output") or {}).get("simple_summary", liaison.get("final_report")),
                    "technical_appendix": (liaison.get("liaison_output") or {}).get("technical_appendix", ""),
                    "risk_level": liaison.get("risk_level"),
                },
            },
        }

    def _formatted_output(self, recommended: dict[str, Any], liaison: dict[str, Any]) -> str:
        params = recommended.get("params", {})
        weights = params.get("weights", {})
        scores = recommended.get("score_breakdown", {})
        legal = recommended.get("legal_risk", {})
        liaison_payload = liaison.get("liaison_output") or {}
        simple = liaison_payload.get("simple_summary", liaison.get("final_report", ""))
        tech = liaison_payload.get("technical_appendix", "")
        flags = legal.get("flags", [])
        flags_text = "; ".join(flags) if flags else "No immediate legal warning flags."
        return (
            "Engine Agent:\n"
            "This map was tuned by running a reward-guided optimizer over many district assignments and keeping "
            "the best-performing option. In simple terms: we tested many map choices and kept the one that scored "
            "best on fairness and stability.\n"
            f"Technical RL details: method={recommended.get('method', 'search_sa')}, iterations={params.get('iterations')}, "
            f"exploration_rate={params.get('exploration_rate')}, weights={{racial:{weights.get('racial_weight')}, "
            f"population:{weights.get('population_weight')}, compactness:{weights.get('compactness_weight')}, "
            f"vra:{weights.get('vra_weight')}}}, reward={recommended.get('best_reward')} (baseline={recommended.get('baseline_reward')}).\n\n"
            "Civil Rights Advocate Agent:\n"
            "This review checks whether the map stays fair for protected communities and avoids obvious Voting Rights Act "
            "risk signals using Census-backed demographic indicators.\n"
            f"Technical fairness details: voting_rights={scores.get('voting_rights')}, racial_fairness={scores.get('racial_fairness')}, "
            f"population_equality={scores.get('population_equality')}, risk_level={legal.get('risk_level')}, "
            f"max_population_deviation={legal.get('max_population_deviation')}, flags={flags_text}\n\n"
            "Legislative Agent:\n"
            "This step converts the analysis into policy language and checks whether the proposal appears usable "
            "from a legislative process and compliance perspective.\n"
            f"Legislative memo: {simple}\n"
            f"Technical legal appendix: {tech}\n\n"
            "Summary:\n"
            "Recommended action for legislators: adopt the recommended map configuration as the working draft, "
            "then send it to formal legal counsel review before final adoption."
        )
