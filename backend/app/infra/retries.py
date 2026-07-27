"""
Resilient HTTP layer shared by all connectors — US-03.6.

  - Retries only on 5xx, 429 (rate-limited), and network/timeout errors.
    Other 4xx responses are returned as-is, never retried.
  - Exponential backoff 100ms -> 400ms -> 1600ms, max 2 retries.
  - Every attempt logs its duration; persistent failure logs a structured
    entry (source, endpoint, keyword, error_class) and raises ConnectorError
    so the orchestrator can log-and-continue (US-03.4) instead of crashing.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.domain.entities import ConnectorError

logger = logging.getLogger("app.infra.retries")

MAX_RETRIES = 2
_RETRYABLE_STATUS_FLOOR = 500
_RETRYABLE_STATUS_EXTRA = {429}


class _RetryableStatusError(Exception):
    def __init__(self, response: httpx.Response):
        self.response = response
        super().__init__(f"retryable status {response.status_code}")


def _is_retryable_status(status_code: int) -> bool:
    return status_code >= _RETRYABLE_STATUS_FLOOR or status_code in _RETRYABLE_STATUS_EXTRA


def _is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, _RetryableStatusError):
        return True
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


async def call_with_retry(
    request_fn: Callable[[], Awaitable[httpx.Response]],
    *,
    source: str,
    endpoint: str,
    keyword: str,
) -> httpx.Response:
    retrying = AsyncRetrying(
        stop=stop_after_attempt(MAX_RETRIES + 1),
        wait=wait_exponential(multiplier=0.1, exp_base=4, max=1.6),
        retry=retry_if_exception(_is_retryable_exception),
        reraise=True,
    )

    async def _attempt() -> httpx.Response:
        started = time.monotonic()
        response = await request_fn()
        duration_s = time.monotonic() - started
        logger.info(
            "request_completed",
            extra={
                "source": source,
                "endpoint": endpoint,
                "keyword": keyword,
                "status_code": response.status_code,
                "duration_s": round(duration_s, 3),
            },
        )
        if _is_retryable_status(response.status_code):
            raise _RetryableStatusError(response)
        return response

    try:
        return await retrying(_attempt)
    except _RetryableStatusError as exc:
        error_class = f"HTTP{exc.response.status_code}"
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        error_class = type(exc).__name__

    logger.error(
        "request_failed",
        extra={
            "source": source,
            "endpoint": endpoint,
            "keyword": keyword,
            "error_class": error_class,
        },
    )
    raise ConnectorError(
        source=source,
        endpoint=endpoint,
        keyword=keyword,
        error_class=error_class,
        message=f"{source} request to {endpoint} failed after retries: {error_class}",
    )
