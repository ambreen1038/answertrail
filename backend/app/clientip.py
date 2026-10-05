"""Working out which visitor a request really came from.

Behind a hosting platform's proxy, the connection's own address is the PROXY's, the same for every
visitor, so per-visitor rate limits would quietly become one limit shared by everybody. The real
address travels in the `X-Forwarded-For` header, which each proxy on the way appends to.

That header cannot simply be trusted: a visitor can send their own `X-Forwarded-For: 1.2.3.4`, and
the proxy then adds the true address after it. So we count from the RIGHT, skipping exactly as many
entries as there are proxies we trust (`TRUSTED_PROXY_HOPS`). Those entries were written by our own
infrastructure, not by the visitor; everything to their left may be forged and is ignored.

  TRUSTED_PROXY_HOPS=0  (default, local development)  use the connection's address
  TRUSTED_PROXY_HOPS=1  one trusted proxy in front     use the last entry of the header
  TRUSTED_PROXY_HOPS=2  two trusted proxies            use the second-to-last entry, and so on

If the header has fewer entries than expected (a misconfiguration, or a request that bypassed the
proxy) we fall back to the connection's address. That is the safe direction: visitors are then
limited together instead of escaping the limit.
"""
from fastapi import Request

from .config import settings


def forwarded_chain(request: Request) -> list[str]:
    raw = request.headers.get("x-forwarded-for", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def client_ip(request: Request) -> str:
    hops = settings.trusted_proxy_hops
    if hops > 0:
        chain = forwarded_chain(request)
        if len(chain) >= hops:
            return chain[-hops]
    return request.client.host if request.client else "unknown"
