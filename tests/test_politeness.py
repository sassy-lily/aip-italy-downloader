"""Concurrency cap and retry/backoff behaviour."""

from __future__ import annotations

import asyncio

import pytest

from aip_downloader.politeness import PolitenessPolicy, Throttle, retry


async def test_retry_succeeds_after_transient_failures():
    calls = 0
    sleeps: list[float] = []

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ValueError("boom")
        return "ok"

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    policy = PolitenessPolicy(max_attempts=5, backoff_base=2.0, backoff_max=60.0)
    result = await retry(
        flaky, policy=policy, is_retryable=lambda _: True, sleep=fake_sleep
    )

    assert result == "ok"
    assert calls == 3
    assert sleeps == [1.0, 2.0]  # 2**0, 2**1


async def test_retry_stops_on_non_retryable():
    calls = 0

    async def always_fail() -> None:
        nonlocal calls
        calls += 1
        raise ValueError()

    async def fake_sleep(_: float) -> None:
        pass

    with pytest.raises(ValueError):
        await retry(
            always_fail,
            policy=PolitenessPolicy(max_attempts=5),
            is_retryable=lambda _: False,
            sleep=fake_sleep,
        )
    assert calls == 1


async def test_retry_exhausts_attempts():
    calls = 0

    async def always_fail() -> None:
        nonlocal calls
        calls += 1
        raise ValueError()

    async def fake_sleep(_: float) -> None:
        pass

    with pytest.raises(ValueError):
        await retry(
            always_fail,
            policy=PolitenessPolicy(max_attempts=3),
            is_retryable=lambda _: True,
            sleep=fake_sleep,
        )
    assert calls == 3


async def test_throttle_caps_concurrency():
    policy = PolitenessPolicy(max_concurrency=2, delay_seconds=0.0, jitter_seconds=0.0)
    throttle = Throttle(policy, rng=lambda: 0.0)
    active = 0
    peak = 0

    async def worker() -> None:
        nonlocal active, peak
        async with throttle.slot():
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(worker() for _ in range(6)))
    assert peak <= 2
