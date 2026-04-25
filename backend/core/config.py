"""Central config — RL hyperparameters and environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env regardless of process cwd (uvicorn may start from repo root).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8")

    # API keys
    CENSUS_API_KEY: str = ""
    OPENAI_API_KEY: str = ""          # used by LangChain if needed
    ANTHROPIC_API_KEY: str = ""       # used by Legislative Liaison node

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    # RL hyperparameters
    RL_ALGORITHM: str = "PPO"         # "PPO" | "SAC" | "A2C"
    RL_LEARNING_RATE: float = 3e-4
    RL_GAMMA: float = 0.99            # discount factor
    RL_N_STEPS: int = 2048            # steps per rollout (PPO)
    RL_BATCH_SIZE: int = 64
    RL_N_EPOCHS: int = 10
    RL_TOTAL_TIMESTEPS: int = 1_000_000
    RL_ENT_COEF: float = 0.01         # entropy coefficient

    # Environment
    N_DISTRICTS: int = 5              # default number of districts per state
    STATE_FIPS: str = "06"            # default state (California)

    # DuckDB
    DUCKDB_PATH: str = "data/remapd.duckdb"

    # LLM defaults
    LIAISON_MODEL: str = "claude-3-5-sonnet-20241022"


settings = Settings()
