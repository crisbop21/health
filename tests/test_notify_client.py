"""Outbound alerting. Only the unconfigured (no-op) path is unit-tested here;
the actual POST is exercised via the daily_sync integration with send mocked."""

from __future__ import annotations

from clients import notify_client
from core.config import settings


def test_not_configured_is_noop(monkeypatch):
    monkeypatch.setattr(type(settings), "alert_webhook_url", property(lambda self: None))
    assert notify_client.is_configured() is False
    assert notify_client.send("anything") is False


def test_configured_reports_true(monkeypatch):
    monkeypatch.setattr(
        type(settings), "alert_webhook_url", property(lambda self: "https://hooks.example/x")
    )
    assert notify_client.is_configured() is True
