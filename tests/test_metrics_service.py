"""Metrics service source-resolution, with the repos mocked. Verifies Whoop
wins HRV/recovery/sleep, Garmin fills gaps, and Garmin activities become
workouts."""

from __future__ import annotations

from services import metrics_service


WHOOP_RECOVERY = [
    {
        "created_at": "2026-05-26T12:00:00.000Z",
        "score": {"hrv_rmssd_milli": 65.0, "resting_heart_rate": 48, "recovery_score": 72},
    }
]
WHOOP_SLEEP = [
    {
        "end": "2026-05-26T06:30:00.000Z",
        "nap": False,
        "score": {
            "stage_summary": {
                "total_in_bed_time_milli": 28_800_000,  # 8h
                "total_awake_time_milli": 1_800_000,  # 0.5h
            }
        },
    },
    {"end": "2026-05-26T14:00:00.000Z", "nap": True, "score": {}},  # nap ignored
]
WHOOP_CYCLE = [{"start": "2026-05-26T04:00:00.000Z", "score": {"strain": 12.4}}]

GARMIN_DAILY = [
    {  # 2026-05-26: Whoop already covers HRV/sleep, so Garmin must not override
        "date": "2026-05-26",
        "resting_hr": {"restingHeartRate": 99},
        "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 3600}},
        "hrv": {"hrvSummary": {"lastNightAvg": 10}},
    },
    {  # 2026-05-25: only Garmin -> Garmin becomes the source
        "date": "2026-05-25",
        "resting_hr": {"restingHeartRate": 50},
        "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 25_200}},  # 7h
        "hrv": {"hrvSummary": {"lastNightAvg": 55}},
    },
]
GARMIN_ACTIVITIES = [
    [
        {
            "startTimeLocal": "2026-05-26 06:00:00",
            "activityType": {"typeKey": "running"},
            "distance": 10000.0,
            "duration": 3000.0,
            "averageHR": 150,
            "maxHR": 175,
        }
    ]
]


def _wire(monkeypatch):
    def records(endpoint):
        return {"recovery": WHOOP_RECOVERY, "sleep": WHOOP_SLEEP, "cycle": WHOOP_CYCLE}.get(
            endpoint, []
        )

    def payloads(endpoint):
        return {"daily_stats": GARMIN_DAILY, "activities": GARMIN_ACTIVITIES}.get(endpoint, [])

    monkeypatch.setattr(metrics_service.whoop_raw_repo, "records", records)
    monkeypatch.setattr(metrics_service.garmin_raw_repo, "payloads", payloads)

    captured = {}
    monkeypatch.setattr(
        metrics_service.daily_metrics_repo,
        "upsert_many",
        lambda rows: captured.update(metrics={r["date"]: r for r in rows}) or len(rows),
    )
    monkeypatch.setattr(metrics_service.workouts_repo, "delete_source", lambda s: None)
    monkeypatch.setattr(
        metrics_service.workouts_repo,
        "insert_many",
        lambda rows: captured.update(workouts=rows) or len(rows),
    )
    return captured


def test_whoop_wins_and_garmin_fills_gaps(monkeypatch):
    captured = _wire(monkeypatch)
    result = metrics_service.recompute_daily_metrics()
    assert result["ok"] is True

    m26 = captured["metrics"]["2026-05-26"]
    assert m26["hrv_ms"] == 65.0
    assert m26["source_hrv"] == "whoop"
    assert m26["resting_hr"] == 48  # whoop, not garmin's 99
    assert m26["recovery_score"] == 72
    assert m26["strain"] == 12.4
    assert m26["sleep_hours"] == 7.5  # 8h in bed - 0.5h awake
    assert m26["source_sleep"] == "whoop"

    m25 = captured["metrics"]["2026-05-25"]
    assert m25["source_hrv"] == "garmin"
    assert m25["hrv_ms"] == 55
    assert m25["resting_hr"] == 50
    assert m25["sleep_hours"] == 7.0
    assert m25["source_sleep"] == "garmin"


def test_garmin_activities_become_workouts(monkeypatch):
    captured = _wire(monkeypatch)
    metrics_service.recompute_daily_metrics()

    workouts = captured["workouts"]
    assert len(workouts) == 1
    w = workouts[0]
    assert w["date"] == "2026-05-26"
    assert w["sport"] == "running"
    assert w["distance_km"] == 10.0
    assert w["duration_seconds"] == 3000
    assert w["source"] == "garmin"


def test_recompute_handles_failure(monkeypatch):
    def boom(endpoint):
        raise RuntimeError("db down")

    monkeypatch.setattr(metrics_service.whoop_raw_repo, "records", boom)
    result = metrics_service.recompute_daily_metrics()
    assert result["ok"] is False
    assert "db down" in result["error"]
