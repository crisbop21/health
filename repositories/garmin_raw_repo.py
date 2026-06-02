"""Raw Garmin payloads. Stored verbatim; never parsed in place.

One row per logical record, keyed by (endpoint, external_id), so re-syncing a
day or activity overwrites rather than duplicates."""

from __future__ import annotations

from typing import Any

from core.supabase_client import get_client


def upsert_records(records: list, endpoint: str, key_field: str, recorded_at: str | None = None) -> int:
    """Upsert one row per record, using record[key_field] as the dedupe key.
    Records missing the key (or not dicts) are skipped."""
    rows = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        kid = rec.get(key_field)
        if kid is None:
            continue
        rows.append(
            {
                "endpoint": endpoint,
                "external_id": str(kid),
                "payload": rec,
                "recorded_at": recorded_at,
            }
        )
    if not rows:
        return 0
    resp = (
        get_client()
        .table("garmin_raw")
        .upsert(rows, on_conflict="endpoint,external_id")
        .execute()
    )
    return len(resp.data or [])


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
