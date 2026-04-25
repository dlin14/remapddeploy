"""Legislative Liaison MCP tool wrapper.

This is a lightweight MCP-style server abstraction for hackathon use.
It exposes deterministic tool methods with provenance metadata so
LangGraph nodes can reference auditable data sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any

import httpx

from core.config import settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    payload: dict[str, Any]
    provenance: dict[str, Any]


class LegislativeMCPServer:
    """MCP wrapper around external data tools and audit verification."""

    def __init__(self):
        self._audit: dict[str, dict[str, Any]] = {}

    async def fetch_census_metrics(
        self, state_fips: str, district_map: dict[str, int], year: int = 2022
    ) -> ToolResult:
        """Fetch a compact Census metric bundle with provenance metadata."""
        url = f"https://api.census.gov/data/{year}/acs/acs5"
        params = {
            "get": "NAME,B01003_001E,B19013_001E,B17001_002E,B17001_001E",
            "for": f"state:{state_fips}",
        }
        if settings.CENSUS_API_KEY:
            params["key"] = settings.CENSUS_API_KEY

        success = True
        payload: dict[str, Any]
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                resp = await client.get(url, params=params)
            if resp.status_code != 200:
                success = False
                payload = {
                    "error": f"Census response {resp.status_code}",
                    "state_fips": state_fips,
                    "fallback": True,
                    "district_count": len(set(district_map.values())),
                }
            else:
                rows = resp.json()
                headers, data = rows[0], rows[1]
                row = dict(zip(headers, data))
                total = int(row.get("B01003_001E", 0) or 0)
                pov_n = int(row.get("B17001_002E", 0) or 0)
                pov_d = int(row.get("B17001_001E", 0) or 1)
                payload = {
                    "state_name": row.get("NAME", state_fips),
                    "state_fips": state_fips,
                    "total_population": total,
                    "median_household_income": int(row.get("B19013_001E", 0) or 0),
                    "poverty_rate": round(100.0 * pov_n / max(1, pov_d), 2),
                    "district_count": len(set(district_map.values())),
                }
        except Exception as exc:  # pragma: no cover - defensive fallback
            success = False
            payload = {
                "error": str(exc),
                "state_fips": state_fips,
                "fallback": True,
                "district_count": len(set(district_map.values())),
            }

        digest_source = f"{state_fips}|{sorted(district_map.items())}|{payload}".encode("utf-8")
        payload_hash = hashlib.sha256(digest_source).hexdigest()[:16]
        tool_call_id = f"census_{payload_hash}"
        provenance = {
            "tool_call_id": tool_call_id,
            "source": "US Census Bureau ACS 5-Year",
            "queried_at": _utc_now(),
            "dataset_year": year,
            "payload_hash": payload_hash,
        }
        self._audit[tool_call_id] = {
            "tool_name": "fetch_census_metrics",
            "success": success,
            "payload": payload,
            "provenance": provenance,
        }
        return ToolResult(
            tool_name="fetch_census_metrics",
            success=success,
            payload=payload,
            provenance=provenance,
        )

    async def verify_audit_trail(self, tool_call_id: str) -> ToolResult:
        """Verify a prior tool call provenance entry."""
        record = self._audit.get(tool_call_id)
        success = record is not None
        payload = {
            "verified": success,
            "tool_call_id": tool_call_id,
            "record": record,
        }
        provenance = {
            "tool_call_id": f"verify_{tool_call_id}",
            "source": "LegislativeMCPServer.audit_store",
            "queried_at": _utc_now(),
            "payload_hash": hashlib.sha256(str(payload).encode("utf-8")).hexdigest()[:16],
        }
        self._audit[provenance["tool_call_id"]] = {
            "tool_name": "verify_audit_trail",
            "success": success,
            "payload": payload,
            "provenance": provenance,
        }
        return ToolResult(
            tool_name="verify_audit_trail",
            success=success,
            payload=payload,
            provenance=provenance,
        )


mcp_server = LegislativeMCPServer()
