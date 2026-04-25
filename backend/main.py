"""remapd FastAPI entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings

app = FastAPI(
    title="remapd API",
    description="RL-powered redistricting backend — world model, agentic reasoning, gov-data integration.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# TODO: mount routers
# from api.routes import metrics, states, agent
# app.include_router(metrics.router, prefix="/api/metrics")
# app.include_router(states.router, prefix="/api/states")
# app.include_router(agent.router, prefix="/api/agent")
