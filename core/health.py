"""Lightweight health checks for external systems. Used to render banners and
disable writes when something is down."""

from __future__ import annotations


def db_available() -> bool:
    """Cheap probe: count one debug_log row. Any exception means the DB is not
    reachable / not configured."""
    try:
        from core.supabase_client import get_client

        get_client().table("debug_log").select("id").limit(1).execute()
        return True
    except Exception:
        return False
