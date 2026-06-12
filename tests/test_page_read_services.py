"""Read wrappers that pages use instead of touching repositories directly
(pages -> services only). Each follows the service contract: an ok-dict that
never raises into the UI."""

from __future__ import annotations

from repositories import debug_log_repo, progress_tests_repo, qa_log_repo, training_plan_repo
from services import log_service, plan_service, qa_service, test_service


def test_recent_questions_ok(monkeypatch):
    monkeypatch.setattr(qa_log_repo, "recent", lambda limit: [{"question": "q"}])
    result = qa_service.recent_questions(limit=5)
    assert result == {"ok": True, "rows": [{"question": "q"}]}


def test_recent_questions_failure(monkeypatch):
    monkeypatch.setattr(
        qa_log_repo, "recent", lambda limit: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    result = qa_service.recent_questions()
    assert result["ok"] is False
    assert result["rows"] == []
    assert "db down" in result["error"]


def test_current_plan_ok(monkeypatch):
    monkeypatch.setattr(training_plan_repo, "get_plan", lambda: [{"date": "2026-06-12"}])
    result = plan_service.current_plan()
    assert result == {"ok": True, "rows": [{"date": "2026-06-12"}]}


def test_current_plan_failure(monkeypatch):
    monkeypatch.setattr(
        training_plan_repo, "get_plan", lambda: (_ for _ in ()).throw(RuntimeError("x"))
    )
    result = plan_service.current_plan()
    assert result["ok"] is False and result["rows"] == []


def test_all_tests_ok(monkeypatch):
    monkeypatch.setattr(progress_tests_repo, "get_all", lambda: [{"id": 1}])
    assert test_service.all_tests() == {"ok": True, "rows": [{"id": 1}]}


def test_upcoming_tests_ok(monkeypatch):
    captured = {}

    def fake(start, end):
        captured["window"] = (start, end)
        return [{"id": 2}]

    monkeypatch.setattr(progress_tests_repo, "upcoming", fake)
    result = test_service.upcoming_tests("2026-06-12", "2026-06-19")
    assert result == {"ok": True, "rows": [{"id": 2}]}
    assert captured["window"] == ("2026-06-12", "2026-06-19")


def test_upcoming_tests_failure(monkeypatch):
    monkeypatch.setattr(
        progress_tests_repo, "upcoming", lambda s, e: (_ for _ in ()).throw(RuntimeError("x"))
    )
    assert test_service.upcoming_tests("a", "b")["ok"] is False


def test_recent_logs_passes_filters(monkeypatch):
    captured = {}

    def fake(limit=200, severity=None, source=None, since=None):
        captured.update(limit=limit, severity=severity, source=source, since=since)
        return [{"message": "m"}]

    monkeypatch.setattr(debug_log_repo, "recent", fake)
    result = log_service.recent_logs(limit=50, severity="error", source="garmin", since="t")
    assert result == {"ok": True, "rows": [{"message": "m"}]}
    assert captured == {"limit": 50, "severity": "error", "source": "garmin", "since": "t"}


def test_recent_logs_failure(monkeypatch):
    monkeypatch.setattr(
        debug_log_repo, "recent",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    result = log_service.recent_logs()
    assert result["ok"] is False and result["rows"] == []
