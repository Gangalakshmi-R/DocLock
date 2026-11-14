from datetime import datetime, timedelta, timezone

import importlib.util
from pathlib import Path

import jwt
import pytest

from app import config, security

GOOD = {"username": "tester", "password": "correct-horse-battery"}


def test_login_success_returns_a_working_token(client):
    r = client.post("/api/auth/login", json=GOOD)
    assert r.status_code == 200
    token = r.json()["token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json() == {"username": "tester"}


def test_wrong_password_and_wrong_username_are_rejected(client):
    assert client.post("/api/auth/login", json={**GOOD, "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={**GOOD, "username": "someone"}).status_code == 401
    # same message for both, so an attacker cannot tell which field was wrong
    a = client.post("/api/auth/login", json={**GOOD, "password": "nope"}).json()
    b = client.post("/api/auth/login", json={**GOOD, "username": "someone"}).json()
    assert a == b


def test_non_ascii_credentials_do_not_crash(client):
    assert client.post("/api/auth/login", json={"username": "tëster", "password": "pässwörd✓"}).status_code == 401


def test_repeated_failures_are_rate_limited_and_success_resets(client):
    for _ in range(config.LOGIN_MAX_ATTEMPTS):
        assert client.post("/api/auth/login", json={**GOOD, "password": "bad"}).status_code == 401
    blocked = client.post("/api/auth/login", json=GOOD)  # even the right password is refused while locked out
    assert blocked.status_code == 429
    assert "Too many" in blocked.json()["message"]


def test_a_success_clears_earlier_failures(client):
    for _ in range(config.LOGIN_MAX_ATTEMPTS - 1):
        client.post("/api/auth/login", json={**GOOD, "password": "bad"})
    assert client.post("/api/auth/login", json=GOOD).status_code == 200
    for _ in range(config.LOGIN_MAX_ATTEMPTS - 1):  # counter was reset, so these do not lock us out
        assert client.post("/api/auth/login", json={**GOOD, "password": "bad"}).status_code == 401


def test_protected_routes_require_a_valid_bearer_token(client):
    for path in ("/api/documents", "/api/alerts", "/api/chat/conversations"):
        assert client.get(path).status_code == 401
    assert client.get("/api/documents", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/documents", headers={"Authorization": "Basic abc"}).status_code == 401


def test_expired_and_wrongly_signed_tokens_are_rejected(client):
    now = datetime.now(timezone.utc)
    expired = jwt.encode({"sub": "tester", "exp": now - timedelta(minutes=1)}, config.JWT_SECRET, algorithm="HS256")
    forged = jwt.encode({"sub": "tester", "exp": now + timedelta(hours=1)}, "another-secret-another-secret-another", algorithm="HS256")
    for token in (expired, forged):
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_health_is_public(client):
    assert client.get("/actuator/health").json()["status"] == "UP"
    assert client.get("/health").status_code == 200


def test_validation_errors_use_the_message_format_the_frontend_expects(client):
    r = client.post("/api/auth/login", json={"username": "x"})
    assert r.status_code == 422 and "message" in r.json()


# ---------------------------------------------------------------- PBKDF2 password hashes (DOCLOCK_PASSWORD may be a hash)
def test_hash_and_verify_roundtrip():
    stored = security.hash_password("s3cret-pass!", rounds=1000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert security.verify_password("s3cret-pass!", stored)
    assert not security.verify_password("s3cret-pass?", stored)
    assert security.hash_password("s3cret-pass!", rounds=1000) != stored  # random salt each time


@pytest.mark.parametrize("broken", ["pbkdf2_sha256$", "pbkdf2_sha256$abc$salt$digest", "pbkdf2_sha256$1000$salt", "pbkdf2_sha256$1000$salt$zz✓"])
def test_malformed_hash_never_matches_and_never_raises(broken):
    assert security.verify_password("anything", broken) is False


def test_login_works_when_password_is_stored_as_a_hash(client, monkeypatch):
    monkeypatch.setattr(config, "PASSWORD", security.hash_password("hashed-login-pw", rounds=1000))
    ok = client.post("/api/auth/login", json={"username": "tester", "password": "hashed-login-pw"})
    assert ok.status_code == 200
    assert client.post("/api/auth/login", json={"username": "tester", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "tester", "password": config.PASSWORD}).status_code == 401  # the hash itself is not a password


def test_hash_password_script_output_is_accepted_by_the_server():
    script = Path(__file__).resolve().parents[1] / "hash_password.py"
    spec = importlib.util.spec_from_file_location("hash_password_script", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # importing must not prompt for a password
    stored = module.make_hash("from-the-script", rounds=1000)
    assert security.verify_password("from-the-script", stored)
