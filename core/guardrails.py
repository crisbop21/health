"""Structural guardrails on a generated plan. These never block generation —
plan_service logs each warning and proceeds (Claude's plan stands; the warnings
flag spots worth reviewing)."""

from __future__ import annotations

from datetime import date, timedelta

# Allow a little slack above the 10% weekly-increase rule before warning.
MILEAGE_TOLERANCE = 1.12
TAPER_WEEKS = 3


def _expand_blackouts(blackout_dates) -> set[str]:
    out: set[str] = set()
    for entry in blackout_dates or []:
        if isinstance(entry, str):
            out.add(entry)
        elif isinstance(entry, dict) and entry.get("start") and entry.get("end"):
            try:
                cur = date.fromisoformat(entry["start"])
                end = date.fromisoformat(entry["end"])
            except ValueError:
                continue
            while cur <= end:
                out.add(cur.isoformat())
                cur += timedelta(days=1)
    return out


def _iso_week(day: str) -> tuple[int, int] | None:
    try:
        y, w, _ = date.fromisoformat(day).isocalendar()
        return (y, w)
    except ValueError:
        return None


def _weekly_mileage(plan_rows: list[dict]) -> dict[tuple[int, int], float]:
    weekly: dict[tuple[int, int], float] = {}
    for row in plan_rows:
        wk = _iso_week(row.get("date"))
        if wk is None:
            continue
        weekly[wk] = weekly.get(wk, 0.0) + (row.get("planned_distance_km") or 0.0)
    return weekly


def check_plan(plan_rows: list[dict], goal: dict) -> list[dict]:
    """Return a list of warning dicts (type, message, ...). Empty means clean."""
    warnings: list[dict] = []
    blackout = _expand_blackouts(goal.get("blackout_dates"))

    for row in plan_rows:
        d = row.get("date")
        if d in blackout and (row.get("planned_workout_type") or "").lower() != "rest":
            warnings.append(
                {"type": "blackout", "date": d, "message": f"Workout scheduled on blackout date {d}"}
            )

    weekly = _weekly_mileage(plan_rows)
    weeks = sorted(weekly)

    for prev, cur in zip(weeks, weeks[1:]):
        p, c = weekly[prev], weekly[cur]
        if p > 0 and c > p * MILEAGE_TOLERANCE:
            warnings.append(
                {
                    "type": "mileage_jump",
                    "week": str(cur),
                    "message": f"Weekly mileage jumped {round((c / p - 1) * 100)}% (10% cap)",
                }
            )

    race_wk = _iso_week(goal.get("race_date")) if goal.get("race_date") else None
    if race_wk and weeks:
        taper = [w for w in weeks if w <= race_wk][-TAPER_WEEKS:]
        for prev, cur in zip(taper, taper[1:]):
            if weekly[cur] > weekly[prev]:
                warnings.append(
                    {
                        "type": "taper",
                        "week": str(cur),
                        "message": "Taper-week mileage increased vs the prior week",
                    }
                )

    return warnings
