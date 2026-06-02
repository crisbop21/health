"""Garmin Connect client (unofficial python-garminconnect). The only module
that talks to Garmin. Returns raw payloads; parsing happens at the derived
layer. If the unofficial library breaks on a Garmin site change, the fallback
is manual FIT import or Whoop-only mode (see the technical brief)."""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

from core import logger
from core.config import settings
from repositories import oauth_tokens_repo

PROVIDER = "garmin"

# Garmin throttles bursts of requests (a 365-day backfill makes ~4 calls/day).
# Back off and retry on rate limits so throttled days complete instead of being
# stored empty, which otherwise leaves only the most-recent days populated.
_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_BASE_DELAY = 4.0  # seconds; doubles each retry (4, 8, 16, 32)


def _is_rate_limit(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return (
        "toomanyrequests" in name
        or "429" in msg
        or "too many requests" in msg
        or "rate limit" in msg
    )


def _call(fn, *args):
    """Call a Garmin endpoint, backing off and retrying on rate limits."""
    delay = _RATE_LIMIT_BASE_DELAY
    for attempt in range(_RATE_LIMIT_RETRIES):
        try:
            return fn(*args)
        except Exception as exc:
            if _is_rate_limit(exc) and attempt < _RATE_LIMIT_RETRIES - 1:
                logger.warning(
                    "garmin",
                    f"rate limited on {getattr(fn, '__name__', 'call')}; backing off {delay}s",
                )
                time.sleep(delay)
                delay *= 2
                continue
            raise
    return fn(*args)  # pragma: no cover - exhausted retries re-raise above


def _stored_token() -> str | None:
    """The saved Garmin OAuth token blob: the GARMIN_TOKENS env value if set,
    otherwise whatever a prior login persisted in oauth_tokens."""
    if settings.garmin_tokens:
        return settings.garmin_tokens
    try:
        row = oauth_tokens_repo.get(PROVIDER)
    except Exception as exc:
        logger.warning("garmin", "could not read stored Garmin token", {"error": str(exc)})
        return None
    return row.get("access_token") if row else None


def _store_token(token: str) -> None:
    try:
        oauth_tokens_repo.upsert(PROVIDER, access_token=token, refresh_token=None, expires_at=None)
    except Exception as exc:
        logger.warning("garmin", "could not persist Garmin token", {"error": str(exc)})


def _resume(token: str):
    """Build a Garmin client from a saved garth token blob — no password login,
    so Garmin's datacenter-IP CAPTCHA is never hit."""
    from garminconnect import Garmin

    client = Garmin()
    client.garth.loads(token)
    return client


def login():
    """Return a logged-in Garmin client. Prefers a saved OAuth token (which
    avoids the CAPTCHA Garmin throws at password logins from cloud IPs); falls
    back to email/password and persists the resulting token for next time.

    Generate a token without a cloud CAPTCHA by running
    `python -m scripts.garmin_login` locally."""
    token = _stored_token()
    if token:
        try:
            client = _resume(token)
            logger.info("garmin", "resumed session from saved token")
            return client
        except Exception as exc:
            logger.warning(
                "garmin", "saved token unusable; trying password login", {"error": str(exc)}
            )

    missing = settings.missing(["garmin_email", "garmin_password"])
    if missing:
        raise RuntimeError(
            f"Garmin not configured: no saved token and missing {missing}. "
            "Run `python -m scripts.garmin_login` locally to mint a token."
        )

    from garminconnect import Garmin

    client = Garmin(settings.garmin_email, settings.garmin_password)
    try:
        client.login()
    except Exception as exc:
        # Garmin blocks password logins from cloud IPs (CAPTCHA / HTTP 403).
        # Surface the real fix instead of the cryptic transport error.
        raise RuntimeError(
            f"Garmin password login failed ({exc}). Garmin blocks logins from "
            "datacenter IPs — mint a token locally with "
            "`python -m scripts.garmin_login` and set GARMIN_TOKENS (it's also "
            "saved to the DB for the app to reuse)."
        ) from exc
    logger.info("garmin", "login succeeded (password)")
    try:
        _store_token(client.garth.dumps())
    except Exception as exc:
        logger.warning("garmin", "could not dump Garmin token", {"error": str(exc)})
    return client


def fetch_recent_activities(days: int = 7, client=None) -> list[Any]:
    client = client or login()
    end = date.today()
    start = end - timedelta(days=days)
    activities = _call(client.get_activities_by_date, start.isoformat(), end.isoformat())
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
            return _call(fn, *args)  # retries rate limits before giving up
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
