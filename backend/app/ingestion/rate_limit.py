"""Cooperative async rate limiter for provider clients."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    def __init__(
        self,
        calls_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if calls_per_minute < 1:
            raise ValueError("calls_per_minute must be positive")
        self._interval = 60.0 / calls_per_minute
        self._clock = clock
        self._sleep = sleep
        self._next_allowed = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            wait = self._next_allowed - now
            if wait > 0:
                await self._sleep(wait)
                now = self._clock()
            self._next_allowed = max(now, self._next_allowed) + self._interval
