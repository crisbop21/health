"""Pure-helper tests for the Claude client. No anthropic package required —
these exercise cost estimation, token totals, and JSON extraction only."""

from __future__ import annotations

from types import SimpleNamespace

from clients import claude_client


def test_estimate_cost_input_output():
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=2000,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    cost = claude_client._estimate_cost("claude-opus-4-7", usage)
    expected = 1000 * (5.0 / 1_000_000) + 2000 * (25.0 / 1_000_000)
    assert cost == expected


def test_estimate_cost_includes_cache():
    usage = SimpleNamespace(
        input_tokens=0,
        output_tokens=0,
        cache_creation_input_tokens=1000,
        cache_read_input_tokens=1000,
    )
    cost = claude_client._estimate_cost("claude-opus-4-7", usage)
    expected = 1000 * (6.25 / 1_000_000) + 1000 * (0.5 / 1_000_000)
    assert cost == expected


def test_total_input_tokens_sums_cache():
    usage = SimpleNamespace(
        input_tokens=100,
        cache_creation_input_tokens=10,
        cache_read_input_tokens=5,
    )
    assert claude_client._total_input_tokens(usage) == 115


def test_first_text_skips_non_text_blocks():
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="…"),
            SimpleNamespace(type="text", text="the answer"),
        ]
    )
    assert claude_client._first_text(message) == "the answer"


def test_first_text_empty_when_no_text():
    message = SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking="…")])
    assert claude_client._first_text(message) == ""


def test_extract_json_finds_text_block():
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="…"),
            SimpleNamespace(type="text", text='{"summary": "s", "plan": []}'),
        ]
    )
    data = claude_client._extract_json(message)
    assert data["summary"] == "s"
    assert data["plan"] == []


def test_build_user_message_is_deterministic():
    goal = {"sport": "running", "race_date": "2026-12-06"}
    a = claude_client._build_user_message(goal, {"hrv": 60}, {"easy": 330.0}, "2026-05-27")
    b = claude_client._build_user_message(goal, {"hrv": 60}, {"easy": 330.0}, "2026-05-27")
    assert a == b  # sorted keys -> stable prefix for prompt caching
    assert "2026-12-06" in a
    assert '"mode": "initial"' in a


def test_build_user_message_recalibration_mode():
    msg = claude_client._build_user_message(
        {"race_date": "2026-12-06"},
        {},
        {},
        "2026-05-27",
        current_plan=[{"date": "2026-05-27", "planned_workout_type": "easy"}],
        reason="low recovery this week",
    )
    assert '"mode": "recalibration"' in msg
    assert "low recovery this week" in msg
    assert "current_remaining_plan" in msg
