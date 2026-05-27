"""Singleton Supabase client. Every repository imports get_client() from here;
nothing else constructs a connection."""

from __future__ import annotations

from functools import lru_cache

from core.config import settings


@lru_cache(maxsize=1)
def get_client():
    # Import lazily so repositories can be imported without supabase installed
    # (keeps the service graph testable in a minimal environment).
    from supabase import create_client

    url = settings.supabase_url
    key = settings.supabase_key
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set (see secrets.toml.example)."
        )
    return create_client(url, key)
