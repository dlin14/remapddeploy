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


from api.routes.states import router as states_router
from api.routes.agent import router as agent_router
from api.routes.mcp import router as mcp_router
from api.routes.policy import router as policy_router

app.include_router(states_router)
app.include_router(agent_router)
app.include_router(mcp_router)
app.include_router(policy_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
