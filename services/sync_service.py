"""Device sync orchestration. Pulls raw data from the device clients and writes
it to the raw tables, logging each step. Never raises into the UI — failures
are logged and surfaced through the return value.

The range functions accept an arbitrary number of days back so the same code
path serves both the routine 7-day sync and a one-off year-long backfill. Raw
rows are stored verbatim and recompute is idempotent (daily_metrics upsert by
date, workouts deleted-then-reinserted), so re-running a backfill is safe."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from clients import garmin_client, whoop_client
from core import logger
from repositories import garmin_raw_repo, whoop_raw_repo


def sync_garmin_range(days: int = 7, client=None) -> dict:
    """Sync `days` of Garmin activities and daily stats into garmin_raw,
    idempotently — re-syncing a day or activity overwrites instead of
    duplicating. Activities come in one date-range call; daily stats are per-day
    endpoints, so we loop day by day. A single bad day (e.g. a transient 429) is
    logged and skipped rather than aborting the whole range. Returns a summary
    dict; on failure, ok=False."""
    now = datetime.now(timezone.utc).isoformat()
    written = 0
    failed_days = 0
    try:
        client = client or garmin_client.login()

        activities = garmin_client.fetch_recent_activities(days=days, client=client)
        written += garmin_raw_repo.upsert_records(
            activities, endpoint="activities", key_field="activityId", recorded_at=now
        )

        for offset in range(days):
            day = (date.today() - timedelta(days=offset)).isoformat()
            try:
                stats = garmin_client.fetch_daily_stats(day, client=client)
            except Exception as exc:
                failed_days += 1
                logger.warning("garmin", f"daily stats failed for {day}", {"error": str(exc)})
                continue
            written += garmin_raw_repo.upsert_records(
                [stats], endpoint="daily_stats", key_field="date", recorded_at=now
            )

        logger.info(
            "garmin", "sync_garmin_range complete",
            {"days": days, "rows_written": written, "failed_days": failed_days},
        )
        return {"ok": True, "rows_written": written, "failed_days": failed_days}
    except Exception as exc:
        logger.error("garmin", "sync_garmin_range failed", {"days": days, "error": str(exc)})
        return {"ok": False, "error": str(exc), "rows_written": written}


def _whoop_windows(days: int, window: int = 30):
    """Yield non-overlapping (start, end) ISO-8601 UTC pairs spanning the last
    `days`, chunked into `window`-day slices. Chunking keeps each Whoop request
    well inside the client's pagination cap (25/page, 10 pages)."""
    end = date.today()
    start = end - timedelta(days=days)
    cur = start
    while cur <= end:
        w_end = min(cur + timedelta(days=window - 1), end)
        yield (
            cur.isoformat() + "T00:00:00.000Z",
            w_end.isoformat() + "T23:59:59.999Z",
        )
        cur = w_end + timedelta(days=1)


def sync_whoop_range(days: int = 7) -> dict:
    """Sync `days` of Whoop recovery, sleep, workout, and cycle data into
    whoop_raw, idempotently (one row per record, keyed by id/cycle_id, so
    overlapping windows don't duplicate). Returns a summary dict; on failure,
    ok=False with the error."""
    now = datetime.now(timezone.utc).isoformat()
    written = 0
    try:
        endpoints = [
            ("recovery", whoop_client.fetch_recoveries),
            ("sleep", whoop_client.fetch_sleeps),
            ("workout", whoop_client.fetch_workouts),
            ("cycle", whoop_client.fetch_cycles),
        ]
        for endpoint, fetch in endpoints:
            for start, end in _whoop_windows(days):
                payload = fetch(start, end)
                records = payload.get("records", []) if isinstance(payload, dict) else payload
                written += whoop_raw_repo.upsert_records(records, endpoint=endpoint, recorded_at=now)

        logger.info("whoop", "sync_whoop_range complete", {"days": days, "rows_written": written})
        return {"ok": True, "rows_written": written}
    except Exception as exc:
        logger.error("whoop", "sync_whoop_range failed", {"days": days, "error": str(exc)})
        return {"ok": False, "error": str(exc), "rows_written": written}


def sync_garmin_last_7_days() -> dict:
    return sync_garmin_range(7)


def sync_whoop_last_7_days() -> dict:
    return sync_whoop_range(7)


def sync_all_devices(days: int = 7) -> dict:
    """Sync both devices over the last `days`. Each device's failure is
    isolated; the overall ok is true only if both succeeded."""
    garmin = sync_garmin_range(days)
    whoop = sync_whoop_range(days)
    return {"ok": garmin["ok"] and whoop["ok"], "garmin": garmin, "whoop": whoop}


def backfill_all_devices(days: int = 365) -> dict:
    """One-off historical pull: sync both devices over the last `days`
    (default a full year). Same isolation rules as sync_all_devices."""
    logger.info("sync", "backfill_all_devices starting", {"days": days})
    return sync_all_devices(days)
