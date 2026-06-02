"""Garmin client and sync service, with the Garmin API and repo mocked."""

from __future__ import annotations

from clients import garmin_client
from repositories import garmin_raw_repo
from services import sync_service


class FakeGarmin:
    def get_activities_by_date(self, start, end, *a, **k):
        return [{"activityId": 1, "start": start, "end": end}]

    def get_stats(self, day):
        return {"date": day, "steps": 8000}

    def get_sleep_data(self, day):
        return {"date": day, "sleep_hours": 7.5}

    def get_hrv_data(self, day):
        return {"date": day, "hrv_ms": 62}

    def get_rhr_day(self, day):
        return {"date": day, "resting_hr": 48}


def test_fetch_recent_activities(monkeypatch):
    monkeypatch.setattr(garmin_client, "login", lambda: FakeGarmin())
    acts = garmin_client.fetch_recent_activities(days=7)
    assert len(acts) == 1
    assert acts[0]["activityId"] == 1


def test_fetch_daily_stats_bundles_endpoints():
    stats = garmin_client.fetch_daily_stats("2026-05-27", client=FakeGarmin())
    assert stats["date"] == "2026-05-27"
    assert stats["stats"]["steps"] == 8000
    assert stats["sleep"]["sleep_hours"] == 7.5
    assert stats["hrv"]["hrv_ms"] == 62
    assert stats["resting_hr"]["resting_hr"] == 48


def test_daily_stats_one_endpoint_failure_is_isolated():
    class PartialGarmin(FakeGarmin):
        def get_hrv_data(self, day):
            raise RuntimeError("garmin hiccup")

    stats = garmin_client.fetch_daily_stats("2026-05-27", client=PartialGarmin())
    assert stats["hrv"] is None  # failed endpoint -> None, others intact
    assert stats["stats"]["steps"] == 8000


def test_rate_limit_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr(garmin_client.time, "sleep", lambda s: None)  # no real waiting
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 Too Many Requests")
        return "ok"

    assert garmin_client._call(flaky) == "ok"
    assert calls["n"] == 3  # two rate-limit retries, then success


def test_non_rate_limit_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(garmin_client.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("garmin hiccup")

    import pytest

    with pytest.raises(RuntimeError, match="hiccup"):
        garmin_client._call(boom)
    assert calls["n"] == 1  # generic errors fail fast, no backoff


def test_sync_writes_raw_rows(monkeypatch):
    monkeypatch.setattr(garmin_client, "login", lambda: FakeGarmin())
    upserts = []
    monkeypatch.setattr(
        garmin_raw_repo,
        "upsert_records",
        lambda records, endpoint, key_field, recorded_at=None: upserts.append((endpoint, key_field)) or len(records),
    )

    result = sync_service.sync_garmin_last_7_days()

    assert result["ok"] is True
    assert result["rows_written"] == 8  # 1 activity + 7 daily_stats
    endpoints = [e for e, _ in upserts]
    assert endpoints.count("activities") == 1
    assert endpoints.count("daily_stats") == 7
    # Activities dedupe on activityId; daily stats on the day.
    assert ("activities", "activityId") in upserts
    assert ("daily_stats", "date") in upserts


def test_sync_handles_login_failure_gracefully(monkeypatch):
    def boom():
        raise RuntimeError("bad password")

    monkeypatch.setattr(garmin_client, "login", boom)
    result = sync_service.sync_garmin_last_7_days()
    assert result["ok"] is False
    assert "bad password" in result["error"]
