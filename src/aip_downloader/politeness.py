"""Politeness controls: concurrency cap, jittered delays, retry/backoff.

Centralised here so auth/version/discover/download all throttle identically and
the live ENAV server is never hammered. Dependencies (sleep, RNG) are injectable
so tests stay deterministic and fast.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class PolitenessPolicy:
    """Knobs governing how gently we talk to the server."""

    max_concurrency: int = 2
    delay_seconds: float = 1.0
    jitter_seconds: float = 0.3
    user_agent: str = "aip-downloader/0.1 (+personal AIP archival)"
    max_attempts: int = 5
    backoff_base: float = 2.0
    backoff_max: float = 60.0


class Throttle:
    """Bounds concurrency and spaces out requests.

    Use as ``async with throttle.slot(): ...`` around each network call.
    """

    def __init__(
        self,
        policy: PolitenessPolicy,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._policy = policy
        self._sleep = sleep
        self._rng = rng
        self._semaphore = asyncio.Semaphore(policy.max_concurrency)

    @asynccontextmanager
    async def slot(self):
        async with self._semaphore:
            delay = (
                self._policy.delay_seconds + self._rng() * self._policy.jitter_seconds
            )
            if delay > 0:
                await self._sleep(delay)
            yield


async def retry[T](
    func: Callable[[], Awaitable[T]],
    *,
    policy: PolitenessPolicy,
    is_retryable: Callable[[Exception], bool],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run ``func`` with exponential backoff on retryable exceptions.

    Re-raises immediately on non-retryable errors or once attempts are exhausted.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await func()
        except Exception as exc:  # noqa: BLE001 - re-raised below if not retryable
            if attempt >= policy.max_attempts or not is_retryable(exc):
                raise
            backoff = min(
                policy.backoff_base ** (attempt - 1),
                policy.backoff_max,
            )
            await sleep(backoff)
