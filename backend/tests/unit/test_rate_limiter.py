import pytest

from app.orchestrator.rate_limiter import AsyncRateLimiter


@pytest.mark.asyncio
async def test_acquire_waits_min_interval_between_calls(monkeypatch):
    fake_clock = [0.0]
    sleep_calls: list[float] = []

    def fake_monotonic() -> float:
        return fake_clock[0]

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        fake_clock[0] += seconds

    monkeypatch.setattr("app.orchestrator.rate_limiter.time.monotonic", fake_monotonic)
    monkeypatch.setattr("app.orchestrator.rate_limiter.asyncio.sleep", fake_sleep)

    limiter = AsyncRateLimiter(min_interval_s=3.0)
    await limiter.acquire()
    await limiter.acquire()

    assert sleep_calls == [pytest.approx(3.0)]


@pytest.mark.asyncio
async def test_acquire_does_not_wait_once_interval_has_elapsed(monkeypatch):
    fake_clock = [0.0]
    sleep_calls: list[float] = []

    def fake_monotonic() -> float:
        return fake_clock[0]

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("app.orchestrator.rate_limiter.time.monotonic", fake_monotonic)
    monkeypatch.setattr("app.orchestrator.rate_limiter.asyncio.sleep", fake_sleep)

    limiter = AsyncRateLimiter(min_interval_s=3.0)
    await limiter.acquire()
    fake_clock[0] += 5.0  # plenty of time already passed since the first call
    await limiter.acquire()

    assert sleep_calls == []
