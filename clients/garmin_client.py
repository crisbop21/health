"""Garmin Connect client (unofficial python-garminconnect). The only module
that talks to Garmin. Returns raw payloads; parsing happens at the derived
layer. If the unofficial library breaks on a Garmin site change, the fallback
is manual FIT import or Whoop-only mode (see the technical brief)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from core import logger
from core.config import settings


def login():
    """Authenticate and return a logged-in Garmin client. MFA-protected
    accounts may require interactive handling; revisit if login starts
    returning a challenge instead of a session."""
    from garminconnect import Garmin

    missing = settings.missing(["garmin_email", "garmin_password"])
    if missing:
        raise RuntimeError(f"Garmin credentials not configured: {missing}")

    client = Garmin(settings.garmin_email, settings.garmin_password)
    client.login()
    logger.info("garmin", "login succeeded")
    return client


def fetch_recent_activities(days: int = 7, client=None) -> list[Any]:
    client = client or login()
    end = date.today()
    start = end - timedelta(days=days)
    activities = client.get_activities_by_date(start.isoformat(), end.isoformat())
    logger.info(
        "garmin",
        "fetched activities",
        {"days": days, "count": len(activities or [])},
    )
    return activities or []


def fetch_daily_stats(day: str, client=None) -> dict[str, Any]:
    """Bundle the per-day endpoints into one raw payload. Each value is the
    untouched Garmin response (or None if that endpoint failed for the day)."""
    client = client or login()

    def _safe(fn, *args):
        try:
            return fn(*args)
        except Exception as exc:  # one endpoint failing shouldn't sink the day
            logger.warning("garmin", f"{fn.__name__} failed for {day}", {"error": str(exc)})
            return None

    return {
        "date": day,
        "stats": _safe(client.get_stats, day),
        "sleep": _safe(client.get_sleep_data, day),
        "hrv": _safe(client.get_hrv_data, day),
        "resting_hr": _safe(client.get_rhr_day, day),
    }
