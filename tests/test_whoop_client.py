"""Whoop client OAuth and pagination logic, with the HTTP layer and token repo
mocked. No requests package required."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from clients import whoop_client
from repositories import oauth_tokens_repo


def test_authorize_url_includes_params(monkeypatch):
    monkeypatch.setenv("WHOOP_CLIENT_ID", "cid123")
    monkeypatch.setenv("WHOOP_REDIRECT_URI", "https://app.example/cb")
    url = whoop_client.authorize_url("st4te")
    assert url.startswith(whoop_client.AUTH_URL)
    assert "client_id=cid123" in url
    assert "state=st4te" in url
    assert "response_type=code" in url


def test_exchange_code_stores_tokens(monkeypatch):
    monkeypatch.setattr(
        whoop_client,
        "_token_request",
        lambda data: {
            "access_token": "a1",
            "refresh_token": "r1",
            "expires_in": 3600,
            "scope": whoop_client.SCOPES,
        },
    )
    stored = {}
    monkeypatch.setattr(
        oauth_tokens_repo,
        "upsert",
        lambda provider, **kw: stored.update(provider=provider, **kw),
    )

    whoop_client.exchange_code("authcode")

    assert stored["provider"] == "whoop"
    assert stored["access_token"] == "a1"
    assert stored["refresh_token"] == "r1"
    assert stored["expires_at"] is not None


def test_refresh_preserves_refresh_token_when_omitted(monkeypatch):
    monkeypatch.setattr(oauth_tokens_repo, "get", lambda p: {"refresh_token": "old_r"})
    monkeypatch.setattr(
        whoop_client,
        "_token_request",
        lambda data: {"access_token": "a2", "expires_in": 3600},  # no refresh_token
    )
    stored = {}
    monkeypatch.setattr(oauth_tokens_repo, "upsert", lambda provider, **kw: stored.update(kw))

    whoop_client.refresh()

    assert stored["access_token"] == "a2"
    assert stored["refresh_token"] == "old_r"  # preserved


def test_valid_access_token_refreshes_when_expired(monkeypatch):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    rows = iter(
        [
            {"access_token": "stale", "refresh_token": "r", "expires_at": past},
            {"access_token": "fresh", "refresh_token": "r", "expires_at": future},
        ]
    )
    monkeypatch.setattr(oauth_tokens_repo, "get", lambda p: next(rows))
    refreshed = {"called": False}
    monkeypatch.setattr(whoop_client, "refresh", lambda: refreshed.update(called=True))

    token = whoop_client._valid_access_token()

    assert refreshed["called"] is True
    assert token == "fresh"


def test_valid_access_token_no_refresh_when_fresh(monkeypatch):
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    monkeypatch.setattr(
        oauth_tokens_repo, "get", lambda p: {"access_token": "ok", "expires_at": future}
    )
    monkeypatch.setattr(
        whoop_client, "refresh", lambda: (_ for _ in ()).throw(AssertionError("should not refresh"))
    )
    assert whoop_client._valid_access_token() == "ok"


def test_collect_paginates(monkeypatch):
    monkeypatch.setattr(whoop_client, "_valid_access_token", lambda: "tok")
    pages = iter(
        [
            {"records": [{"id": 1}, {"id": 2}], "next_token": "p2"},
            {"records": [{"id": 3}], "next_token": None},
        ]
    )
    monkeypatch.setattr(whoop_client, "_request_get", lambda path, params, token: next(pages))

    result = whoop_client._collect("/recovery", "s", "e")

    assert [r["id"] for r in result["records"]] == [1, 2, 3]


def test_collect_follows_long_paginations(monkeypatch):
    """A dense backfill window can run past 10 pages; the cap must be generous
    enough that records are never silently dropped mid-window."""
    monkeypatch.setattr(whoop_client, "_valid_access_token", lambda: "tok")
    pages = iter(
        {"records": [{"id": i}], "next_token": f"p{i + 1}" if i < 11 else None}
        for i in range(12)
    )
    monkeypatch.setattr(whoop_client, "_request_get", lambda path, params, token: next(pages))

    result = whoop_client._collect("/activity/sleep", "s", "e")

    assert [r["id"] for r in result["records"]] == list(range(12))


def test_collect_backs_off_on_429_and_succeeds(monkeypatch):
    """A long backfill fires hundreds of requests; transient 429s must be
    retried with a pause, not abort the whole window."""

    class FakeResp:
        status_code = 429
        headers = {"Retry-After": "7"}

    class RateErr(Exception):
        response = FakeResp()

    naps = []
    monkeypatch.setattr(whoop_client.time, "sleep", lambda s: naps.append(s))
    monkeypatch.setattr(whoop_client, "_valid_access_token", lambda: "tok")
    responses = iter([RateErr(), RateErr(), {"records": [{"id": 1}], "next_token": None}])

    def fake_get(path, params, token):
        r = next(responses)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(whoop_client, "_request_get", fake_get)

    result = whoop_client._collect("/recovery", "s", "e")

    assert result["records"] == [{"id": 1}]
    assert naps == [7, 7]  # honored Retry-After both times


def test_collect_gives_up_after_max_rate_limit_retries(monkeypatch):
    class FakeResp:
        status_code = 429
        headers = {}

    class RateErr(Exception):
        response = FakeResp()

    monkeypatch.setattr(whoop_client.time, "sleep", lambda s: None)
    monkeypatch.setattr(whoop_client, "_valid_access_token", lambda: "tok")
    monkeypatch.setattr(
        whoop_client, "_request_get",
        lambda path, params, token: (_ for _ in ()).throw(RateErr()),
    )

    try:
        whoop_client._collect("/recovery", "s", "e")
    except RateErr:
        pass
    else:
        raise AssertionError("expected the 429 to propagate once retries are exhausted")


def test_expired_helpers():
    assert whoop_client._expired(None) is True
    assert whoop_client._expired("not-a-date") is True
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert whoop_client._expired(past) is True
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert whoop_client._expired(future) is False


def test_collect_retries_once_on_401(monkeypatch):
    class FakeResp:
        status_code = 401

    class AuthErr(Exception):
        response = FakeResp()

    calls = {"tokens": [], "refreshed": 0}
    tokens = iter(["tok1", "tok2"])

    def fake_token():
        t = next(tokens)
        calls["tokens"].append(t)
        return t

    monkeypatch.setattr(whoop_client, "_valid_access_token", fake_token)
    monkeypatch.setattr(
        whoop_client, "refresh", lambda: calls.__setitem__("refreshed", calls["refreshed"] + 1)
    )

    responses = iter([AuthErr(), {"records": [{"id": 1}], "next_token": None}])

    def fake_get(path, params, token):
        r = next(responses)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(whoop_client, "_request_get", fake_get)

    result = whoop_client._collect("/recovery", "s", "e")

    assert result["records"] == [{"id": 1}]
    assert calls["refreshed"] == 1
    assert calls["tokens"] == ["tok1", "tok2"]


def test_collect_does_not_retry_twice_on_401(monkeypatch):
    class FakeResp:
        status_code = 401

    class AuthErr(Exception):
        response = FakeResp()

    monkeypatch.setattr(whoop_client, "_valid_access_token", lambda: "tok")
    monkeypatch.setattr(whoop_client, "refresh", lambda: None)
    monkeypatch.setattr(
        whoop_client, "_request_get", lambda path, params, token: (_ for _ in ()).throw(AuthErr())
    )

    try:
        whoop_client._collect("/recovery", "s", "e")
    except AuthErr:
        pass
    else:
        raise AssertionError("expected AuthErr to propagate after one retry")


def test_whoop_raw_key_falls_back_to_cycle_id():
    from repositories import whoop_raw_repo

    # Recovery records carry no top-level id; they key on cycle_id.
    assert whoop_raw_repo._key({"id": 99, "cycle_id": 7}) == "99"
    assert whoop_raw_repo._key({"cycle_id": 7}) == "7"
    assert whoop_raw_repo._key({"score": {}}) is None
