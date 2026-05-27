"""Deterministic pace-zone math."""

from __future__ import annotations

from core import pace_zones


def test_marathon_pace():
    # 4:00:00 over 42.195 km
    mp = pace_zones.marathon_pace_sec_per_km(14400)
    assert round(mp, 2) == round(14400 / 42.195, 2)


def test_pace_zones_ordering():
    zones = pace_zones.pace_zones(14400)
    assert set(zones) == {"recovery", "easy", "marathon", "threshold", "interval"}
    # faster paces have fewer seconds per km
    assert zones["interval"] < zones["threshold"] < zones["marathon"]
    assert zones["marathon"] < zones["easy"] < zones["recovery"]


def test_non_running_returns_empty():
    assert pace_zones.pace_zones(14400, sport="cycling") == {}


def test_missing_goal_time_returns_empty():
    assert pace_zones.pace_zones(None) == {}
    assert pace_zones.pace_zones(0) == {}


def test_format_pace():
    assert pace_zones.format_pace(330) == "5:30/km"
    assert pace_zones.format_pace(389.9) == "6:30/km"  # rounds to whole second
    assert pace_zones.format_pace(59.6) == "1:00/km"  # 60s rolls to next minute
    assert pace_zones.format_pace(None) is None
