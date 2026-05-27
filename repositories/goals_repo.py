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


def create(goal: dict) -> dict:
    """Deactivate the current active goal and insert a new active one."""
    client = get_client()
    client.table("goals").update({"active": False}).eq("active", True).execute()
    row = {
        "sport": goal.get("sport", "running"),
        "race_date": goal.get("race_date"),
        "goal_time_seconds": goal.get("goal_time_seconds"),
        "days_per_week": goal.get("days_per_week"),
        "max_session_minutes": goal.get("max_session_minutes"),
        "time_windows": goal.get("time_windows") or {},
        "blackout_dates": goal.get("blackout_dates") or [],
        "active": True,
    }
    resp = client.table("goals").insert(row).execute()
    return resp.data[0] if resp.data else row
