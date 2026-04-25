"""In-memory storage for the latest optimization run."""

from __future__ import annotations

from typing import Any


_latest_metrics: dict[str, Any] = {
    "episode": 0,
    "reward": [],
    "entropy": [],
    "socialImpactScores": {
        "racial_fairness": 0.0,
        "population_equality": 0.0,
        "compactness": 0.0,
        "voting_rights": 0.0,
    },
    "baselineSocialImpactScores": {
        "racial_fairness": 0.0,
        "population_equality": 0.0,
        "compactness": 0.0,
        "voting_rights": 0.0,
    },
    "baselineReward": 0.0,
    "optimizedReward": 0.0,
    "baselineLabel": "",
    "improvement": None,
}
_latest_plans: dict[str, dict[str, Any]] = {}
_cancel_requested: bool = False


def request_cancel() -> None:
    global _cancel_requested
    _cancel_requested = True


def reset_cancel() -> None:
    global _cancel_requested
    _cancel_requested = False


def should_cancel() -> bool:
    return _cancel_requested


def set_latest_run(
    state_abbr: str,
    state_fips: str,
    assignment: dict[str, int],
    district_metrics: list[dict[str, Any]],
    rewards: list[float],
    explorations: list[float],
    score_breakdown: dict[str, float],
    baseline_score_breakdown: dict[str, float],
    baseline_reward: float,
    optimized_reward: float,
    baseline_label: str,
    improvement: dict[str, Any] | None,
) -> None:
    global _latest_metrics
    _latest_metrics = {
        "episode": len(rewards),
        "reward": rewards[-120:],
        "entropy": explorations[-120:],
        "socialImpactScores": score_breakdown,
        "baselineSocialImpactScores": baseline_score_breakdown,
        "baselineReward": baseline_reward,
        "optimizedReward": optimized_reward,
        "baselineLabel": baseline_label,
        "improvement": improvement,
        "state_abbr": state_abbr.upper(),
        "state_fips": state_fips,
    }
    _latest_plans[state_abbr.upper()] = {
        "state_abbr": state_abbr.upper(),
        "state_fips": state_fips,
        "assignment": assignment,
        "district_metrics": district_metrics,
        "best_reward": optimized_reward,
    }


def get_metrics() -> dict[str, Any]:
    return _latest_metrics


def get_all_plans() -> dict[str, dict[str, Any]]:
    """Return all cached plans keyed by state_abbr."""
    return dict(_latest_plans)


def get_plan(state_abbr: str) -> dict[str, Any] | None:
    return _latest_plans.get(state_abbr.upper())
