"""Home-timezone date handling. Device timestamps arrive in UTC; bucketing
them (and "today") in the athlete's home timezone keeps evening workouts and
overnight recoveries on the right calendar day instead of drifting to the UTC
date."""

from __future__ import annotations

from datetime import date, datetime, timezone, tzinfo

from core.config import settings


def _tz() -> tzinfo:
    name = settings.home_timezone
    if not name:
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def local_today() -> date:
    return datetime.now(_tz()).date()


def local_date_of(iso_ts: str | None) -> str | None:
    """The home-timezone calendar date (ISO) of a timestamp. Date-only and
    naive inputs (e.g. Garmin's startTimeLocal, already local) pass through;
    unparseable values fall back to their date prefix."""
    if not iso_ts:
        return None
    s = iso_ts.strip()
    if len(s) == 10:
        return s
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s[:10]
    if dt.tzinfo is None:
        return s[:10]
    return dt.astimezone(_tz()).date().isoformat()
