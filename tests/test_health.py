"""DB-availability probe."""

from __future__ import annotations

from types import SimpleNamespace

from core import health, supabase_client


def _make_client(success: bool):
    class Q:
        def select(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            if not success:
                raise RuntimeError("connection refused")
            return SimpleNamespace(data=[])

    class C:
        def table(self, *a, **k):
            return Q()

    return C()


def test_db_available_true(monkeypatch):
    supabase_client.get_client.cache_clear()
    monkeypatch.setattr(supabase_client, "get_client", lambda: _make_client(True))
    assert health.db_available() is True


def test_db_available_false(monkeypatch):
    def boom():
        raise RuntimeError("supabase down")

    monkeypatch.setattr(supabase_client, "get_client", boom)
    assert health.db_available() is False
