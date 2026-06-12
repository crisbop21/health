"""Race-time benchmarking from actual workouts: "if race day were today".

Uses the Riegel race-equivalency model, T2 = T1 * (D2/D1)^1.06 — the standard
way to translate a performance at one distance into another. Garmin activities
carry only whole-run average pace (no splits), so each qualifying run's total
time is converted into an equivalent race time and the fastest equivalent wins.

Projections prefer evidence close to the target distance: a marathon estimate
from a 30 km run beats one extrapolated from a 5K, even if the 5K's equivalent
is faster. The remaining stretch is surfaced as a confidence level.

Pure Python — no Streamlit. Never raises into the UI."""

from __future__ import annotations

from datetime import date, timedelta

from core import clock, logger, pace_zones
from repositories import goals_repo, workouts_repo

RIEGEL_EXPONENT = 1.06
TARGETS = {"10K": 10.0, "Half marathon": 21.0975, "Marathon": 42.195}
PR_DISTANCES = {"5K": 5.0, "10K": 10.0, "Half marathon": 21.0975, "Marathon": 42.195}
MIN_RUN_KM = 5.0  # below this a run says little about race fitness
WINDOW_DAYS = 90  # how far back "current fitness" looks
_CONFIDENCE_ORDER = ("high", "medium", "low")


def riegel(t1_seconds: float, d1_km: float, d2_km: float) -> float:
    """Equivalent time at d2 given t1 at d1."""
    return t1_seconds * (d2_km / d1_km) ** RIEGEL_EXPONENT


def _confidence(d1_km: float, d2_km: float) -> str:
    """How much the projection extrapolates: within 1.5x distance either way
    is solid Riegel territory; beyond 2.5x is a rough guide only."""
    ratio = max(d1_km, d2_km) / min(d1_km, d2_km)
    if ratio <= 1.5:
        return "high"
    if ratio <= 2.5:
        return "medium"
    return "low"


def _is_run(w: dict) -> bool:
    return "run" in (w.get("sport") or "").lower()


def _qualifying_runs(workouts: list[dict]) -> list[dict]:
    return [
        w for w in workouts
        if _is_run(w) and (w.get("distance_km") or 0) >= MIN_RUN_KM and w.get("duration_seconds")
    ]


def _best_projection(runs: list[dict], target_km: float) -> dict | None:
    """Fastest Riegel equivalent within the best available confidence tier."""
    tiers: dict[str, list] = {tier: [] for tier in _CONFIDENCE_ORDER}
    for w in runs:
        eq = riegel(w["duration_seconds"], w["distance_km"], target_km)
        tiers[_confidence(w["distance_km"], target_km)].append((eq, w))
    for tier in _CONFIDENCE_ORDER:
        if tiers[tier]:
            eq, w = min(tiers[tier], key=lambda pair: pair[0])
            return {
                "projected_seconds": int(round(eq)),
                "confidence": tier,
                "source": {
                    "date": w.get("date"),
                    "distance_km": w.get("distance_km"),
                    "duration_seconds": w.get("duration_seconds"),
                    "avg_pace": w.get("avg_pace"),
                },
            }
    return None


def _safe_goal() -> dict | None:
    try:
        return goals_repo.get_active()
    except Exception as exc:
        logger.warning("calc", "could not load goal for benchmark", {"error": str(exc)})
        return None


def race_projections(window_days: int = WINDOW_DAYS) -> dict:
    """Projected 10K / half / marathon times from the best efforts in the last
    `window_days`, with the goal-distance projection carrying the delta to the
    goal time. ok=False only on a read failure."""
    try:
        today = clock.local_today()
        start = (today - timedelta(days=window_days)).isoformat()
        runs = _qualifying_runs(workouts_repo.get_range(start, today.isoformat()))

        goal = _safe_goal() or {}
        goal_seconds = goal.get("goal_time_seconds")
        goal_km = goal.get("race_distance_km") or pace_zones.MARATHON_KM

        projections = []
        for label, km in TARGETS.items():
            entry: dict = {"label": label, "distance_km": km, "projected_seconds": None}
            best = _best_projection(runs, km)
            if best:
                entry.update(best)
                entry["projected"] = pace_zones.format_duration(best["projected_seconds"])
            if goal_seconds and abs(km - goal_km) < 0.5 and entry["projected_seconds"]:
                entry["goal_seconds"] = goal_seconds
                entry["delta_seconds"] = entry["projected_seconds"] - goal_seconds
            projections.append(entry)

        return {
            "ok": True,
            "projections": projections,
            "runs_considered": len(runs),
            "window_days": window_days,
        }
    except Exception as exc:
        logger.error("calc", "race_projections failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}


def projection_history(target_km: float, weeks: int = 26,
                       window_days: int = WINDOW_DAYS) -> dict:
    """Weekly "if race day were today" checkpoints — the fitness curve. Each
    point projects from the runs in the `window_days` before that week."""
    try:
        today = clock.local_today()
        earliest = (today - timedelta(days=weeks * 7 + window_days)).isoformat()
        runs = _qualifying_runs(workouts_repo.get_range(earliest, today.isoformat()))

        rows = []
        for i in range(weeks, -1, -1):
            checkpoint = today - timedelta(days=7 * i)
            lo = (checkpoint - timedelta(days=window_days)).isoformat()
            window = [w for w in runs if lo < (w.get("date") or "") <= checkpoint.isoformat()]
            best = _best_projection(window, target_km)
            if best:
                rows.append(
                    {"date": checkpoint.isoformat(),
                     "projected_seconds": best["projected_seconds"]}
                )
        return {"ok": True, "rows": rows, "target_km": target_km}
    except Exception as exc:
        logger.error("calc", "projection_history failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}


def personal_records() -> dict:
    """All-time bests from the workout history: fastest equivalent time per
    classic distance (only from runs at/near that distance — no upscaling),
    longest run, and biggest week."""
    try:
        today = clock.local_today().isoformat()
        runs = _qualifying_runs(workouts_repo.get_range("2000-01-01", today))

        records: dict[str, dict | None] = {}
        for label, km in PR_DISTANCES.items():
            candidates = [w for w in runs if w["distance_km"] >= km * 0.95]
            best = None
            for w in candidates:
                eq = riegel(w["duration_seconds"], w["distance_km"], km)
                if best is None or eq < best[0]:
                    best = (eq, w)
            records[label] = (
                {
                    "seconds": int(round(best[0])),
                    "formatted": pace_zones.format_duration(best[0]),
                    "date": best[1].get("date"),
                    "from_km": best[1].get("distance_km"),
                }
                if best
                else None
            )

        longest = max(runs, key=lambda w: w["distance_km"], default=None)
        weekly: dict[str, float] = {}
        for w in runs:
            d = w.get("date")
            if not d:
                continue
            day = date.fromisoformat(d)
            monday = (day - timedelta(days=day.weekday())).isoformat()
            weekly[monday] = weekly.get(monday, 0.0) + w["distance_km"]

        return {
            "ok": True,
            "records": records,
            "longest_run": (
                {"date": longest.get("date"), "distance_km": longest["distance_km"],
                 "duration_seconds": longest.get("duration_seconds")}
                if longest
                else None
            ),
            "biggest_week_km": round(max(weekly.values()), 1) if weekly else None,
            "total_runs": len(runs),
            "total_km": round(sum(w["distance_km"] for w in runs), 1),
        }
    except Exception as exc:
        logger.error("calc", "personal_records failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}
