"""Authentication: constant-time credential check, JWT helpers and a small login rate limiter."""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Header, HTTPException

from app import config


PBKDF2_PREFIX = "pbkdf2_sha256$"
PBKDF2_ROUNDS = 310_000


def hash_password(password: str, rounds: int = PBKDF2_ROUNDS) -> str:
    """Value to put in DOCLOCK_PASSWORD: ``pbkdf2_sha256$<rounds>$<salt>$<hex digest>``."""
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds).hex()
    return f"{PBKDF2_PREFIX}{rounds}${salt}${digest}"


def verify_password(candidate: str, configured: str) -> bool:
    """Check *candidate* against DOCLOCK_PASSWORD, which is either a PBKDF2 hash or (legacy) plain text.

    Always uses a constant-time comparison. A malformed hash never raises: it simply fails to match."""
    if configured.startswith(PBKDF2_PREFIX):
        try:
            _, rounds, salt, expected = configured.split("$", 3)
            actual = hashlib.pbkdf2_hmac("sha256", candidate.encode("utf-8"), salt.encode("utf-8"), int(rounds)).hex()
            return hmac.compare_digest(actual.encode("ascii"), expected.encode("ascii", "ignore"))
        except (ValueError, TypeError):
            return False
    return hmac.compare_digest(candidate.encode("utf-8"), configured.encode("utf-8"))


def credentials_valid(username: str, password: str) -> bool:
    """Check both fields every time (no early exit) so the response does not reveal which one was wrong."""
    user_ok = hmac.compare_digest(username.encode("utf-8"), config.USERNAME.encode("utf-8"))
    pass_ok = verify_password(password, config.PASSWORD)
    return user_ok and pass_ok


def create_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "iat": now, "exp": now + timedelta(milliseconds=config.JWT_EXPIRATION_MS)}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def current_user(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        payload = jwt.decode(authorization[7:], config.JWT_SECRET, algorithms=["HS256"])
        user = payload.get("sub")
        if not user:
            raise ValueError("Missing subject")
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")


class LoginRateLimiter:
    """Sliding-window limiter on *failed* logins, keyed by client address.

    In-memory and per-process: enough for this single-worker, single-user deployment.
    Behind the bundled nginx every request shares one address, which simply makes the limit global.
    """

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        window = self._failures[key]
        while window and now - window[0] > config.LOGIN_WINDOW_SECONDS:
            window.popleft()
        return window

    def check(self, key: str) -> None:
        with self._lock:
            if len(self._prune(key, time.monotonic())) >= config.LOGIN_MAX_ATTEMPTS:
                raise HTTPException(status_code=429, detail="Too many failed login attempts. Please wait a few minutes and try again.")

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._failures.clear()
            else:
                self._failures.pop(key, None)


login_limiter = LoginRateLimiter()
