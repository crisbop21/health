"""Metrics service source-resolution, with the repos mocked. Verifies Whoop
wins HRV/recovery/sleep, Garmin fills gaps, Garmin activities become workouts
(with Whoop workouts filling Garmin-less days), and incremental recompute only
replays raw rows recorded since the watermark."""

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
WHOOP_WORKOUTS = [
    {  # 2026-05-25 has no Garmin activity -> Whoop fills the day
        "id": "w-1",
        "start": "2026-05-25T11:00:00.000Z",
        "end": "2026-05-25T12:00:00.000Z",
        "sport_name": "running",
        "score": {"distance_meter": 8000.0, "average_heart_rate": 150, "max_heart_rate": 170},
    },
    {  # 2026-05-26 has a Garmin activity -> Garmin wins, Whoop excluded
        "id": "w-2",
        "start": "2026-05-26T11:00:00.000Z",
        "end": "2026-05-26T11:30:00.000Z",
        "sport_name": "cycling",
        "score": {},
    },
]

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
            "activityId": 111,
            "startTimeLocal": "2026-05-26 06:00:00",
            "activityType": {"typeKey": "running"},
            "distance": 10000.0,
            "duration": 3000.0,
            "averageHR": 150,
            "maxHR": 175,
        }
    ]
]


def _wire(monkeypatch, *, whoop=None, garmin=None, garmin_dates_in_db=frozenset()):
    whoop = whoop if whoop is not None else {
        "recovery": WHOOP_RECOVERY, "sleep": WHOOP_SLEEP,
        "cycle": WHOOP_CYCLE, "workout": WHOOP_WORKOUTS,
    }
    garmin = garmin if garmin is not None else {
        "daily_stats": GARMIN_DAILY, "activities": GARMIN_ACTIVITIES,
    }
    captured = {"since": {}, "deleted_sources": [], "deleted_whoop_dates": []}

    def records(endpoint, since=None):
        captured["since"][f"whoop_{endpoint}"] = since
        return whoop.get(endpoint, [])

    def payloads(endpoint, since=None):
        captured["since"][f"garmin_{endpoint}"] = since
        return garmin.get(endpoint, [])

    monkeypatch.setattr(metrics_service.whoop_raw_repo, "records", records)
    monkeypatch.setattr(metrics_service.garmin_raw_repo, "payloads", payloads)
    monkeypatch.setattr(
        metrics_service.daily_metrics_repo,
        "upsert_many",
        lambda rows: captured.update(metrics={r["date"]: r for r in rows}) or len(rows),
    )
    monkeypatch.setattr(
        metrics_service.workouts_repo,
        "delete_source",
        lambda s: captured["deleted_sources"].append(s),
    )
    monkeypatch.setattr(
        metrics_service.workouts_repo,
        "delete_source_dates",
        lambda s, dates: captured["deleted_whoop_dates"].extend(dates),
    )
    monkeypatch.setattr(
        metrics_service.workouts_repo,
        "dates_with_source",
        lambda s, dates: {d for d in dates if d in garmin_dates_in_db},
    )
    monkeypatch.setattr(
        metrics_service.workouts_repo,
        "upsert_many",
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

    garmin_workouts = [w for w in captured["workouts"] if w["source"] == "garmin"]
    assert len(garmin_workouts) == 1
    w = garmin_workouts[0]
    assert w["date"] == "2026-05-26"
    assert w["sport"] == "running"
    assert w["distance_km"] == 10.0
    assert w["duration_seconds"] == 3000
    assert w["avg_pace"] == "5:00/km"  # 3000 s over 10 km
    assert w["external_id"] == "111"


def test_whoop_workouts_fill_garmin_less_days_only(monkeypatch):
    captured = _wire(monkeypatch)
    metrics_service.recompute_daily_metrics()

    whoop_workouts = [w for w in captured["workouts"] if w["source"] == "whoop"]
    # w-2 lands on 05-26 where Garmin has an activity -> excluded.
    assert [w["external_id"] for w in whoop_workouts] == ["w-1"]
    w = whoop_workouts[0]
    assert w["date"] == "2026-05-25"
    assert w["sport"] == "running"
    assert w["distance_km"] == 8.0
    assert w["duration_seconds"] == 3600
    assert w["avg_hr"] == 150
    assert w["max_hr"] == 170


def test_full_recompute_replaces_both_workout_sources(monkeypatch):
    captured = _wire(monkeypatch)
    metrics_service.recompute_daily_metrics()
    assert set(captured["deleted_sources"]) == {"garmin", "whoop"}


def test_incremental_passes_since_and_never_deletes_sources(monkeypatch):
    captured = _wire(monkeypatch)
    result = metrics_service.recompute_daily_metrics(since="2026-06-01T00:00:00Z")

    assert result["ok"] is True
    assert captured["deleted_sources"] == []  # no destructive full rebuild
    assert set(captured["since"].values()) == {"2026-06-01T00:00:00Z"}


def test_incremental_displaces_whoop_when_garmin_arrives(monkeypatch):
    captured = _wire(monkeypatch)
    metrics_service.recompute_daily_metrics(since="2026-06-01T00:00:00Z")
    # Garmin activity on 05-26 displaces any earlier Whoop fallback rows there.
    assert captured["deleted_whoop_dates"] == ["2026-05-26"]


def test_incremental_respects_garmin_days_already_in_db(monkeypatch):
    # Batch has only the Whoop workout on 05-25, but the DB already holds a
    # Garmin workout for that date -> Whoop must not be inserted.
    captured = _wire(
        monkeypatch,
        whoop={"workout": [WHOOP_WORKOUTS[0]]},
        garmin={},
        garmin_dates_in_db=frozenset({"2026-05-25"}),
    )
    metrics_service.recompute_daily_metrics(since="2026-06-01T00:00:00Z")
    assert captured["workouts"] == []


def test_dates_bucket_in_home_timezone(monkeypatch):
    monkeypatch.setenv("HOME_TIMEZONE", "America/Bogota")
    # Recovery created 03:00 UTC on the 27th is the evening of the 26th in Bogotá.
    recovery = [{
        "created_at": "2026-05-27T03:00:00.000Z",
        "score": {"hrv_rmssd_milli": 60.0, "resting_heart_rate": 50, "recovery_score": 80},
    }]
    captured = _wire(monkeypatch, whoop={"recovery": recovery}, garmin={})
    metrics_service.recompute_daily_metrics()
    assert list(captured["metrics"]) == ["2026-05-26"]


def test_avg_pace_is_none_without_distance():
    assert metrics_service._avg_pace(None, 1800) is None
    assert metrics_service._avg_pace(0, 1800) is None
    assert metrics_service._avg_pace(5.0, None) is None


def test_recompute_handles_failure(monkeypatch):
    def boom(endpoint, since=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(metrics_service.whoop_raw_repo, "records", boom)
    result = metrics_service.recompute_daily_metrics()
    assert result["ok"] is False
    assert "db down" in result["error"]
