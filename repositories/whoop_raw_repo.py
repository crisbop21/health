"""Raw Whoop payloads. Stored verbatim; never parsed in place.

One row per record, keyed by (endpoint, external_id), so re-syncing overlapping
date windows overwrites rather than duplicates. Recovery records have no `id`
of their own, so they key on `cycle_id`."""

from __future__ import annotations

from core.supabase_client import fetch_all, get_client

# Keep bulk upserts comfortably sized; a long backfill window can return
# hundreds of records per endpoint.
_UPSERT_CHUNK = 500


def _key(rec: dict) -> str | None:
    kid = rec.get("id")
    if kid is None:  # not falsy: 0 is a legitimate id
        kid = rec.get("cycle_id")
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
    written = 0
    for i in range(0, len(rows), _UPSERT_CHUNK):
        resp = (
            get_client()
            .table("whoop_raw")
            .upsert(rows[i : i + _UPSERT_CHUNK], on_conflict="endpoint,external_id")
            .execute()
        )
        written += len(resp.data or [])
    return written


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


def count() -> int:
    """Total stored raw rows (for the Settings status card)."""
    resp = get_client().table("whoop_raw").select("id", count="exact").limit(1).execute()
    return resp.count or 0


def records(endpoint: str, since: str | None = None) -> list[dict]:
    """Return stored Whoop records for an endpoint, oldest first, paging past
    the per-response row cap so long histories replay in full. With `since`,
    only rows recorded at/after that timestamp (the incremental-recompute
    path). Each row now holds a single record; legacy rows holding a
    `{records: [...]}` blob or a list are flattened for backward
    compatibility."""

    def query():
        q = get_client().table("whoop_raw").select("payload").eq("endpoint", endpoint)
        if since:
            q = q.gte("recorded_at", since)
        return q.order("ingested_at").order("id")

    out: list[dict] = []
    for row in fetch_all(query):
        payload = row.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("records"), list):
            out.extend(payload["records"])
        elif isinstance(payload, list):
            out.extend(payload)
        elif isinstance(payload, dict):
            out.append(payload)
    return out
