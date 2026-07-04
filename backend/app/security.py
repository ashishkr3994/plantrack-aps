"""Authentication & authorization primitives.

Password hashing uses PBKDF2-HMAC-SHA256 from the standard library. Access tokens
are short-lived signed JWTs; refresh tokens are opaque random strings stored only
as hashes. The signing secret comes from central settings (which fails fast in
production if left at the insecure default).
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError

from .config import settings

ALGORITHM = "HS256"
PBKDF2_ROUNDS = 240_000


def _secret() -> str:
    return settings.SECRET_KEY


# ---- password hashing ----
def hash_password(password: str) -> str:
    """Return 'pbkdf2_sha256$rounds$salt_hex$hash_hex'."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds_s, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt_hex), int(rounds_s))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# ---- access tokens (JWT) ----
def create_access_token(sub: str, role: str, uid: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub, "role": role, "uid": uid, "typ": "access",
        "iat": now, "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MIN),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except JWTError:
        return None


# ---- refresh tokens (opaque, stored hashed) ----
def generate_refresh_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). The raw token is shown to the client once;
    only the hash is persisted."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
