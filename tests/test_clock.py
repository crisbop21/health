"""Home-timezone date bucketing. Device timestamps are UTC; without a home
timezone, an evening workout in Bogotá lands on tomorrow's date."""

from __future__ import annotations

from core import clock


def test_utc_timestamp_buckets_to_home_tz_date(monkeypatch):
    monkeypatch.setenv("HOME_TIMEZONE", "America/Bogota")
    # 03:00 UTC on the 2nd is 22:00 on the 1st in Bogotá (UTC-5).
    assert clock.local_date_of("2026-01-02T03:00:00.000Z") == "2026-01-01"


def test_naive_and_date_only_pass_through(monkeypatch):
    monkeypatch.setenv("HOME_TIMEZONE", "America/Bogota")
    # Garmin's startTimeLocal is naive and already local — no conversion.
    assert clock.local_date_of("2026-05-26 06:00:00") == "2026-05-26"
    assert clock.local_date_of("2026-05-26") == "2026-05-26"
    assert clock.local_date_of(None) is None
    assert clock.local_date_of("garbage-timestamp") == "garbage-ti"[:10]


def test_defaults_to_utc(monkeypatch):
    monkeypatch.delenv("HOME_TIMEZONE", raising=False)
    assert clock.local_date_of("2026-01-02T03:00:00.000Z") == "2026-01-02"


def test_invalid_timezone_falls_back_to_utc(monkeypatch):
    monkeypatch.setenv("HOME_TIMEZONE", "Mars/Olympus_Mons")
    assert clock.local_date_of("2026-01-02T03:00:00.000Z") == "2026-01-02"


def test_local_today_is_a_date(monkeypatch):
    monkeypatch.setenv("HOME_TIMEZONE", "America/Bogota")
    assert len(clock.local_today().isoformat()) == 10
