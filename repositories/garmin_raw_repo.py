"""Raw Garmin payloads. Stored verbatim; never parsed in place."""

from __future__ import annotations

from typing import Any

from core.supabase_client import get_client


def insert(payload: Any, endpoint: str, recorded_at: str | None = None) -> dict:
    row = {"payload": payload, "endpoint": endpoint, "recorded_at": recorded_at}
    resp = get_client().table("garmin_raw").insert(row).execute()
    return resp.data[0] if resp.data else row


def payloads(endpoint: str) -> list:
    """Return the stored payloads for an endpoint, oldest first."""
    resp = (
        get_client()
        .table("garmin_raw")
        .select("payload")
        .eq("endpoint", endpoint)
        .order("ingested_at")
        .execute()
    )
    return [row.get("payload") for row in (resp.data or [])]


def latest_ingested_at() -> str | None:
    resp = (
        get_client()
        .table("garmin_raw")
        .select("ingested_at")
        .order("ingested_at", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0]["ingested_at"] if resp.data else None
