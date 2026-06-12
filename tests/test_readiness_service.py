"""Readiness verdict (the Today go/no-go banner) and taper status, with
repos/services mocked."""

from __future__ import annotations

from datetime import date, timedelta

from repositories import daily_metrics_repo, goals_repo
from services import dashboard_service, readiness_service


# --- Verdict rules ----------------------------------------------------------

def test_verdict_green_when_all_good():
    verdict, reasons = readiness_service._verdict(recovery=80, sleep_hours=7.5, acwr=1.0)
    assert verdict == "green"
    assert reasons == []


def test_verdict_red_on_low_recovery():
    verdict, reasons = readiness_service._verdict(recovery=20, sleep_hours=8, acwr=1.0)
    assert verdict == "red"
    assert any("recovery" in r.lower() for r in reasons)


def test_verdict_red_on_load_spike():
    verdict, reasons = readiness_service._verdict(recovery=80, sleep_hours=8, acwr=1.7)
    assert verdict == "red"
    assert any("load" in r.lower() for r in reasons)


def test_verdict_amber_on_moderate_flags():
    verdict, reasons = readiness_service._verdict(recovery=50, sleep_hours=5.5, acwr=1.0)
    assert verdict == "amber"
    assert len(reasons) == 2  # recovery and sleep both flagged


def test_verdict_amber_on_detraining():
    verdict, reasons = readiness_service._verdict(recovery=80, sleep_hours=8, acwr=0.5)
    assert verdict == "amber"


def test_verdict_handles_missing_inputs():
    verdict, reasons = readiness_service._verdict(recovery=None, sleep_hours=None, acwr=None)
    assert verdict == "unknown"


# --- Wiring -----------------------------------------------------------------

def test_readiness_combines_metrics_and_load(monkeypatch):
    monkeypatch.setattr(
        daily_metrics_repo, "get_recent",
        lambda n: [{"date": "2026-06-11", "recovery_score": 75, "sleep_hours": 7.8, "hrv_ms": 62}],
    )
    monkeypatch.setattr(
        dashboard_service, "training_load",
        lambda days=60: {"ok": True, "rows": [{"date": "2026-06-12", "acwr": 1.1}]},
    )

    result = readiness_service.readiness()

    assert result["ok"] is True
    assert result["verdict"] == "green"
    assert result["metrics"]["acwr"] == 1.1
    assert result["metrics"]["recovery_score"] == 75


def test_readiness_without_data_is_unknown(monkeypatch):
    monkeypatch.setattr(daily_metrics_repo, "get_recent", lambda n: [])
    monkeypatch.setattr(
        dashboard_service, "training_load", lambda days=60: {"ok": True, "rows": []}
    )
    result = readiness_service.readiness()
    assert result["ok"] is True
    assert result["verdict"] == "unknown"


def test_readiness_survives_failure(monkeypatch):
    monkeypatch.setattr(
        daily_metrics_repo, "get_recent", lambda n: (_ for _ in ()).throw(RuntimeError("db"))
    )
    monkeypatch.setattr(
        dashboard_service, "training_load", lambda days=60: {"ok": False, "error": "db"}
    )
    result = readiness_service.readiness()
    assert result["ok"] is True  # degrades, never raises into the UI
    assert result["verdict"] == "unknown"


# --- Taper ------------------------------------------------------------------

def test_taper_status_in_race_week(monkeypatch):
    race = (date.today() + timedelta(days=10)).isoformat()
    monkeypatch.setattr(goals_repo, "get_active", lambda: {"race_date": race})
    monkeypatch.setattr(
        dashboard_service, "training_load",
        lambda days=60: {"ok": True, "rows": [{"acute": 3.0, "chronic": 6.0, "acwr": 0.5}]},
    )

    result = readiness_service.taper_status()

    assert result["ok"] is True
    assert result["days_to_race"] == 10
    assert result["race_week"] is True
    assert result["tapering"] is True


def test_taper_status_flags_high_load_near_race(monkeypatch):
    race = (date.today() + timedelta(days=5)).isoformat()
    monkeypatch.setattr(goals_repo, "get_active", lambda: {"race_date": race})
    monkeypatch.setattr(
        dashboard_service, "training_load",
        lambda days=60: {"ok": True, "rows": [{"acute": 8.0, "chronic": 6.0, "acwr": 1.33}]},
    )
    assert readiness_service.taper_status()["tapering"] is False


def test_taper_status_without_goal(monkeypatch):
    monkeypatch.setattr(goals_repo, "get_active", lambda: None)
    result = readiness_service.taper_status()
    assert result["ok"] is True
    assert result["days_to_race"] is None
