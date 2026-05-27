"""Goal configuration. A single active goal at a time."""

from __future__ import annotations

from core.supabase_client import get_client


def get_active() -> dict | None:
    resp = (
        get_client()
        .table("goals")
        .select("*")
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def get(goal_id: str) -> dict | None:
    resp = get_client().table("goals").select("*").eq("id", goal_id).limit(1).execute()
    return resp.data[0] if resp.data else None
