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
from services.census_cache import get_county_data


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
        self.county_ids, self._county_centroids = self._load_counties_and_centroids(state_fips)
        if not self.county_ids:
            raise ValueError(f"No counties found for state FIPS {state_fips}")
        self._unit_data = self._build_county_features(self.county_ids)
        self._target_pop = float(sum(u["population"] for u in self._unit_data.values())) / max(
            1, self.params.n_districts
        )
        self._state_minority_share = float(
            np.mean([u["minority_share"] for u in self._unit_data.values()])
        )

        # Precompute state geographic extent for compactness normalization.
        # _state_extent = RMS distance from state centroid to each county centroid.
        # This represents how "big" the state is and is used to normalize district spread.
        if self._county_centroids:
            xs = [c[0] for c in self._county_centroids.values()]
            ys = [c[1] for c in self._county_centroids.values()]
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            self._state_extent = math.sqrt(
                sum((x - cx) ** 2 + (y - cy) ** 2 for x, y in zip(xs, ys)) / len(xs)
            )
        else:
            self._state_extent = 0.0

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
        # Sort counties geographically (west→east then north→south) and assign
        # contiguous blocks to each district.  This gives each district a
        # spatially cohesive starting shape, improving the initial compactness
        # score and accelerating geographic clustering during optimization.
        if self._county_centroids:
            sorted_ids = sorted(
                self.county_ids,
                key=lambda cid: (
                    round(self._county_centroids[cid][0] / 3) * 3,  # ~3° lon band
                    -self._county_centroids[cid][1],                  # north→south within band
                ),
            )
        else:
            sorted_ids = self.county_ids

        n = len(sorted_ids)
        k = self.params.n_districts
        chunk = n / max(1, k)
        return {cid: min(int(idx / chunk), k - 1) for idx, cid in enumerate(sorted_ids)}

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

        # ── Population equality ──────────────────────────────────────────────
        pop_dev = np.abs(district_pops - self._target_pop) / max(1.0, self._target_pop)
        population_equality = float(np.clip(1.0 - np.mean(pop_dev), 0.0, 1.0))

        # ── Racial fairness ──────────────────────────────────────────────────
        racial_gap = np.mean(np.abs(district_shares - self._state_minority_share))
        racial_fairness = float(np.clip(1.0 - racial_gap * 2.0, 0.0, 1.0))

        # ── Geographic compactness ───────────────────────────────────────────
        # Measure how tightly clustered each district's county centroids are.
        # We compute the RMS spread of county centroids within each district,
        # then normalize by the state's overall geographic extent (RMS distance
        # from state centroid to all county centroids).
        #
        # Score interpretation:
        #   spread = 0            → compactness = 1.0 (all counties co-located)
        #   spread = state_extent → compactness = 0.0 (district spans the whole state)
        #
        # A random round-robin assignment scores ≈ 0.03–0.10 because its districts
        # span nearly the full state.  Geographically clustered assignments score
        # ≈ 0.5–0.85, giving the optimizer a clear gradient to climb.
        if self._county_centroids and self._state_extent > 0:
            district_spreads: list[float] = []
            for district_id in range(self.params.n_districts):
                members = [cid for cid, d in assignment.items() if d == district_id]
                coords = [self._county_centroids[m] for m in members if m in self._county_centroids]
                if len(coords) < 2:
                    district_spreads.append(0.0)
                    continue
                cx = sum(c[0] for c in coords) / len(coords)
                cy = sum(c[1] for c in coords) / len(coords)
                rms_spread = math.sqrt(
                    sum((c[0] - cx) ** 2 + (c[1] - cy) ** 2 for c in coords) / len(coords)
                )
                district_spreads.append(rms_spread)

            mean_spread = sum(district_spreads) / max(1, len(district_spreads))
            # Normalize directly by state extent; clip to [0, 1]
            compactness = float(np.clip(1.0 - mean_spread / self._state_extent, 0.0, 1.0))
        else:
            # Fallback when centroids are unavailable: equal county-count distribution
            district_sizes = np.array([d["num_counties"] for d in district_metrics], dtype=float)
            mean_size = max(1.0, float(np.mean(district_sizes)))
            compactness = float(np.clip(1.0 - (np.std(district_sizes) / mean_size), 0.0, 1.0))

        # ── Voting rights (opportunity districts) ────────────────────────────
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
        # Try real Census ACS data first (requires CENSUS_API_KEY in env).
        real = get_county_data(self.state_fips)

        features: dict[str, dict[str, float]] = {}
        for county_id in county_ids:
            if county_id in real:
                features[county_id] = {
                    "population": float(real[county_id]["population"]),
                    "minority_share": float(real[county_id]["minority_share"]),
                }
            else:
                # Deterministic synthetic fallback when no Census API key is set.
                seed = int(county_id)
                rng = np.random.default_rng(seed)
                features[county_id] = {
                    "population": float(rng.integers(12_000, 300_000)),
                    "minority_share": float(rng.uniform(0.12, 0.78)),
                }
        return features

    def _load_counties_and_centroids(
        self, state_fips: str
    ) -> tuple[list[str], dict[str, tuple[float, float]]]:
        """Read county FIPS list + approximate lat/lon centroids from the counties TopoJSON.

        Centroids are computed by decoding each county's arc coordinates using the
        topology's transform (scale + translate) and delta-encoding, then averaging
        all decoded points.  This gives a geographic centroid accurate enough for
        the compactness scoring heuristic.
        """
        root = Path(__file__).resolve().parents[3]
        topo_path = root / "frontend" / "public" / "counties-10m.json"
        with topo_path.open("r", encoding="utf-8") as f:
            topo = json.load(f)

        transform = topo.get("transform", {})
        scale = transform.get("scale", [1.0, 1.0])
        translate = transform.get("translate", [0.0, 0.0])
        arcs: list[list[list[int]]] = topo.get("arcs", [])

        county_ids: list[str] = []
        centroids: dict[str, tuple[float, float]] = {}

        for geom in topo["objects"]["counties"]["geometries"]:
            county_id = str(geom.get("id", "")).zfill(5)
            if not county_id.startswith(state_fips):
                continue
            county_ids.append(county_id)

            # Collect all referenced arc indices (negative = reversed, ~idx)
            raw_arcs = geom.get("arcs", [])
            arc_indices: list[int] = []
            if geom["type"] == "Polygon":
                for ring in raw_arcs:
                    arc_indices.extend(ring)
            elif geom["type"] == "MultiPolygon":
                for polygon in raw_arcs:
                    for ring in polygon:
                        arc_indices.extend(ring)

            # Decode delta-encoded arc coordinates → real lon/lat
            all_x: list[float] = []
            all_y: list[float] = []
            for arc_idx in arc_indices:
                real_idx = ~arc_idx if arc_idx < 0 else arc_idx
                if real_idx >= len(arcs):
                    continue
                ax, ay = 0, 0
                for dx, dy in arcs[real_idx]:
                    ax += dx
                    ay += dy
                    all_x.append(ax * scale[0] + translate[0])
                    all_y.append(ay * scale[1] + translate[1])

            if all_x:
                centroids[county_id] = (
                    sum(all_x) / len(all_x),
                    sum(all_y) / len(all_y),
                )

        return sorted(county_ids), centroids

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
