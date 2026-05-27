"""Device sync orchestration. Pulls raw data from the device clients and writes
it to the raw tables, logging each step. Never raises into the UI — failures
are logged and surfaced through the return value."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from clients import garmin_client
from core import logger
from repositories import garmin_raw_repo


def sync_garmin_last_7_days() -> dict:
    """Sync the last 7 days of Garmin activities and daily stats into
    garmin_raw. Returns a summary dict; on failure, ok=False with the error."""
    now = datetime.now(timezone.utc).isoformat()
    written = 0
    try:
        client = garmin_client.login()

        activities = garmin_client.fetch_recent_activities(days=7, client=client)
        garmin_raw_repo.insert(payload=activities, endpoint="activities", recorded_at=now)
        written += 1

        for offset in range(7):
            day = (date.today() - timedelta(days=offset)).isoformat()
            stats = garmin_client.fetch_daily_stats(day, client=client)
            garmin_raw_repo.insert(
                payload=stats, endpoint="daily_stats", recorded_at=day
            )
            written += 1

        logger.info("garmin", "sync_garmin_last_7_days complete", {"rows_written": written})
        return {"ok": True, "rows_written": written}
    except Exception as exc:
        logger.error("garmin", "sync_garmin_last_7_days failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc), "rows_written": written}
