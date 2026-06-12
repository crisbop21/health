"""Raw Garmin payloads. Stored verbatim; never parsed in place.

One row per logical record, keyed by (endpoint, external_id), so re-syncing a
day or activity overwrites rather than duplicates."""

from __future__ import annotations


from core.supabase_client import fetch_all, get_client, last_write_wins

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
    rows = last_write_wins(rows, key=lambda r: r["external_id"])
    for i in range(0, len(rows), _UPSERT_CHUNK):
        resp = (
            get_client()
            .table("garmin_raw")
            .upsert(rows[i : i + _UPSERT_CHUNK], on_conflict="endpoint,external_id")
            .execute()
        )
        written += len(resp.data or [])
    return written


def payloads(endpoint: str, since: str | None = None) -> list:
    """Return stored payloads for an endpoint, oldest first, paging past the
    per-response row cap so long histories replay in full. With `since`, only
    rows recorded at/after that timestamp (the incremental-recompute path)."""

    def query():
        q = get_client().table("garmin_raw").select("payload").eq("endpoint", endpoint)
        if since:
            q = q.gte("recorded_at", since)
        return q.order("ingested_at").order("id")

    return [row.get("payload") for row in fetch_all(query)]


def existing_ids(endpoint: str) -> set[str]:
    """The external_ids already stored for an endpoint. Lets a backfill skip
    re-fetching days it already holds (daily_stats keys on the date)."""
    rows = fetch_all(
        lambda: get_client()
        .table("garmin_raw")
        .select("external_id")
        .eq("endpoint", endpoint)
        .order("id")
    )
    return {row["external_id"] for row in rows if row.get("external_id")}


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
