"""Read access to debug_log. Writes go through core.logger.log; this repo is
for the Debug tab to query rows back."""

from __future__ import annotations

from typing import Any

from core.supabase_client import get_client


def recent(
    limit: int = 200,
    severity: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    query = get_client().table("debug_log").select("*")
    if severity:
        query = query.eq("severity", severity)
    if source:
        query = query.eq("source", source)
    resp = query.order("event_at", desc=True).limit(limit).execute()
    return resp.data or []
