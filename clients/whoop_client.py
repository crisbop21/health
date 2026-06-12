"""Whoop Developer API v2 client (OAuth 2.0). The only module that talks to
Whoop. Handles the authorization-code flow, refresh, and paginated reads.
Returns raw payloads; parsing happens in metrics_service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core import logger
from core.config import settings
from repositories import oauth_tokens_repo

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
API_BASE = "https://api.prod.whoop.com/developer/v2"
SCOPES = "offline read:recovery read:sleep read:workout read:cycles read:profile"
PROVIDER = "whoop"


# --- OAuth ---------------------------------------------------------------

def authorize_url(state: str) -> str:
    from urllib.parse import urlencode

    params = {
        "client_id": settings.whoop_client_id,
        "redirect_uri": settings.whoop_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _token_request(data: dict) -> dict:
    import requests

    resp = requests.post(TOKEN_URL, data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _store(token: dict) -> None:
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(token.get("expires_in", 3600)))
    ).isoformat()
    oauth_tokens_repo.upsert(
        PROVIDER,
        access_token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        expires_at=expires_at,
        scope=token.get("scope"),
    )


def exchange_code(code: str) -> dict:
    """One-time: exchange an authorization code for tokens and store them."""
    token = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.whoop_client_id,
            "client_secret": settings.whoop_client_secret,
            "redirect_uri": settings.whoop_redirect_uri,
        }
    )
    _store(token)
    logger.info("whoop", "exchanged authorization code for tokens")
    return token


def refresh() -> dict:
    row = oauth_tokens_repo.get(PROVIDER)
    if not row or not row.get("refresh_token"):
        raise RuntimeError("Whoop is not connected (no refresh token).")
    token = _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": row["refresh_token"],
            "client_id": settings.whoop_client_id,
            "client_secret": settings.whoop_client_secret,
            "scope": SCOPES,
        }
    )
    # Whoop may omit a new refresh token on refresh; keep the existing one.
    if not token.get("refresh_token"):
        token["refresh_token"] = row["refresh_token"]
    _store(token)
    logger.info("whoop", "refreshed access token")
    return token


def _expired(expires_at: str | None) -> bool:
    if not expires_at:
        return True
    try:
        dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Refresh a minute early to avoid edge-of-expiry failures.
    return dt <= datetime.now(timezone.utc) + timedelta(seconds=60)


def _valid_access_token() -> str:
    row = oauth_tokens_repo.get(PROVIDER)
    if not row:
        raise RuntimeError("Whoop is not connected.")
    if _expired(row.get("expires_at")):
        refresh()
        row = oauth_tokens_repo.get(PROVIDER)
    return row["access_token"]


def is_connected() -> bool:
    row = oauth_tokens_repo.get(PROVIDER)
    return bool(row and row.get("refresh_token"))


def token_expiry() -> str | None:
    """When the stored access token expires (it auto-refreshes; this is shown
    in Settings as a health signal)."""
    row = oauth_tokens_repo.get(PROVIDER)
    return row.get("expires_at") if row else None


# --- Reads ---------------------------------------------------------------

def _request_get(path: str, params: dict, token: str) -> dict:
    import requests

    resp = requests.get(
        API_BASE + path,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _is_auth_error(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None) == 401


def _collect(path: str, start: str, end: str, max_pages: int = 40) -> dict:
    """Fetch every page in [start, end]. max_pages is a runaway-loop guard, not
    a working limit — at 25 records/page it allows 1000 records per window,
    far beyond what a 30-day sync window can contain."""
    token = _valid_access_token()
    params = {"start": start, "end": end, "limit": 25}
    out: list = []
    refreshed = False
    pages = 0
    while pages < max_pages:
        try:
            data = _request_get(path, params, token)
        except Exception as exc:
            if _is_auth_error(exc) and not refreshed:
                logger.warning("whoop", "401 from API; refreshing token and retrying once")
                refresh()
                token = _valid_access_token()
                refreshed = True
                continue
            raise
        records = data.get("records", []) if isinstance(data, dict) else data
        out.extend(records or [])
        nxt = data.get("next_token") if isinstance(data, dict) else None
        if not nxt:
            break
        params["nextToken"] = nxt
        pages += 1
    return {"records": out}


def fetch_recoveries(start: str, end: str) -> dict:
    return _collect("/recovery", start, end)


def fetch_sleeps(start: str, end: str) -> dict:
    return _collect("/activity/sleep", start, end)


def fetch_workouts(start: str, end: str) -> dict:
    return _collect("/activity/workout", start, end)


def fetch_cycles(start: str, end: str) -> dict:
    return _collect("/cycle", start, end)
