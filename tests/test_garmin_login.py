"""Garmin token-based auth: resume from a saved token, fall back to password
and persist the minted token. The garminconnect library is faked entirely."""

from __future__ import annotations

import sys
import types

import pytest

from clients import garmin_client


class FakeGarth:
    def __init__(self):
        self.loaded = None

    def loads(self, token):
        if token == "bad":
            raise RuntimeError("token expired")
        self.loaded = token

    def dumps(self):
        return "MINTED"


class FakeGarmin:
    last_init = None

    def __init__(self, email=None, password=None):
        FakeGarmin.last_init = (email, password)
        self.garth = FakeGarth()
        self.logged_in = False

    def login(self):
        self.logged_in = True


@pytest.fixture
def fake_garminconnect(monkeypatch):
    FakeGarmin.last_init = None
    mod = types.ModuleType("garminconnect")
    mod.Garmin = FakeGarmin
    monkeypatch.setitem(sys.modules, "garminconnect", mod)
    # No env token unless a test sets one.
    monkeypatch.delenv("GARMIN_TOKENS", raising=False)
    return mod


def test_resumes_from_db_token_without_password(fake_garminconnect, monkeypatch):
    monkeypatch.setattr(garmin_client.oauth_tokens_repo, "get", lambda p: {"access_token": "DBTOKEN"})

    client = garmin_client.login()

    assert client.garth.loaded == "DBTOKEN"
    assert FakeGarmin.last_init == (None, None)  # built without credentials
    assert client.logged_in is False  # resumed, never called password login


def test_env_token_takes_precedence(fake_garminconnect, monkeypatch):
    monkeypatch.setenv("GARMIN_TOKENS", "ENVTOKEN")

    def boom(_p):
        raise AssertionError("should not read the DB when env token is set")

    monkeypatch.setattr(garmin_client.oauth_tokens_repo, "get", boom)

    client = garmin_client.login()
    assert client.garth.loaded == "ENVTOKEN"


def test_password_fallback_persists_token(fake_garminconnect, monkeypatch):
    monkeypatch.setattr(garmin_client.oauth_tokens_repo, "get", lambda p: None)
    monkeypatch.setenv("GARMIN_EMAIL", "a@b.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "pw")
    stored = {}
    monkeypatch.setattr(
        garmin_client.oauth_tokens_repo, "upsert",
        lambda provider, access_token, refresh_token, expires_at, scope=None: stored.update(
            provider=provider, token=access_token
        ),
    )

    client = garmin_client.login()

    assert FakeGarmin.last_init == ("a@b.com", "pw")
    assert client.logged_in is True
    assert stored == {"provider": "garmin", "token": "MINTED"}


def test_unusable_token_falls_back_to_password(fake_garminconnect, monkeypatch):
    monkeypatch.setattr(garmin_client.oauth_tokens_repo, "get", lambda p: {"access_token": "bad"})
    monkeypatch.setenv("GARMIN_EMAIL", "a@b.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "pw")
    monkeypatch.setattr(
        garmin_client.oauth_tokens_repo, "upsert",
        lambda provider, access_token, refresh_token, expires_at, scope=None: None,
    )

    client = garmin_client.login()
    assert client.logged_in is True  # bad token -> password login


def test_password_login_block_gives_actionable_error(fake_garminconnect, monkeypatch):
    monkeypatch.setattr(garmin_client.oauth_tokens_repo, "get", lambda p: None)
    monkeypatch.setenv("GARMIN_EMAIL", "a@b.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "pw")

    class Blocked(FakeGarmin):
        def login(self):
            raise RuntimeError("Portal login failed (non-JSON): HTTP 403")

    fake_garminconnect.Garmin = Blocked

    # The raw 403 is wrapped with guidance toward token auth.
    with pytest.raises(RuntimeError, match="garmin_login"):
        garmin_client.login()


def test_no_token_no_credentials_raises(fake_garminconnect, monkeypatch):
    monkeypatch.setattr(garmin_client.oauth_tokens_repo, "get", lambda p: None)
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="garmin_login"):
        garmin_client.login()
