"""Shared Streamlit page chrome. Pages import this for elements that should
look identical everywhere — chiefly the persistent race header that keeps the
goal in view on every screen."""

from __future__ import annotations

import streamlit as st

from services import goal_service


def race_header() -> None:
    """One line of context every training decision hangs on: what race, how
    far away, and the goal time. Renders nothing when no goal is set."""
    s = goal_service.race_summary()
    if not s.get("race_date"):
        return
    bits = [f"🏁 {s.get('distance_label') or s.get('sport') or 'race'}", s["race_date"]]
    days = s.get("days_to_race")
    if days is not None:
        if days < 0:
            bits.append("race day has passed — set your next goal in Settings")
        elif days <= 21:
            bits.append(f"**{days} days out**")
        else:
            bits.append(f"**{s['weeks_to_race']} weeks out**")
    if s.get("goal_time"):
        bits.append(f"goal {s['goal_time']}")
    st.caption(" · ".join(bits))
