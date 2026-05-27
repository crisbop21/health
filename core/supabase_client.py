"""Singleton Supabase client. Every repository imports get_client() from here;
nothing else constructs a connection."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from core.config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = settings.supabase_url
    key = settings.supabase_key
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set (see .env.example)."
        )
    return create_client(url, key)
