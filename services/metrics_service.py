"""Derive source-resolved daily metrics and workouts from the raw tables.

Source-of-truth rules (from the technical brief):
- HRV, recovery, sleep: Whoop wins; Garmin is fallback.
- Workouts, distance, pace: Garmin wins.

A recompute replays all stored raw data, so derived rows can be rebuilt at any
time. Parsers are defensive about missing keys — a device only contributes the
fields it actually returned."""

from __future__ import annotations

from core import logger
from repositories import (
    daily_metrics_repo,
    garmin_raw_repo,
    whoop_raw_repo,
    workouts_repo,
)


def _date_of(iso_ts: str | None) -> str | None:
    return iso_ts[:10] if iso_ts else None


def _empty(day: str) -> dict:
    return {
        "date": day,
        "hrv_ms": None,
        "resting_hr": None,
        "sleep_hours": None,
        "recovery_score": None,
        "strain": None,
        "source_hrv": None,
        "source_sleep": None,
    }


# --- Whoop parsers -------------------------------------------------------

def _whoop_recovery(rec: dict) -> dict:
    score = rec.get("score") or {}
    return {
        "hrv_ms": score.get("hrv_rmssd_milli"),
        "resting_hr": score.get("resting_heart_rate"),
        "recovery_score": score.get("recovery_score"),
    }


def _whoop_sleep_hours(rec: dict) -> float | None:
    score = rec.get("score") or {}
    summary = score.get("stage_summary") or {}
    in_bed = summary.get("total_in_bed_time_milli")
    awake = summary.get("total_awake_time_milli") or 0
    if in_bed is not None:
        return round((in_bed - awake) / 3_600_000, 2)
    return None


def _whoop_strain(rec: dict) -> float | None:
    return (rec.get("score") or {}).get("strain")


# --- Garmin parsers (best-effort; shapes vary by Garmin) -----------------

def _garmin_resting_hr(payload: dict) -> float | None:
    rhr = payload.get("resting_hr") or {}
    if isinstance(rhr, dict) and rhr.get("restingHeartRate") is not None:
        return rhr["restingHeartRate"]
    stats = payload.get("stats") or {}
    return stats.get("restingHeartRate")


def _garmin_sleep_hours(payload: dict) -> float | None:
    sleep = payload.get("sleep") or {}
    dto = sleep.get("dailySleepDTO") or {}
    secs = dto.get("sleepTimeSeconds")
    return round(secs / 3600, 2) if secs else None


def _garmin_hrv(payload: dict) -> float | None:
    hrv = payload.get("hrv") or {}
    summary = hrv.get("hrvSummary") or {}
    return summary.get("lastNightAvg")


def _garmin_activity(act: dict) -> dict | None:
    day = _date_of(act.get("startTimeLocal") or act.get("startTimeGMT"))
    if not day:
        return None
    distance_m = act.get("distance")
    return {
        "date": day,
        "sport": (act.get("activityType") or {}).get("typeKey"),
        "distance_km": round(distance_m / 1000, 3) if distance_m else None,
        "duration_seconds": int(act["duration"]) if act.get("duration") else None,
        "avg_pace": None,
        "avg_hr": act.get("averageHR"),
        "max_hr": act.get("maxHR"),
        "source": "garmin",
    }


# --- Recompute -----------------------------------------------------------

def recompute_daily_metrics() -> dict:
    """Rebuild daily_metrics and Garmin-sourced workouts from raw data."""
    try:
        by_date: dict[str, dict] = {}

        for rec in whoop_raw_repo.records("recovery"):
            day = _date_of(rec.get("created_at"))
            if not day:
                continue
            m = by_date.setdefault(day, _empty(day))
            parsed = _whoop_recovery(rec)
            if parsed["hrv_ms"] is not None:
                m["hrv_ms"] = parsed["hrv_ms"]
                m["source_hrv"] = "whoop"
            if parsed["resting_hr"] is not None:
                m["resting_hr"] = parsed["resting_hr"]
            if parsed["recovery_score"] is not None:
                m["recovery_score"] = parsed["recovery_score"]

        for rec in whoop_raw_repo.records("sleep"):
            if rec.get("nap"):
                continue
            day = _date_of(rec.get("end") or rec.get("start"))
            hours = _whoop_sleep_hours(rec)
            if day and hours is not None:
                m = by_date.setdefault(day, _empty(day))
                m["sleep_hours"] = hours
                m["source_sleep"] = "whoop"

        for rec in whoop_raw_repo.records("cycle"):
            day = _date_of(rec.get("start"))
            strain = _whoop_strain(rec)
            if day and strain is not None:
                by_date.setdefault(day, _empty(day))["strain"] = strain

        # Garmin fills gaps Whoop didn't cover.
        for payload in garmin_raw_repo.payloads("daily_stats"):
            if not isinstance(payload, dict):
                continue
            day = payload.get("date")
            if not day:
                continue
            m = by_date.setdefault(day, _empty(day))
            if m["resting_hr"] is None:
                m["resting_hr"] = _garmin_resting_hr(payload)
            if m["sleep_hours"] is None:
                sh = _garmin_sleep_hours(payload)
                if sh is not None:
                    m["sleep_hours"] = sh
                    m["source_sleep"] = "garmin"
            if m["hrv_ms"] is None:
                gh = _garmin_hrv(payload)
                if gh is not None:
                    m["hrv_ms"] = gh
                    m["source_hrv"] = "garmin"

        metrics_written = daily_metrics_repo.upsert_many(list(by_date.values()))

        # Workouts: Garmin wins.
        activities: list = []
        for payload in garmin_raw_repo.payloads("activities"):
            if isinstance(payload, list):
                activities.extend(payload)
        workouts = [w for w in (_garmin_activity(a) for a in activities) if w]
        workouts_repo.delete_source("garmin")
        workouts_written = workouts_repo.insert_many(workouts)

        logger.info(
            "calc",
            "recompute_daily_metrics complete",
            {"daily_metrics": metrics_written, "workouts": workouts_written},
        )
        return {
            "ok": True,
            "daily_metrics": metrics_written,
            "workouts": workouts_written,
        }
    except Exception as exc:
        logger.error("calc", "recompute_daily_metrics failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}
