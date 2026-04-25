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

---

## Technical Reimplementation Guide (Hackathon Optimizer MVP)

This section is a low-level implementation spec for reproducing the current county-level district optimizer and UI integration.

### 1) Problem Formulation

#### 1.1 Atomic units
- Geographic atomic unit for this MVP is **county** (5-digit county FIPS), not census block.
- A districting plan is represented as a label assignment:
  - `assignment: Dict[county_fips, district_id]`
  - `district_id in [0, n_districts-1]`

#### 1.2 Optimization objective
Maximize weighted reward:

\[
R = w_r S_r + w_p S_p + w_c S_c + w_v S_v
\]

Where:
- `S_r`: racial fairness proxy
- `S_p`: population equality
- `S_c`: compactness proxy
- `S_v`: voting-rights proxy
- weights from runtime request (`racial_weight`, `population_weight`, `compactness_weight`, `vra_weight`)

All sub-scores are normalized/clamped to `[0, 1]`.

### 2) Runtime Data Model

#### 2.1 County feature table (in-memory)
For each county:
- `county_fips: str`
- `population: float`
- `minority_share: float` in `[0,1]`

Current implementation uses deterministic pseudo-features per county FIPS seed for reliability under hackathon constraints.

#### 2.2 District aggregate model (derived each iteration)
For each district:
- `district_id: int`
- `num_counties: int`
- `population: int`
- `minority_share: float`

#### 2.3 Global cached outputs
- Latest metrics payload for dashboard polling:
  - `episode` (iteration count)
  - `reward` (history array)
  - `entropy` (exploration-rate history array)
  - `socialImpactScores` (latest component scores)
- Latest district plan per state:
  - `state_abbr`
  - `state_fips`
  - `assignment`
  - `district_metrics`

### 3) Geography Ingestion

#### 3.1 Source file
- TopoJSON from frontend static asset:
  - `frontend/public/counties-10m.json`

#### 3.2 State county extraction
1. Load TopoJSON.
2. Enumerate `objects.counties.geometries`.
3. Normalize county IDs to zero-padded 5-char strings.
4. Filter by prefix match on 2-char `state_fips`.

### 4) Optimizer Algorithm

Implementation file: `backend/models/agent/rl_agent.py` (class name retained as `RLAgent` for compatibility).

#### 4.1 Initialization
1. Extract all counties for state.
2. Build county features.
3. Compute:
   - `target_pop = total_pop / n_districts`
   - `state_minority_share = mean(county_minority_share)`
4. Build initial assignment by round-robin county index:
   - `assignment[county_i] = i % n_districts`

#### 4.2 Single action definition
Action is a local reassignment:
- pick one county `c`
- move from `old_district` to `new_district` (`new_district != old_district`)

No polygon coordinate editing is performed; district geometry is emergent from county color classes.

#### 4.3 Move acceptance (simulated annealing style)
Given current reward `R_cur` and proposed reward `R_new`:
- if `R_new >= R_cur`, accept
- else with probability `exploration_rate`, try probabilistic uphill escape:
  \[
  P(\text{accept}) = \exp\left(\frac{R_{new}-R_{cur}}{T}\right)
  \]
- decay temperature each iteration:
  - `T = T * cooling_rate`

#### 4.4 Iteration loop
For `iterations` steps:
1. Propose random county reassignment.
2. Compute proposal reward.
3. Apply acceptance rule.
4. Track best-so-far assignment and reward.
5. Append metrics:
   - `reward_history`
   - `exploration_history`

Return best plan + histories.

### 5) Reward Components (Exact Proxies)

Let district metrics produce arrays:
- `district_pops`
- `district_shares` (minority share per district)
- `district_sizes` (counties per district)

#### 5.1 Population equality `S_p`
\[
\delta_d = \frac{|pop_d - target\_pop|}{target\_pop}
\]
\[
S_p = clamp(1 - mean(\delta_d), 0, 1)
\]

#### 5.2 Racial fairness `S_r`
\[
gap = mean(|district\_share_d - state\_minority\_share|)
\]
\[
S_r = clamp(1 - 2 \cdot gap, 0, 1)
\]

