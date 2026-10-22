"""Per-client token-bucket rate limiting (in memory; fine for a single-process server)."""

from __future__ import annotations

import threading
import time

from starlette.requests import HTTPConnection


class TokenBucket:
    """``rate`` tokens per second, bursts up to ``burst``; one bucket per client key."""

    def __init__(self, rate: float, burst: int, max_clients: int = 10_000):
        self.rate = rate
        self.burst = burst
        self.max_clients = max_clients
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_ts)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """Take one token. Returns (allowed, seconds until the next token if denied)."""
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0.0
            self._buckets[key] = (tokens, now)
            if len(self._buckets) > self.max_clients:  # crude bound on memory
                self._buckets.clear()
            return False, (1.0 - tokens) / self.rate


def client_ip(conn: HTTPConnection, trust_proxy: bool) -> str:
    """The real client address.

    Behind our own proxies (Cloudflare tunnel -> Caddy -> app) the socket peer is the
    proxy, so we read forwarding headers -- but only when configured to trust them, since
    a client talking to the app directly could forge them. Caddy strips an incoming
    CF-Connecting-IP on the direct (non-Cloudflare) site, so it can't be spoofed there.
    """
    if trust_proxy:
        cf = conn.headers.get("cf-connecting-ip")
        if cf:
            return cf.strip()
        xff = conn.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()  # appended by our proxy; the rest is client-controlled
    return conn.client.host if conn.client else "unknown"
