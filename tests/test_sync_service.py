"""Whoop and all-device sync orchestration, with clients and repos mocked."""

from __future__ import annotations

from clients import garmin_client, whoop_client
from repositories import garmin_raw_repo, whoop_raw_repo
from services import sync_service


def test_sync_whoop_writes_four_endpoints(monkeypatch):
    monkeypatch.setattr(whoop_client, "fetch_recoveries", lambda s, e: {"records": [1]})
    monkeypatch.setattr(whoop_client, "fetch_sleeps", lambda s, e: {"records": [2]})
    monkeypatch.setattr(whoop_client, "fetch_workouts", lambda s, e: {"records": [3]})
    monkeypatch.setattr(whoop_client, "fetch_cycles", lambda s, e: {"records": [4]})
    inserts = []
    monkeypatch.setattr(
        whoop_raw_repo,
        "insert",
        lambda payload, endpoint, recorded_at=None: inserts.append(endpoint),
    )

    result = sync_service.sync_whoop_last_7_days()

    assert result["ok"] is True
    assert result["rows_written"] == 4
    assert set(inserts) == {"recovery", "sleep", "workout", "cycle"}


def test_sync_whoop_failure_is_graceful(monkeypatch):
    def boom(s, e):
        raise RuntimeError("token expired")

    monkeypatch.setattr(whoop_client, "fetch_recoveries", boom)
    result = sync_service.sync_whoop_last_7_days()
    assert result["ok"] is False
    assert "token expired" in result["error"]


def test_sync_all_devices_combines(monkeypatch):
    monkeypatch.setattr(
        sync_service, "sync_garmin_last_7_days", lambda: {"ok": True, "rows_written": 8}
    )
    monkeypatch.setattr(
        sync_service, "sync_whoop_last_7_days", lambda: {"ok": False, "error": "no whoop"}
    )

    result = sync_service.sync_all_devices()

    assert result["ok"] is False  # one device failed
    assert result["garmin"]["rows_written"] == 8
    assert result["whoop"]["error"] == "no whoop"