#### 5.3 Compactness proxy `S_c`
Uses district county-count balance as a cheap compactness surrogate:
\[
S_c = clamp\left(1 - \frac{std(district\_sizes)}{mean(district\_sizes)}, 0, 1\right)
\]

#### 5.4 Voting-rights proxy `S_v`
Opportunity district threshold set to minority share `>= 0.45`:
- `opportunity_count = count(district_share >= 0.45)`
- `target_opportunity = max(1, round(n_districts * state_minority_share))`
\[
S_v = clamp\left(\frac{opportunity\_count}{target\_opportunity}, 0, 1\right)
\]

#### 5.5 Total reward
\[
R = w_r S_r + w_p S_p + w_c S_c + w_v S_v
\]

### 6) Backend API Contract

#### 6.1 `POST /api/agent/run`
Body:
```json
{
  "state_abbr": "CA",
  "n_districts": 8,
  "n_steps": 700,
  "racial_weight": 0.35,
  "population_weight": 0.30,
  "compactness_weight": 0.20,
  "vra_weight": 0.15,
  "ent_coef": 0.25
}
```

Semantics:
- `n_steps` -> iteration budget
- `ent_coef` -> exploration rate

Response:
```json
{
  "status": "ok",
  "state_abbr": "CA",
  "state_fips": "06",
  "best_reward": 0.7421,
  "iterations": 700
}
```

#### 6.2 `GET /api/agent/metrics`
Returns latest dashboard metrics:
```json
{
  "episode": 700,
  "reward": [0.61, 0.62, "..."],
  "entropy": [0.25, 0.25, "..."],
  "socialImpactScores": {
    "racial_fairness": 0.71,
    "population_equality": 0.76,
    "compactness": 0.67,
    "voting_rights": 0.83
  }
}
```

#### 6.3 `GET /api/states/{state_abbr_or_fips}/district-plan`
Supports either 2-letter state abbreviation or 2-digit FIPS route token.
Response:
```json
{
  "state_abbr": "CA",
  "state_fips": "06",
  "assignment": {
    "06001": 0,
    "06003": 1
  },
  "district_metrics": [
    {
      "district_id": 0,
      "num_counties": 8,
      "population": 3200000,
      "minority_share": 0.54
    }
  ]
}
```

### 7) Frontend Integration Contract

#### 7.1 Run control (`RLParamsSliders`)
- Sends slider values to `POST /api/agent/run`.
- Displays completion text with iteration count and best reward.

#### 7.2 Metrics panel (`RLMetricsPanel`)
- Poll interval: ~2500 ms.
- Endpoint: `GET /api/agent/metrics`.
- Renders current reward, exploration rate, and component scores.

#### 7.3 State map (`StateMap`)
- Poll interval: ~3000 ms.
- Endpoint: `GET /api/states/{state_fips}/district-plan`.
- County fill color keyed by `assignment[county_fips]`.
- Legend generated from `district_metrics`.

### 8) Determinism and Reproducibility

- County pseudo-features are deterministic per county FIPS seed.
- The search trajectory is stochastic unless you set a fixed global RNG seed.
- To make runs reproducible, inject a configurable seed and initialize `numpy` RNG once per run.

### 9) Complexity Characteristics

Let:
- `N = # counties in state`
- `K = n_districts`
- `I = iterations`

Per iteration:
- recompute district metrics currently scans `N` counties
- complexity approx `O(N)` per move
- total `O(I * N)` time, `O(N + K)` memory

For hackathon state sizes (county-level), this is practical in seconds.

### 10) Upgrade Path (Post-Hackathon)

1. Replace pseudo county features with real county/block aggregates from Census + TIGER joins.
2. Add adjacency-aware compactness and explicit contiguity penalties.
3. Add hard constraints (reject moves that violate contiguity/pop bounds).
4. Swap optimizer module behind same API contract:
   - simulated annealing -> PPO/SAC/A2C/GNN policy.
5. Introduce background job execution and websocket streaming for long runs.

### 11) Minimal Reimplementation Checklist

If another engineer re-implements from scratch, they must preserve:
- assignment-based district representation (county -> district label),
- weighted reward interface with the same 4 components,
- run endpoint returning quick completion metadata,
- metrics endpoint returning history arrays and score breakdown,
- district-plan endpoint returning assignment + district aggregates,
- frontend polling + county recolor behavior.
