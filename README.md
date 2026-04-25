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

### Frontend

**Next.js 15 (App Router) + React 19**
The frontend uses the Next.js App Router, which means each route is a React Server Component by default — data fetching and HTML rendering happen on the server, and only interactive pieces are shipped as client bundles. The `app/map/[stateId]` dynamic route uses `generateStaticParams` to pre-render all 50 state pages at build time. React 19 brings the new `use` API and improved Suspense boundaries, which we use to stream demographic data into the sidebar without blocking the map render.

**TypeScript**
Strict TypeScript throughout. Every Census API response, D3 feature, RL parameter, and component prop has an explicit type. This catches shape mismatches between the FastAPI response models and the frontend display components at compile time instead of at runtime.

**TailwindCSS v4**
Tailwind v4 moves configuration into CSS (`@theme`) instead of `tailwind.config.js`. All design tokens — colors, radii, spacing — are CSS custom properties declared in `globals.css`, which means they respond to dark mode via `:root` / `.dark` without any JavaScript.

**shadcn/ui + Radix UI**
shadcn/ui components (Button, etc.) are copied directly into the repo rather than installed as a package dependency. Each component is built on Radix UI primitives, which handle all accessibility concerns (keyboard navigation, ARIA attributes, focus traps) so we don't have to. Components use `class-variance-authority` (CVA) for variant management, keeping conditional class logic declarative.

**D3.js v7 + TopoJSON (us-atlas)**
D3 is used strictly for geographic rendering — no React–D3 hybrid libraries. The `USMap` component uses a `useEffect` that runs once on mount, selects the SVG via a `ref`, and issues D3 calls directly against the DOM. The `geoAlbersUsa` composite projection handles Alaska and Hawaii repositioning automatically. `StateMap` uses `geoMercator().fitSize()` to fit each individual state into its viewport. TopoJSON's `mesh` function is used to draw only internal borders (borders shared between two features) rather than drawing each state outline twice.

**Recharts**
Declarative React chart library used for the RL metrics panel — reward curves (`LineChart`), entropy trends (`AreaChart`), and social impact score breakdowns (`BarChart`). Chosen over D3 charts because the metrics panel is pure data display with no custom geographic projection requirements.

---

### Backend

**FastAPI + Uvicorn**
FastAPI is an ASGI framework built on Starlette and Pydantic. Every route's request and response shape is declared as a Pydantic model, which means FastAPI auto-generates an OpenAPI schema (viewable at `/docs`) and validates all inputs/outputs at the boundary. Uvicorn is the ASGI server; `--reload` uses `watchfiles` to hot-reload on any `.py` change during development.

**Pydantic v2 + pydantic-settings**
Pydantic v2 rewrites the validation core in Rust (`pydantic-core`), making model instantiation ~5–50x faster than v1. `pydantic-settings` extends Pydantic to load configuration from `.env` files and environment variables, with the same type validation. All RL hyperparameters, API keys, and database paths live in `core/config.py` as a single `Settings` class — one source of truth, loaded once at startup.

**PyTorch**
The underlying tensor and autograd engine for all neural network components. In remapd, PyTorch backs the policy network inside Stable-Baselines3. Eventually the plan is to replace the default MLP policy with a Graph Neural Network (GNN) that encodes the adjacency structure of census blocks — PyTorch Geometric will be used for that.

**Stable-Baselines3 (SB3)**
SB3 provides battle-tested implementations of PPO, SAC, and A2C that follow the Gymnasium interface. The `RLAgent` wrapper in `models/agent/rl_agent.py` is thin on purpose — swapping the algorithm is a one-line config change (`RL_ALGORITHM=SAC`). SB3 handles rollout buffers, advantage estimation, gradient clipping, and learning rate scheduling internally.

**Gymnasium**
OpenAI Gym's maintained successor. `StateEnvironment` subclasses `gym.Env` and defines the redistricting problem as a standard RL loop: `reset()` initializes a district map, `step(action)` applies a block reassignment and returns `(observation, reward, terminated, truncated, info)`. This interface means any SB3 algorithm — or any external RL framework — can train against it without modification.

**LangChain + LangGraph**
LangChain provides the tool-calling abstractions and LLM client wrappers. LangGraph is used for the `SocialImpactAgent`: it models the evaluation pipeline as a directed graph where nodes are Python functions and edges define execution order. The current graph fans out from `evaluate_proposal` into three parallel analysis nodes (`legal_check`, `demographic_analysis`, `equity_analysis`), then fans back into `synthesize_report` — a pattern LangGraph supports natively via its state reducer system. This keeps each concern isolated and independently testable.

**DuckDB**
An in-process OLAP database — no server, no port, just a `.duckdb` file. DuckDB is optimized for analytical queries (GROUP BY, window functions, aggregations) over columnar data, which is exactly the workload for redistricting: "what is the racial composition of district 3 given these 40,000 block assignments?" Standard SQLite would be much slower for these scans. DuckDB also has a native spatial extension (`LOAD spatial`) for future geometry operations.

**httpx**
Async HTTP client used by `GovDataService` to call the Census Bureau API. Unlike `requests`, httpx is natively async so Census API calls don't block the event loop. `follow_redirects=False` is intentional — the Census API redirects to an HTML error page on invalid keys, so we detect the redirect as an error rather than silently following it into a JSON parse failure.

---

### Data

**US Census Bureau ACS 5-Year Estimates**
The American Community Survey (ACS) 5-year dataset aggregates survey responses over 5 years to produce reliable estimates at fine geographic levels. We use the 2022 vintage at the state level for the demographics sidebar. Variables used: total population (`B01003`), racial composition (`B02001`, `B03003`), median household income (`B19013`), educational attainment (`B15003`), poverty rate (`B17001`), and median age (`B01002`).

**Census P.L. 94-171 Redistricting File**
The decennial census redistricting file (named after the law requiring its publication) contains exact population and racial counts at the census block level — the most granular geography the Census Bureau publishes. This is the legally mandated dataset used for actual redistricting. The `GovDataService` is scaffolded to fetch this via the Census API for use as the RL environment's state space.

**TIGER/Line + us-atlas TopoJSON**
Census TIGER/Line files contain the official cartographic boundaries for every geographic entity the Census Bureau recognizes. `us-atlas` packages these as compressed TopoJSON for the web — `states-10m.json` (114 KB) and `counties-10m.json` (842 KB) at 1:10M scale. TopoJSON is more compact than GeoJSON because shared borders are stored once rather than duplicated in each adjacent feature.

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
