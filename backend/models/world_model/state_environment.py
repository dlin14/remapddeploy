"""
StateEnvironment — Gymnasium-compatible RL environment for redistricting.

The agent manipulates district assignments for census blocks within a state
and receives a reward signal based on fairness, compactness, and legal constraints.

TODO:
    - Load census block GeoJSON + demographic data from DuckDB
    - Define observation space: adjacency matrix + block-level feature vectors
    - Define action space: Discrete(n_blocks) or MultiDiscrete for district assignment
    - Implement step(): apply action, recompute district stats, return (obs, reward, done, info)
    - Implement reset(): sample a valid initial district map
    - Implement _compute_reward(): weighted sum of sub-rewards below
"""

import gymnasium as gym
import numpy as np
from gymnasium import spaces


class StateEnvironment(gym.Env):
    """Redistricting environment for a single US state."""

    metadata = {"render_modes": ["human", "rgb_array"]}

    def __init__(self, state_fips: str, n_districts: int, render_mode: str | None = None):
        super().__init__()
        self.state_fips = state_fips
        self.n_districts = n_districts
        self.render_mode = render_mode

        # TODO: load real block count from DuckDB
        self.n_blocks: int = 100  # placeholder

        # Observation: for each block, its district assignment + demographic features
        # Shape: (n_blocks, n_features) — flattened for simplicity
        self.observation_space = spaces.Box(
            low=0.0,
            high=1.0,
            shape=(self.n_blocks * (self.n_districts + 5),),
            dtype=np.float32,
        )

        # Action: reassign one block to one district
        self.action_space = spaces.MultiDiscrete([self.n_blocks, self.n_districts])

        self._state: np.ndarray | None = None

    # ------------------------------------------------------------------
    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        # TODO: initialize a valid (contiguous) district map
        self._state = self.observation_space.sample()
        return self._state, {}

    def step(self, action):
        # TODO: apply district reassignment, check contiguity, compute reward
        block_idx, new_district = int(action[0]), int(action[1])
        _ = block_idx, new_district  # suppress unused warning

        obs = self.observation_space.sample()
        reward = self._compute_reward()
        terminated = False
        truncated = False
        info: dict = {}
        return obs, reward, terminated, truncated, info

    def _compute_reward(self) -> float:
        """Weighted combination of redistricting fairness sub-rewards."""
        # TODO: implement each sub-reward
        racial_fairness_score = 0.0
        population_equality_score = 0.0
        compactness_score = 0.0
        voting_rights_score = 0.0

        weights = {"racial": 0.35, "pop": 0.30, "compact": 0.20, "vra": 0.15}
        return (
            weights["racial"] * racial_fairness_score
            + weights["pop"] * population_equality_score
            + weights["compact"] * compactness_score
            + weights["vra"] * voting_rights_score
        )

    def render(self):
        # TODO: render district map as image for debugging
        pass

    def close(self):
        pass
