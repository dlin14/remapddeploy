"""Search-based optimizer for district assignments.

This keeps the ``RLAgent`` name to avoid touching imports, but the
implementation is intentionally lightweight for hackathon reliability:
simulated annealing over county-to-district assignments.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
from typing import Any

import numpy as np

from services.optimizer_store import should_cancel, reset_cancel


@dataclass
class OptimizerParams:
    n_districts: int
    iterations: int = 700
    exploration_rate: float = 0.25
    temperature: float = 0.35
    cooling_rate: float = 0.996
    racial_weight: float = 0.35
    population_weight: float = 0.30
    compactness_weight: float = 0.20
    vra_weight: float = 0.15


class RLAgent:
    """Optimizes a county-to-district plan using reward-guided local search."""

    def __init__(self, state_fips: str, params: OptimizerParams):
        self.state_fips = state_fips
        self.params = params
        self.county_ids = self._load_counties_for_state(state_fips)
        if not self.county_ids:
            raise ValueError(f"No counties found for state FIPS {state_fips}")
        self._unit_data = self._build_county_features(self.county_ids)
        self._target_pop = float(sum(u["population"] for u in self._unit_data.values())) / max(
            1, self.params.n_districts
        )
        self._state_minority_share = float(
            np.mean([u["minority_share"] for u in self._unit_data.values()])
        )

    def run(self) -> dict[str, Any]:
        """Execute local search and return best plan + metric traces."""
        reset_cancel()
        baseline_assignment = self._initial_assignment()
        baseline_breakdown = self._reward_breakdown(baseline_assignment)
        baseline_reward = baseline_breakdown["total"]

        current = baseline_assignment.copy()
        current_breakdown = baseline_breakdown
        current_reward = baseline_reward

        best = current.copy()
        best_breakdown = current_breakdown
        best_reward = current_reward

        rewards: list[float] = []
        explorations: list[float] = []
        temperature = self.params.temperature

        for _ in range(max(50, self.params.iterations)):
            if should_cancel():
                break
            proposal = current.copy()
            county_idx = int(np.random.randint(0, len(self.county_ids)))
            county_id = self.county_ids[county_idx]
            old_district = proposal[county_id]
            new_district = int(np.random.randint(0, self.params.n_districts))
            if new_district == old_district:
                new_district = (new_district + 1) % self.params.n_districts
            proposal[county_id] = new_district

            proposal_breakdown = self._reward_breakdown(proposal)
            proposal_reward = proposal_breakdown["total"]
            delta = proposal_reward - current_reward

            accept = delta >= 0
            if not accept:
                # Exploration allows occasional worse moves to avoid local minima.
                explore = np.random.random() < self.params.exploration_rate
                if explore and temperature > 1e-6:
                    accept_prob = math.exp(delta / temperature)
                    accept = np.random.random() < accept_prob

            if accept:
                current = proposal
                current_breakdown = proposal_breakdown
                current_reward = proposal_reward

            if current_reward > best_reward:
                best = current.copy()
                best_breakdown = current_breakdown
                best_reward = current_reward

            rewards.append(round(current_reward, 4))
            explorations.append(round(self.params.exploration_rate, 4))
            temperature *= self.params.cooling_rate

        district_metrics = self._district_metrics(best)

        def _scores(bd: dict[str, float]) -> dict[str, float]:
            return {
                "racial_fairness": round(bd["racial_fairness"], 4),
                "population_equality": round(bd["population_equality"], 4),
                "compactness": round(bd["compactness"], 4),
                "voting_rights": round(bd["voting_rights"], 4),
            }

        baseline_scores = _scores(baseline_breakdown)
        optimized_scores = _scores(best_breakdown)
        component_deltas: dict[str, dict[str, float | None]] = {}
        for key in baseline_scores:
            b = baseline_scores[key]
            o = optimized_scores[key]
            delta = round(o - b, 4)
            rel_pct: float | None = None
            if b > 1e-6:
                rel_pct = round(100.0 * (o - b) / b, 1)
            component_deltas[key] = {"delta": delta, "pct_vs_baseline": rel_pct}

        total_delta = round(best_reward - baseline_reward, 4)
        total_pct: float | None = None
        if baseline_reward > 1e-6:
            total_pct = round(100.0 * (best_reward - baseline_reward) / baseline_reward, 1)

        return {
            "state_fips": self.state_fips,
            "n_districts": self.params.n_districts,
            "assignment": best,
            "district_metrics": district_metrics,
            "best_reward": round(best_reward, 4),
            "baseline_reward": round(baseline_reward, 4),
            "reward_history": rewards,
            "exploration_history": explorations,
            "baseline_label": "round_robin_initial",
            "baseline_score_breakdown": baseline_scores,
            "score_breakdown": optimized_scores,
            "improvement": {
                "total_reward_delta": total_delta,
                "total_reward_pct_vs_baseline": total_pct,
                "components": component_deltas,
            },
        }

    def _initial_assignment(self) -> dict[str, int]:
        assignment: dict[str, int] = {}
        for idx, county_id in enumerate(self.county_ids):
            assignment[county_id] = idx % self.params.n_districts
        return assignment

    def _district_metrics(self, assignment: dict[str, int]) -> list[dict[str, Any]]:
        metrics: list[dict[str, Any]] = []
        for district_id in range(self.params.n_districts):
            members = [cid for cid, d in assignment.items() if d == district_id]
            population = int(sum(self._unit_data[cid]["population"] for cid in members))
            minority_population = int(
                sum(
                    self._unit_data[cid]["population"] * self._unit_data[cid]["minority_share"]
                    for cid in members
                )
            )
            minority_share = minority_population / max(1, population)
            metrics.append(
                {
                    "district_id": district_id,
                    "num_counties": len(members),
                    "population": population,
                    "minority_share": round(minority_share, 4),
                }
            )
        return metrics

    def _reward_breakdown(self, assignment: dict[str, int]) -> dict[str, float]:
        district_metrics = self._district_metrics(assignment)
        district_pops = np.array([d["population"] for d in district_metrics], dtype=float)
        district_shares = np.array([d["minority_share"] for d in district_metrics], dtype=float)
        district_sizes = np.array([d["num_counties"] for d in district_metrics], dtype=float)

        pop_dev = np.abs(district_pops - self._target_pop) / max(1.0, self._target_pop)
        population_equality = float(np.clip(1.0 - np.mean(pop_dev), 0.0, 1.0))

        racial_gap = np.mean(np.abs(district_shares - self._state_minority_share))
        racial_fairness = float(np.clip(1.0 - racial_gap * 2.0, 0.0, 1.0))

        mean_size = max(1.0, float(np.mean(district_sizes)))
        compactness = float(
            np.clip(1.0 - (np.std(district_sizes) / mean_size), 0.0, 1.0)
        )

        target_opportunity = max(
            1, int(round(self.params.n_districts * self._state_minority_share))
        )
        opportunity_count = int(np.sum(district_shares >= 0.45))
        voting_rights = float(
            np.clip(opportunity_count / max(1, target_opportunity), 0.0, 1.0)
        )

        total = (
            self.params.racial_weight * racial_fairness
            + self.params.population_weight * population_equality
            + self.params.compactness_weight * compactness
            + self.params.vra_weight * voting_rights
        )
        return {
            "racial_fairness": racial_fairness,
            "population_equality": population_equality,
            "compactness": compactness,
            "voting_rights": voting_rights,
            "total": float(total),
        }

    def _build_county_features(self, county_ids: list[str]) -> dict[str, dict[str, float]]:
        features: dict[str, dict[str, float]] = {}
        for county_id in county_ids:
            # Deterministic pseudo-data keeps local demos stable without API calls.
            seed = int(county_id)
            rng = np.random.default_rng(seed)
            population = int(rng.integers(12_000, 300_000))
            minority_share = float(rng.uniform(0.12, 0.78))
            features[county_id] = {
                "population": float(population),
                "minority_share": minority_share,
            }
        return features

    @classmethod
    def default_plan(cls, state_fips: str, n_districts: int = 5) -> dict[str, Any]:
        """Round-robin assignment with no optimization — served before first run."""
        params = OptimizerParams(n_districts=n_districts, iterations=1)
        agent = cls(state_fips=state_fips, params=params)
        assignment = agent._initial_assignment()
        district_metrics = agent._district_metrics(assignment)
        return {
            "state_abbr": state_fips,   # caller overwrites with proper abbr
            "state_fips": state_fips,
            "assignment": assignment,
            "district_metrics": district_metrics,
        }

    def _load_counties_for_state(self, state_fips: str) -> list[str]:
        root = Path(__file__).resolve().parents[3]
        topo_path = root / "frontend" / "public" / "counties-10m.json"
        with topo_path.open("r", encoding="utf-8") as f:
            topo = json.load(f)
        geometries = topo["objects"]["counties"]["geometries"]
        county_ids = [
            str(item["id"]).zfill(5)
            for item in geometries
            if str(item["id"]).zfill(5).startswith(state_fips)
        ]
        return sorted(county_ids)
