"""State demographics endpoint — fetches ACS 5-year data from Census Bureau API."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import settings
from services.optimizer_store import get_plan

router = APIRouter(prefix="/api/states", tags=["states"])

# ACS 5-year variables
ACS_VARS = ",".join([
    "NAME",
    "B01003_001E",   # total population
    "B02001_002E",   # white alone
    "B02001_003E",   # Black or African American alone
    "B02001_005E",   # Asian alone
    "B03003_003E",   # Hispanic or Latino
    "B19013_001E",   # median household income
    "B15003_022E",   # bachelor's degree
    "B15003_001E",   # population 25+ (education denominator)
    "B17001_002E",   # below poverty level
    "B17001_001E",   # poverty universe
    "B01002_001E",   # median age
])

ABBR_TO_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}
FIPS_TO_ABBR: dict[str, str] = {fips: abbr for abbr, fips in ABBR_TO_FIPS.items()}

# 118th Congress apportionment (2023–2025)
FIPS_TO_DISTRICTS: dict[str, int] = {
    "01": 7,  "02": 1,  "04": 9,  "05": 4,  "06": 52,
    "08": 8,  "09": 5,  "10": 1,  "11": 1,  "12": 28,
    "13": 14, "15": 2,  "16": 2,  "17": 17, "18": 9,
    "19": 4,  "20": 4,  "21": 6,  "22": 6,  "23": 2,
    "24": 8,  "25": 9,  "26": 13, "27": 8,  "28": 4,
    "29": 8,  "30": 2,  "31": 3,  "32": 4,  "33": 2,
    "34": 12, "35": 3,  "36": 26, "37": 14, "38": 1,
    "39": 15, "40": 5,  "41": 6,  "42": 17, "44": 2,
    "45": 7,  "46": 1,  "47": 9,  "48": 38, "49": 4,
    "50": 1,  "51": 11, "53": 10, "54": 2,  "55": 8,
    "56": 1,
}


class Demographics(BaseModel):
    state_name: str
    fips: str
    total_population: int
    white_pct: float
    black_pct: float
    asian_pct: float
    hispanic_pct: float
    other_pct: float
    median_household_income: int
    college_degree_pct: float
    poverty_rate: float
    median_age: float


def _safe_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _safe_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


@router.get("/{state_abbr}/demographics", response_model=Demographics)
async def get_demographics(state_abbr: str):
    abbr = state_abbr.upper()
    fips = ABBR_TO_FIPS.get(abbr)
    if not fips:
        raise HTTPException(status_code=404, detail=f"Unknown state: {state_abbr}")

    if not settings.CENSUS_API_KEY:
        # Return plausible mock data when no API key is configured
        return Demographics(
            state_name=abbr,
            fips=fips,
            total_population=0,
            white_pct=0,
            black_pct=0,
            asian_pct=0,
            hispanic_pct=0,
            other_pct=0,
            median_household_income=0,
            college_degree_pct=0,
            poverty_rate=0,
            median_age=0,
        )

    url = "https://api.census.gov/data/2022/acs/acs5"
    params = {
        "get": ACS_VARS,
        "for": f"state:{fips}",
        "key": settings.CENSUS_API_KEY,
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        resp = await client.get(url, params=params)

    # Census API redirects to an HTML error page on bad key/params — treat as error
    content_type = resp.headers.get("content-type", "")
    if resp.status_code not in (200, 201) or "html" in content_type:
        detail = f"Census API returned {resp.status_code}. "
        if "html" in content_type:
            detail += "Key may be invalid or not yet activated (can take up to 1 hour after signup)."
        else:
            detail += resp.text[:200]
        raise HTTPException(status_code=502, detail=detail)

    try:
        rows = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail=f"Census API returned non-JSON: {resp.text[:200]}")

    if len(rows) < 2:
        raise HTTPException(status_code=502, detail="No data returned from Census API")

    headers, data = rows[0], rows[1]
    row = dict(zip(headers, data))

    total = _safe_int(row.get("B01003_001E", 0)) or 1
    white = _safe_int(row.get("B02001_002E", 0))
    black = _safe_int(row.get("B02001_003E", 0))
    asian = _safe_int(row.get("B02001_005E", 0))
    hispanic = _safe_int(row.get("B03003_003E", 0))
    other = max(0, total - white - black - asian - hispanic)

    edu_total = _safe_int(row.get("B15003_001E", 0)) or 1
    bachelors = _safe_int(row.get("B15003_022E", 0))

    pov_total = _safe_int(row.get("B17001_001E", 0)) or 1
    pov_below = _safe_int(row.get("B17001_002E", 0))

    return Demographics(
        state_name=row.get("NAME", abbr),
        fips=fips,
        total_population=total,
        white_pct=round(white / total * 100, 1),
        black_pct=round(black / total * 100, 1),
        asian_pct=round(asian / total * 100, 1),
        hispanic_pct=round(hispanic / total * 100, 1),
        other_pct=round(other / total * 100, 1),
        median_household_income=_safe_int(row.get("B19013_001E", 0)),
        college_degree_pct=round(bachelors / edu_total * 100, 1),
        poverty_rate=round(pov_below / pov_total * 100, 1),
        median_age=_safe_float(row.get("B01002_001E", 0)),
    )


@router.get("/{state_abbr}/district-plan")
async def get_district_plan(state_abbr: str):
    from models.agent.rl_agent import RLAgent

    token = state_abbr.upper()
    # Accept both 2-letter abbr ("CA") and 2-digit FIPS ("06")
    if token.isdigit():
        normalized = FIPS_TO_ABBR.get(token, token)
        fips = token.zfill(2)
    else:
        normalized = token
        fips = ABBR_TO_FIPS.get(normalized, "")

    if not fips:
        raise HTTPException(status_code=404, detail=f"Unknown state: {state_abbr}")

    # Return cached optimized plan if one exists
    cached = get_plan(normalized)
    if cached:
        return cached

    # No run yet — generate default round-robin plan so the map shows colors immediately
    try:
        n_districts = FIPS_TO_DISTRICTS.get(fips, 5)
        plan = RLAgent.default_plan(state_fips=fips, n_districts=n_districts)
        plan["state_abbr"] = normalized
        plan["n_districts"] = n_districts
        return plan
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
