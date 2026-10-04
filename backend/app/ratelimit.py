"""Rate limiting for the public chat endpoint.

Why this exists: every question calls the Gemini API (one embedding + one generation), and that
quota is personal and finite. A public demo with no limits can be drained by one script, or by
someone who is just curious and keeps clicking.

Three independent limits, checked in this order:
  1. per client, per minute   (sliding window)  -> stops hammering, tells you how long to wait
  2. per client, per UTC day                    -> stops one visitor using the whole allowance
  3. global, per UTC day                        -> a hard cap on total cost, whoever is asking

A request that is refused consumes nothing, so being blocked never makes the block longer or
eats into the daily allowance.

Honest limits of this design (also in the README):
  * State is in memory, so it is per server process and resets on restart. That is right for a
    single free-tier instance; running several instances would need a shared store such as Redis.
  * The client key is the connection's IP address. Behind a proxy that is only the real visitor if
    the proxy headers are handled correctly, and a determined attacker can rotate addresses. The
    global daily cap is the backstop that still bounds cost in that case.
"""
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Callable

from .config import settings

DAY = 86_400


@dataclass
class Decision:
    allowed: bool
    scope: str | None = None  # "minute" | "day" | "global" when refused
    retry_after: int = 0      # whole seconds until it is worth trying again

    @property
    def message(self) -> str:
        if self.scope == "minute":
            return f"You're asking too quickly. Please wait {self.retry_after} seconds and try again."
        if self.scope == "day":
            return "You've reached today's question limit. Please try again tomorrow."
        if self.scope == "global":
            return "This demo has reached its daily capacity. Please try again tomorrow."
        return ""


@dataclass
class _Client:
    hits: deque = field(default_factory=deque)  # timestamps of allowed requests in the last minute
    day: int = -1                               # which UTC day `day_count` belongs to
    day_count: int = 0


class RateLimiter:
    def __init__(
        self,
        per_minute: int,
        per_client_per_day: int,
        global_per_day: int,
        max_clients: int = 5000,
        clock: Callable[[], float] = time.time,
    ):
        self.per_minute, self.per_client_per_day, self.global_per_day = per_minute, per_client_per_day, global_per_day
        self.max_clients = max_clients
        self._clock = clock
        self._clients: "OrderedDict[str, _Client]" = OrderedDict()
        self._global_day, self._global_count = -1, 0
        self._lock = threading.Lock()  # FastAPI runs sync endpoints on a thread pool

    @classmethod
    def from_settings(cls) -> "RateLimiter":
        return cls(
            settings.rate_limit_per_minute,
            settings.rate_limit_per_client_per_day,
            settings.rate_limit_global_per_day,
            settings.rate_limit_max_clients,
        )

    def check(self, key: str) -> Decision:
        """Decide whether `key` may make a request now, and if so, record it."""
        with self._lock:
            now = self._clock()
            today = int(now // DAY)
            until_midnight = int(DAY - (now % DAY)) + 1

            client = self._clients.get(key)
            if client is None:
                client = self._clients[key] = _Client()
                while len(self._clients) > self.max_clients:  # bound memory: drop the stalest client
                    self._clients.popitem(last=False)
            self._clients.move_to_end(key)

            while client.hits and client.hits[0] <= now - 60:
                client.hits.popleft()
            if client.day != today:
                client.day, client.day_count = today, 0
            if self._global_day != today:
                self._global_day, self._global_count = today, 0

            if len(client.hits) >= self.per_minute:
                wait = int(client.hits[0] + 60 - now) + 1
                return Decision(False, "minute", max(wait, 1))
            if client.day_count >= self.per_client_per_day:
                return Decision(False, "day", until_midnight)
            if self._global_count >= self.global_per_day:
                return Decision(False, "global", until_midnight)

            client.hits.append(now)
            client.day_count += 1
            self._global_count += 1
            return Decision(True)
