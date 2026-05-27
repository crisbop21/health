"""OAuth token storage, one row per provider."""

from __future__ import annotations

from datetime import datetime, timezone

from core.supabase_client import get_client


def get(provider: str) -> dict | None:
    resp = (
        get_client()
        .table("oauth_tokens")
        .select("*")
        .eq("provider", provider)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def upsert(
    provider: str,
    access_token: str | None,
    refresh_token: str | None,
    expires_at: str | None,
    scope: str | None = None,
) -> dict:
    row = {
        "provider": provider,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "scope": scope,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = get_client().table("oauth_tokens").upsert(row, on_conflict="provider").execute()
    return resp.data[0] if resp.data else row
