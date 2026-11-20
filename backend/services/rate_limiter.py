"""In-memory per-IP token-bucket rate limiter for public API endpoints."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class TokenBucketRateLimiter:
    """Thread-safe in-memory per-IP token bucket.

    Default policy: 30 tokens per 600 seconds (10 minutes) per IP.
    Expensive endpoints (e.g. /api/line-run) consume more tokens via `cost`.
    """

    def __init__(self, capacity: int = 30, window_seconds: int = 600) -> None:
        self.capacity = float(capacity)
        self.window_seconds = float(window_seconds)
        self.refill_rate = self.capacity / self.window_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def consume(self, key: str, cost: int = 1) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, last_refill=now)
                self._buckets[key] = bucket
            else:
                elapsed = max(0.0, now - bucket.last_refill)
                bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_rate)
                bucket.last_refill = now

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True, 0

            needed = cost - bucket.tokens
            retry_after = max(1, math.ceil(needed / self.refill_rate))
            return False, retry_after

    def check_request(self, request: Request, cost: int = 1) -> None:
        ip = self._client_ip(request)
        allowed, retry_after = self.consume(ip, cost=cost)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded ({int(self.capacity)} requests per "
                    f"{int(self.window_seconds // 60)} minutes). "
                    f"Please wait {retry_after}s and try again."
                ),
                headers={"Retry-After": str(retry_after)},
            )
