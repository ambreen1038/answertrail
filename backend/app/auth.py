"""Admin authentication using Supabase Auth.

The browser signs in with supabase-js and sends its access token as `Authorization: Bearer ...`.
We do not decode or trust that token ourselves. We hand it to Supabase (GET /auth/v1/user) and let
Supabase say who it belongs to. That works whatever signing algorithm the project uses, and a
revoked or expired session is rejected on the spot.

Being signed in is not enough to be an admin. The account must also have a CONFIRMED email that
is on the ADMIN_EMAILS allowlist, so someone who somehow registers an account still gets a 403.

Failure modes, deliberately distinct:
  not configured / Supabase unreachable -> 503  (the server can't decide; never let anyone in)
  missing or invalid token              -> 401  (you are not signed in)
  valid user, not an admin              -> 403  (you are signed in, but not allowed)
"""
from dataclasses import dataclass

import httpx
from fastapi import Header, HTTPException

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
