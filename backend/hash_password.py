"""Generate a PBKDF2 password value for DOCLOCK_PASSWORD in .env.

    python hash_password.py

Copy the printed line into .env as DOCLOCK_PASSWORD=... and sign in with the ORIGINAL password.
"""
import getpass
import hashlib
import os

ROUNDS = 310_000


def make_hash(password: str, rounds: int = ROUNDS) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds).hex()
    return f"pbkdf2_sha256${rounds}${salt}${digest}"


if __name__ == "__main__":
    first = getpass.getpass("New DocLock password: ")
    if getpass.getpass("Repeat password: ") != first:
        raise SystemExit("Passwords do not match.")
    if len(first) < 10:
        raise SystemExit("Use at least 10 characters.")
    print(make_hash(first))
