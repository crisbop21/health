"""The headless daily-sync entrypoint, with the services and alerting mocked."""

from __future__ import annotations

import pytest

from clients import notify_client
from scripts import daily_sync
from services import metrics_service, sync_service


@pytest.fixture(autouse=True)
def _no_real_alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(notify_client, "send", lambda text: sent.append(text) or True)
    return sent


def _wire(monkeypatch, *, garmin, whoop, recompute):
    monkeypatch.setattr(
        sync_service, "sync_all_devices",
        lambda days: {"ok": garmin.get("ok") and whoop.get("ok"), "garmin": garmin, "whoop": whoop},
    )
    monkeypatch.setattr(metrics_service, "recompute_daily_metrics", lambda: recompute)


def test_run_ok_when_both_succeed(monkeypatch, _no_real_alerts):
    _wire(monkeypatch, garmin={"ok": True}, whoop={"ok": True}, recompute={"ok": True})
    result = daily_sync.run(days=14)
    assert result["ok"] is True
    assert result["problems"] == []
    assert _no_real_alerts == []  # no alert on success


def test_whoop_not_connected_is_skipped_not_failed(monkeypatch, _no_real_alerts):
    _wire(
        monkeypatch,
        garmin={"ok": True},
        whoop={"ok": False, "error": "Whoop is not connected."},
        recompute={"ok": True},
    )
    result = daily_sync.run()
    assert result["ok"] is True  # expected skip, not a problem
    assert _no_real_alerts == []


def test_real_failure_records_problem_and_alerts(monkeypatch, _no_real_alerts):
    _wire(
        monkeypatch,
        garmin={"ok": False, "error": "503 from Garmin"},
        whoop={"ok": True},
        recompute={"ok": True},
    )
    result = daily_sync.run()
    assert result["ok"] is False
    assert any("garmin" in p for p in result["problems"])
    assert len(_no_real_alerts) == 1  # alerted once


def test_recompute_failure_is_a_problem(monkeypatch, _no_real_alerts):
    _wire(monkeypatch, garmin={"ok": True}, whoop={"ok": True}, recompute={"ok": False, "error": "x"})
    assert daily_sync.run()["ok"] is False


def test_main_returns_nonzero_on_failure(monkeypatch):
    monkeypatch.setattr(daily_sync, "run", lambda days=7: {"ok": False, "problems": ["x"], "sync": {}, "recompute": {}})
    monkeypatch.setattr(daily_sync.sys, "argv", ["daily_sync"])
    assert daily_sync.main() == 1


def test_main_returns_zero_on_success(monkeypatch):
    monkeypatch.setattr(daily_sync, "run", lambda days=7: {"ok": True, "problems": [], "sync": {}, "recompute": {}})
    monkeypatch.setattr(daily_sync.sys, "argv", ["daily_sync", "30"])
    assert daily_sync.main() == 0
