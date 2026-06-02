"""Raw Whoop payloads. Stored verbatim; never parsed in place.

One row per record, keyed by (endpoint, external_id), so re-syncing overlapping
date windows overwrites rather than duplicates. Recovery records have no `id`
of their own, so they key on `cycle_id`."""

from __future__ import annotations

from core.supabase_client import get_client


def _key(rec: dict) -> str | None:
    kid = rec.get("id") or rec.get("cycle_id")
    return str(kid) if kid is not None else None


def upsert_records(records: list, endpoint: str, recorded_at: str | None = None) -> int:
    """Upsert one row per Whoop record. Records without a usable key are skipped."""
    rows = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        kid = _key(rec)
        if kid is None:
            continue
        rows.append(
            {
                "endpoint": endpoint,
                "external_id": kid,
                "payload": rec,
                "recorded_at": recorded_at,
            }
        )
    if not rows:
        return 0
    resp = (
        get_client()
        .table("whoop_raw")
        .upsert(rows, on_conflict="endpoint,external_id")
        .execute()
    )
    return len(resp.data or [])


def latest_ingested_at() -> str | None:
    resp = (
        get_client()
        .table("whoop_raw")
        .select("ingested_at")
        .order("ingested_at", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0]["ingested_at"] if resp.data else None


def records(endpoint: str) -> list[dict]:
    """Return the stored Whoop records for an endpoint, oldest first. Each row
    now holds a single record; legacy rows holding a `{records: [...]}` blob or
    a list are flattened for backward compatibility."""
    resp = (
        get_client()
        .table("whoop_raw")
        .select("payload")
        .eq("endpoint", endpoint)
        .order("ingested_at")
        .execute()
    )
    out: list[dict] = []
    for row in resp.data or []:
        payload = row.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("records"), list):
            out.extend(payload["records"])
        elif isinstance(payload, list):
            out.extend(payload)
        elif isinstance(payload, dict):
            out.append(payload)
    return out
