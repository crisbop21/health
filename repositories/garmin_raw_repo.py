"""Raw Garmin payloads. Stored verbatim; never parsed in place.

One row per logical record, keyed by (endpoint, external_id), so re-syncing a
day or activity overwrites rather than duplicates."""

from __future__ import annotations

from typing import Any

from core.supabase_client import fetch_all, get_client

# Keep bulk upserts comfortably sized; a multi-year activity backfill can be
# thousands of rows, too big for one request.
_UPSERT_CHUNK = 500


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
    written = 0
    for i in range(0, len(rows), _UPSERT_CHUNK):
        resp = (
            get_client()
            .table("garmin_raw")
            .upsert(rows[i : i + _UPSERT_CHUNK], on_conflict="endpoint,external_id")
            .execute()
        )
        written += len(resp.data or [])
    return written


def payloads(endpoint: str) -> list:
    """Return all stored payloads for an endpoint, oldest first, paging past
    the per-response row cap so long histories replay in full."""
    rows = fetch_all(
        lambda: get_client()
        .table("garmin_raw")
        .select("payload")
        .eq("endpoint", endpoint)
        .order("ingested_at")
        .order("id")
    )
    return [row.get("payload") for row in rows]


def count() -> int:
    """Total stored raw rows (for the Settings status card)."""
    resp = get_client().table("garmin_raw").select("id", count="exact").limit(1).execute()
    return resp.count or 0


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
