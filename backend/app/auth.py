"""Sign-in using Supabase Auth: optional for customers, required (plus an allowlist) for admins.

The browser signs in with supabase-js and sends its access token as `Authorization: Bearer ...`.
We do not decode or trust that token ourselves. We hand it to Supabase (GET /auth/v1/user) and let
Supabase say who it belongs to. That works whatever signing algorithm the project uses, and a
revoked or expired session is rejected on the spot.

Being signed in is not enough to be an admin. The account must also have a CONFIRMED email that
is on the ADMIN_EMAILS allowlist, so someone who somehow registers an account still gets a 403.

Customers may also sign in (optional): a signed-in customer's conversations belong to their account
and follow them across devices. Anonymous chatting keeps working with no account at all. Signing up
gives no admin rights; only the allowlist does.

Failure modes, deliberately distinct:
  not configured / Supabase unreachable -> 503  (the server can't decide; never let anyone in)
  missing or invalid token              -> 401  (you are not signed in)
  valid user, not an admin              -> 403  (you are signed in, but not allowed)
"""
from dataclasses import dataclass

import hashlib
import threading
import time

import httpx
from fastapi import Depends, Header, HTTPException

from .config import settings


class InvalidToken(Exception):
    """Supabase says this token is not valid (expired, forged, signed out)."""


class AuthUnavailable(Exception):
    """We could not reach Supabase, so we cannot tell whether the token is valid."""


@dataclass
class AdminUser:
    id: str
    email: str


def admin_emails() -> set[str]:
    return {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}


def is_configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_anon_key and admin_emails())


def accounts_configured() -> bool:
    """Customer sign-in only needs Supabase itself; the admin allowlist is irrelevant to it."""
    return bool(settings.supabase_url and settings.supabase_anon_key)


def _fetch_user(access_token: str) -> dict:
    """Ask Supabase who owns this access token. Returns the user object."""
    try:
        resp = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {access_token}"},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
    except httpx.HTTPError as exc:
        raise AuthUnavailable(type(exc).__name__) from exc
    if resp.status_code in (401, 403):
        raise InvalidToken()
    if resp.status_code != 200:
        raise AuthUnavailable(f"HTTP {resp.status_code}")
    return resp.json()


def require_admin(authorization: str | None = Header(default=None)) -> AdminUser:
    if not is_configured():
        raise HTTPException(status_code=503, detail="Admin access is not configured on this server.")

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Sign in to continue.")

    try:
        user = _fetch_user(token.strip())
    except InvalidToken:
        raise HTTPException(status_code=401, detail="Your session is not valid. Please sign in again.") from None
    except AuthUnavailable:
        raise HTTPException(status_code=503, detail="The sign-in service is temporarily unavailable.") from None

    email = (user.get("email") or "").lower()
    if not user.get("email_confirmed_at") or email not in admin_emails():
        raise HTTPException(status_code=403, detail="This account is not an administrator.")
    return AdminUser(id=user["id"], email=email)


# ------------------------------------------------------------------ customer accounts


@dataclass
class User:
    id: str
    email: str
    is_admin: bool


def _bearer(authorization: str | None) -> str | None:
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


# Asking a question is the hot path, and checking a token costs a round trip to Supabase. Remember
# a verified token for a short time. The trade-off: a token that was just revoked (signed out
# elsewhere) can still work here for up to TTL seconds. Admin endpoints never use this cache.
_TOKEN_TTL = 30.0
_MAX_CACHED = 1000
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def clear_token_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _verified_user(token: str) -> dict:
    key = hashlib.sha256(token.encode()).hexdigest()  # never keep the token itself around
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    user = _fetch_user(token)
    with _cache_lock:
        if len(_cache) >= _MAX_CACHED:
            _cache.clear()  # crude but bounded; entries are cheap to recompute
        _cache[key] = (now + _TOKEN_TTL, user)
    return user


def _to_user(raw: dict) -> User:
    email = (raw.get("email") or "").lower()
    is_admin = bool(raw.get("email_confirmed_at")) and email in admin_emails()
    return User(id=raw["id"], email=email, is_admin=is_admin)


def current_user(authorization: str | None = Header(default=None)) -> User | None:
    """For endpoints anyone may use. No token = anonymous (None). A token that is present must be
    valid: silently treating a bad token as 'anonymous' would let a signed-in customer's chat be
    saved to nobody's account without them noticing."""
    token = _bearer(authorization)
    if token is None:
        return None
    if not accounts_configured():
        raise HTTPException(status_code=503, detail="Sign-in is not configured on this server.")
    try:
        return _to_user(_verified_user(token))
    except InvalidToken:
        raise HTTPException(status_code=401, detail="Your session is not valid. Please sign in again.") from None
    except AuthUnavailable:
        raise HTTPException(status_code=503, detail="The sign-in service is temporarily unavailable.") from None


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user
