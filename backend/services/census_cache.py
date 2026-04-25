"""Fetches and caches real county-level population + minority share from Census ACS 5-yr.

The cache is process-scoped (in-memory dict).  The first optimizer run for a state
triggers a single Census API call; all subsequent runs for the same state reuse the
cached values.  Falls back to an empty dict when no API key is configured, letting
`_build_county_features` use its deterministic synthetic fallback.
"""

from __future__ import annotations

from typing import Any
import requests

from core.config import settings

# county_fips (5-digit str) → {"population": int, "minority_share": float}
_cache: dict[str, dict[str, Any]] = {}

# ACS variables: total pop + white-alone (minority share = 1 - white/total)
_ACS_VARS = "B01003_001E,B02001_002E"
_ACS_URL = "https://api.census.gov/data/2022/acs/acs5"


def get_county_data(state_fips: str) -> dict[str, dict[str, Any]]:
    """Return {county_fips: {population, minority_share}} for every county in the state.

    Returns an empty dict if no Census API key is configured or the request fails,
    in which case the optimizer falls back to deterministic synthetic data.
    """
    if state_fips in _cache:
        return _cache[state_fips]

    api_key = settings.CENSUS_API_KEY
    if not api_key:
        return {}

    try:
        resp = requests.get(
            _ACS_URL,
            params={
                "get": _ACS_VARS,
                "for": "county:*",
                "in": f"state:{state_fips}",
                "key": api_key,
            },
            timeout=15,
        )
        content_type = resp.headers.get("content-type", "")
        if resp.status_code != 200 or "html" in content_type:
            return {}

        rows = resp.json()
        if len(rows) < 2:
            return {}

        headers = rows[0]
        result: dict[str, dict[str, Any]] = {}

        for row in rows[1:]:
            data = dict(zip(headers, row))
            state_code = str(data.get("state", "")).zfill(2)
            county_code = str(data.get("county", "")).zfill(3)
            fips = state_code + county_code

            try:
                total = int(data["B01003_001E"])
                white = int(data["B02001_002E"])
            except (KeyError, ValueError, TypeError):
                continue

            if total <= 0:
                continue

            minority_share = max(0.0, min(1.0, (total - white) / total))
            result[fips] = {
                "population": total,
                "minority_share": round(minority_share, 4),
            }

        _cache[state_fips] = result
        return result

    except Exception:
        return {}
