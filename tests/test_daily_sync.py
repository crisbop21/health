"""The headless daily-sync entrypoint, with the services mocked."""

from __future__ import annotations

from scripts import daily_sync
from services import metrics_service, sync_service


def test_run_ok_when_both_succeed(monkeypatch):
    captured = {}

    def fake_sync(days):
        captured["days"] = days
        return {"ok": True, "garmin": {"ok": True}, "whoop": {"ok": True}}

    monkeypatch.setattr(sync_service, "sync_all_devices", fake_sync)
    monkeypatch.setattr(metrics_service, "recompute_daily_metrics", lambda: {"ok": True})

    result = daily_sync.run(days=14)

    assert result["ok"] is True
    assert captured["days"] == 14


def test_run_fails_if_recompute_fails(monkeypatch):
    monkeypatch.setattr(
        sync_service, "sync_all_devices", lambda days: {"ok": True, "garmin": {}, "whoop": {}}
    )
    monkeypatch.setattr(
        metrics_service, "recompute_daily_metrics", lambda: {"ok": False, "error": "x"}
    )

    assert daily_sync.run()["ok"] is False


def test_main_returns_nonzero_on_failure(monkeypatch):
    monkeypatch.setattr(daily_sync, "run", lambda days=7: {"ok": False})
    monkeypatch.setattr(daily_sync.sys, "argv", ["daily_sync"])
    assert daily_sync.main() == 1


def test_main_returns_zero_on_success(monkeypatch):
    monkeypatch.setattr(daily_sync, "run", lambda days=7: {"ok": True})
    monkeypatch.setattr(daily_sync.sys, "argv", ["daily_sync", "30"])
    assert daily_sync.main() == 0
