"""The morning go/no-go: synthesizes recovery, sleep, and training load into a
single verdict for the Today screen, plus race-week taper status. The point is
to answer "should I do today's hard session?" in one glance instead of four
charts. Pure Python — no Streamlit. Never raises into the UI."""

from __future__ import annotations

from datetime import date

from core import clock, logger
from repositories import daily_metrics_repo, goals_repo
from services import dashboard_service

# Verdict thresholds. Recovery bands follow Whoop's own traffic light;
# the ACWR bands are the standard 0.8–1.3 sweet spot with >1.5 as the
# widely cited injury-risk spike.
RECOVERY_RED = 33
RECOVERY_AMBER = 66
SLEEP_AMBER_HOURS = 6.5
ACWR_HIGH_AMBER = 1.3
ACWR_RED = 1.5
ACWR_LOW_AMBER = 0.8


def _verdict(recovery, sleep_hours, acwr) -> tuple[str, list[str]]:
    """Pure rule evaluation -> (green|amber|red|unknown, reasons)."""
    if recovery is None and sleep_hours is None and acwr is None:
        return "unknown", ["No recent metrics — sync your devices."]

    reasons: list[str] = []
    level = "green"

    def flag(new_level: str, reason: str):
        nonlocal level
        reasons.append(reason)
        if new_level == "red" or level == "red":
            level = "red"
        elif new_level == "amber" and level == "green":
            level = "amber"

    if recovery is not None:
        if recovery < RECOVERY_RED:
            flag("red", f"Recovery is in the red ({recovery:.0f}). Make today easy or rest.")
        elif recovery < RECOVERY_AMBER:
            flag("amber", f"Recovery is moderate ({recovery:.0f}). Keep intensity in check.")
    if sleep_hours is not None and sleep_hours < SLEEP_AMBER_HOURS:
        flag("amber", f"Short sleep ({sleep_hours:.1f} h).")
    if acwr is not None:
        if acwr > ACWR_RED:
            flag("red", f"Training load spike (ACWR {acwr:.2f}) — high injury risk; back off.")
        elif acwr > ACWR_HIGH_AMBER:
            flag("amber", f"Load is climbing fast (ACWR {acwr:.2f}).")
        elif acwr < ACWR_LOW_AMBER:
            flag("amber", f"Load is well below your base (ACWR {acwr:.2f}) — fitness is detraining.")

    return level, reasons


def readiness() -> dict:
    """Verdict + reasons + the inputs, for the Today banner. Missing inputs
    degrade the verdict to what's known; failures degrade to unknown."""
    recovery = sleep_hours = hrv = acwr = None
    as_of = None
    try:
        recent = daily_metrics_repo.get_recent(1)
        if recent:
            row = recent[-1]
            as_of = row.get("date")
            recovery = row.get("recovery_score")
            sleep_hours = row.get("sleep_hours")
            hrv = row.get("hrv_ms")
    except Exception as exc:
        logger.warning("calc", "readiness: metrics unavailable", {"error": str(exc)})

    load = dashboard_service.training_load(days=60)
    if load.get("ok"):
        ratios = [r["acwr"] for r in load.get("rows", []) if r.get("acwr") is not None]
        acwr = ratios[-1] if ratios else None

    verdict, reasons = _verdict(recovery, sleep_hours, acwr)
    return {
        "ok": True,
        "verdict": verdict,
        "reasons": reasons,
        "date": as_of,
        "metrics": {
            "recovery_score": recovery,
            "sleep_hours": sleep_hours,
            "hrv_ms": hrv,
            "acwr": acwr,
        },
    }


def taper_status() -> dict:
    """Days to race and whether load is actually coming down (acute < chronic),
    for race-week mode. race fields are None when no goal/race date is set."""
    try:
        goal = goals_repo.get_active()
    except Exception as exc:
        logger.warning("calc", "taper_status: goal unavailable", {"error": str(exc)})
        goal = None

    race_date = (goal or {}).get("race_date")
    if not race_date:
        return {"ok": True, "days_to_race": None, "race_week": False, "tapering": None}

    try:
        days_to_race = (date.fromisoformat(race_date) - clock.local_today()).days
    except ValueError:
        return {"ok": True, "days_to_race": None, "race_week": False, "tapering": None}

    tapering = None
    load = dashboard_service.training_load(days=60)
    rows = load.get("rows") or []
    if load.get("ok") and rows:
        last = rows[-1]
        if last.get("acute") is not None and last.get("chronic") is not None:
            tapering = last["acute"] < last["chronic"]

    return {
        "ok": True,
        "days_to_race": days_to_race,
        "race_week": 0 <= days_to_race <= 14,
        "tapering": tapering,
    }
