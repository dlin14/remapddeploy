# remapd

> **RL-powered redistricting simulation** — Claude Hackathon 2025

remapd uses Reinforcement Learning and Agentic AI to simulate, score, and explain US congressional redistricting maps through the lens of racial fairness, population equality, compactness, and Voting Rights Act compliance.

---

## Architecture

```
remapd/
├── frontend/                        # Next.js 15 App Router
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                 # Home — US Map + RL Metrics sidebar
│   │   └── map/[stateId]/
│   │       └── page.tsx             # Zoomed state district view
│   ├── components/
│   │   ├── map/
│   │   │   └── USMap.tsx            # D3 + TopoJSON 50-state choropleth
│   │   └── dashboard/
│   │       └── RLMetricsPanel.tsx   # Reward / entropy / social impact charts
│   ├── lib/utils.ts
│   └── package.json
│
└── backend/                         # Python FastAPI
    ├── main.py                      # FastAPI app + CORS
    ├── requirements.txt
    ├── core/
    │   └── config.py                # RL hyperparams + env vars (pydantic-settings)
    ├── models/
    │   ├── world_model/
    │   │   └── state_environment.py # Gymnasium env — census blocks as RL state
    │   └── agent/
    │       └── rl_agent.py          # Stable-Baselines3 PPO/SAC/A2C wrapper
    ├── services/
    │   └── gov_data_service.py      # Census API + DuckDB caching
    └── agents/
        └── social_impact_agent.py   # LangGraph evaluation graph
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend framework | Next.js 15, React 19, TypeScript |
| Styling | TailwindCSS 4, shadcn/ui |
| Maps | D3.js v7, TopoJSON (us-atlas) |
| Charts | Recharts |
| Icons | Lucide-react |
| Backend framework | FastAPI, Uvicorn, Pydantic v2 |
| RL | PyTorch, Stable-Baselines3, Gymnasium |
| Agentic AI | LangChain, LangGraph |
| Analytics DB | DuckDB |
| Data | US Census Bureau API (P.L. 94-171, ACS 5-year), TIGER/Line |

---

## Getting Started

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add CENSUS_API_KEY
uvicorn main:app --reload --port 8000
```

### Environment Variables (backend/.env)

```
CENSUS_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here        # optional, for LangChain LLM nodes
```

Get a free Census API key at https://api.census.gov/data/key_signup.html

---

## Implementation Roadmap

### Phase 1 — Data Foundation
- [ ] `GovDataService.fetch_block_demographics()` — P.L. 94-171 race/pop per census block
- [ ] `GovDataService.fetch_block_geometries()` — TIGER/Line GeoJSON
- [ ] DuckDB schema + caching pipeline
- [ ] Static TopoJSON map rendering in `USMap.tsx`

### Phase 2 — RL Environment
- [ ] `StateEnvironment.reset()` / `step()` — valid contiguous district maps
- [ ] Reward sub-functions: racial fairness, population equality, compactness, VRA
- [ ] `RLAgent.train()` end-to-end loop with PPO

### Phase 3 — Agentic Reasoning
- [ ] `SocialImpactAgent` LangGraph nodes: legal_check, demographic_analysis, equity_analysis
- [ ] LLM synthesis node with Claude (via Anthropic SDK)
- [ ] FastAPI endpoints: `/api/metrics`, `/api/states/{fips}`, `/api/agent/evaluate`

### Phase 4 — Frontend Integration
- [ ] D3 choropleth choropleth colored by RL reward score
- [ ] State click → `/map/[stateId]` zoom view with district overlay
- [ ] Live-updating `RLMetricsPanel` via polling or WebSocket
- [ ] Plain-English agent report card per state

---

## Key Design Decisions

**Census block as atomic unit** — Using census blocks (not tracts or precincts) gives the agent maximum granularity for constructing fair districts, at the cost of a larger state space (~100k blocks in large states).

**Gymnasium environment** — Wrapping redistricting as a standard Gym env lets us swap RL algorithms (PPO → SAC → custom GNN policy) without touching environment logic.

**LangGraph fan-out** — Legal, demographic, and equity checks run in parallel graph nodes and fan back into a synthesis node, keeping latency low while maintaining explainability.

**DuckDB** — In-process analytical database lets the backend run fast GROUP BY / spatial queries on census block data without a separate DB server.
