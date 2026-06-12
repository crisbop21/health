"""The headless daily-sync entrypoint, with the services and alerting mocked."""

from __future__ import annotations

from datetime import date

import pytest

from clients import notify_client
from scripts import daily_sync
from services import metrics_service, sync_service

MONDAY = date(2026, 6, 8)
TUESDAY = date(2026, 6, 9)


@pytest.fixture(autouse=True)
def _no_real_alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(notify_client, "send", lambda text: sent.append(text) or True)
    return sent


@pytest.fixture(autouse=True)
def _not_monday(monkeypatch):
    # Pin a non-Monday so the weekly heal doesn't fire unless a test asks.
    monkeypatch.setattr(daily_sync.clock, "local_today", lambda: TUESDAY)


def _wire(monkeypatch, *, garmin, whoop, recompute, captured=None):
    captured = captured if captured is not None else {}

    def fake_sync(days):
        captured["days"] = days
        return {"ok": garmin.get("ok") and whoop.get("ok"), "garmin": garmin, "whoop": whoop}

    def fake_recompute(since=None):
        captured["since"] = since
        return recompute

    monkeypatch.setattr(sync_service, "sync_all_devices", fake_sync)
    monkeypatch.setattr(metrics_service, "recompute_daily_metrics", fake_recompute)
    return captured


def test_run_ok_when_both_succeed(monkeypatch, _no_real_alerts):
    _wire(monkeypatch, garmin={"ok": True}, whoop={"ok": True}, recompute={"ok": True})
    result = daily_sync.run(days=14)
    assert result["ok"] is True
    assert result["problems"] == []
    assert _no_real_alerts == []  # no alert on success


def test_recompute_is_incremental_from_sync_start(monkeypatch):
    captured = _wire(
        monkeypatch, garmin={"ok": True}, whoop={"ok": True}, recompute={"ok": True}
    )
    daily_sync.run()
    # The nightly path replays only rows recorded by this sync, not all history.
    assert captured["since"] is not None


def test_monday_extends_lookback_to_heal_late_edits(monkeypatch):
    monkeypatch.setattr(daily_sync.clock, "local_today", lambda: MONDAY)
    captured = _wire(
        monkeypatch, garmin={"ok": True}, whoop={"ok": True}, recompute={"ok": True}
    )
    daily_sync.run()
    assert captured["days"] == daily_sync.HEAL_DAYS


def test_non_monday_keeps_default_lookback(monkeypatch):
    captured = _wire(
        monkeypatch, garmin={"ok": True}, whoop={"ok": True}, recompute={"ok": True}
    )
    daily_sync.run()
    assert captured["days"] == daily_sync.DEFAULT_DAYS


def test_explicit_days_not_overridden_on_monday(monkeypatch):
    monkeypatch.setattr(daily_sync.clock, "local_today", lambda: MONDAY)
    captured = _wire(
        monkeypatch, garmin={"ok": True}, whoop={"ok": True}, recompute={"ok": True}
    )
    daily_sync.run(days=30)
    assert captured["days"] == 30


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


def test_auth_failure_says_reconnect(monkeypatch, _no_real_alerts):
    _wire(
        monkeypatch,
        garmin={"ok": True},
        whoop={"ok": False, "error": "401 Unauthorized: invalid_grant"},
        recompute={"ok": True},
    )
    result = daily_sync.run()
    assert result["ok"] is False
    assert any("reconnect" in p.lower() for p in result["problems"])
    assert any("reconnect" in t.lower() for t in _no_real_alerts)


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
