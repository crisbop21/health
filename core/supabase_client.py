"""Singleton Supabase client. Every repository imports get_client() from here;
nothing else constructs a connection."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

from core.config import settings

# PostgREST caps a single response at 1000 rows. Reads that may exceed that
# (raw replays, full-history ranges) must page or they silently truncate.
PAGE_SIZE = 1000


def fetch_all(make_query: Callable, page_size: int = PAGE_SIZE) -> list[dict]:
    """Execute a query in `page_size` chunks until exhausted and return every
    row. `make_query` must build a fresh, deterministically-ordered query each
    call; .range() is applied here."""
    out: list[dict] = []
    offset = 0
    while True:
        resp = make_query().range(offset, offset + page_size - 1).execute()
        rows = resp.data or []
        out.extend(rows)
        if len(rows) < page_size:
            return out
        offset += page_size


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
