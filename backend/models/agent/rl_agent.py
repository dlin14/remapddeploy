"""
RLAgent — thin wrapper around Stable-Baselines3 for training and inference.

Supports PPO (default), SAC, and A2C via the RL_ALGORITHM config key.

TODO:
    - Wire up StateEnvironment as the training env
    - Add custom policy network that encodes graph structure (GNN or attention)
    - Implement checkpoint saving/loading to disk
    - Stream live metrics (reward, entropy) to FastAPI via asyncio Queue
    - Add curriculum learning: start with small states, scale up
"""

from __future__ import annotations

from stable_baselines3 import PPO, SAC, A2C
from stable_baselines3.common.base_class import BaseAlgorithm

from core.config import settings
from models.world_model.state_environment import StateEnvironment

_ALGORITHM_MAP: dict[str, type[BaseAlgorithm]] = {
    "PPO": PPO,
    "SAC": SAC,
    "A2C": A2C,
}


class RLAgent:
    """Trains and runs inference against StateEnvironment."""

    def __init__(self, state_fips: str | None = None, n_districts: int | None = None):
        self.state_fips = state_fips or settings.STATE_FIPS
        self.n_districts = n_districts or settings.N_DISTRICTS

        self.env = StateEnvironment(
            state_fips=self.state_fips,
            n_districts=self.n_districts,
        )

        algo_cls = _ALGORITHM_MAP.get(settings.RL_ALGORITHM, PPO)
        self.model: BaseAlgorithm = algo_cls(
            policy="MlpPolicy",
            env=self.env,
            learning_rate=settings.RL_LEARNING_RATE,
            gamma=settings.RL_GAMMA,
            n_steps=settings.RL_N_STEPS if settings.RL_ALGORITHM == "PPO" else 1,
            batch_size=settings.RL_BATCH_SIZE,
            verbose=1,
        )

    def train(self, total_timesteps: int | None = None) -> None:
        """Run the RL training loop."""
        self.model.learn(
            total_timesteps=total_timesteps or settings.RL_TOTAL_TIMESTEPS,
            # TODO: add callback for streaming metrics to API
        )

    def predict(self, observation) -> tuple:
        """Return (action, state) for a single observation."""
        return self.model.predict(observation, deterministic=True)

    def save(self, path: str) -> None:
        self.model.save(path)

    def load(self, path: str) -> None:
        algo_cls = _ALGORITHM_MAP.get(settings.RL_ALGORITHM, PPO)
        self.model = algo_cls.load(path, env=self.env)
