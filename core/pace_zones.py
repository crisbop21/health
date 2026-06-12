"""Deterministic pace-zone calculations from a goal finish time. Running-only;
returns nothing for other sports. Used to anchor Claude's plan and as a
reference for guardrail checks."""

from __future__ import annotations

MARATHON_KM = 42.195

# Pace per zone relative to marathon pace (seconds/km). >1 is slower, <1 faster.
ZONE_MULTIPLIERS = {
    "recovery": 1.25,
    "easy": 1.15,
    "marathon": 1.00,
    "threshold": 0.92,
    "interval": 0.85,
}


def marathon_pace_sec_per_km(goal_time_seconds: int | None) -> float | None:
    if not goal_time_seconds or goal_time_seconds <= 0:
        return None
    return goal_time_seconds / MARATHON_KM


def pace_zones(goal_time_seconds: int | None, sport: str = "running") -> dict[str, float]:
    if (sport or "running").lower() != "running":
        return {}
    mp = marathon_pace_sec_per_km(goal_time_seconds)
    if mp is None:
        return {}
    return {zone: round(mp * factor, 1) for zone, factor in ZONE_MULTIPLIERS.items()}


def format_pace(sec_per_km: float | None) -> str | None:
    if sec_per_km is None:
        return None
    minutes = int(sec_per_km // 60)
    seconds = int(round(sec_per_km - minutes * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/km"


def pace_zones_formatted(goal_time_seconds: int | None, sport: str = "running") -> dict[str, str]:
    return {zone: format_pace(p) for zone, p in pace_zones(goal_time_seconds, sport).items()}


def format_duration(seconds: float | None) -> str | None:
    """A race/run time as H:MM:SS (or M:SS under an hour)."""
    if seconds is None:
        return None
    s = int(round(seconds))
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
