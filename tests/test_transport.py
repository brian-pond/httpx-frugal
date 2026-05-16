"""Tests for rate-limited transports."""

import httpx
import pytest
from pyrate_limiter import Limiter, Rate
from pyrate_limiter.buckets import InMemoryBucket

from httpx_frugal.exceptions import HTTPRateLimitError
from httpx_frugal.transport import AsyncDomainRateLimitedTransport, DomainRateLimitedTransport


def _mock_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"url": str(request.url)})


@pytest.mark.parametrize("transport_cls", [DomainRateLimitedTransport])
def test_rate_limit_raises_when_exhausted(transport_cls, rates: list[Rate]) -> None:
    bucket = InMemoryBucket(rates)
    limiter = Limiter(bucket)
    transport = transport_cls(
        limiter=limiter,
        inner_transport=httpx.MockTransport(_mock_response),
        blocking=False,
    )

    request = httpx.Request("GET", "https://example.com/resource")
    for _ in range(5):
        transport.handle_request(request)

    with pytest.raises(HTTPRateLimitError, match="example.com"):
        transport.handle_request(request)


@pytest.mark.asyncio
async def test_async_rate_limit_raises_when_exhausted(rates: list[Rate]) -> None:
    bucket = InMemoryBucket(rates)
    limiter = Limiter(bucket)

    async def async_mock(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": str(request.url)})

    transport = AsyncDomainRateLimitedTransport(
        limiter=limiter,
        inner_transport=httpx.MockTransport(async_mock),
        blocking=False,
    )

    request = httpx.Request("GET", "https://example.com/resource")
    for _ in range(5):
        await transport.handle_async_request(request)

    with pytest.raises(HTTPRateLimitError, match="example.com"):
        await transport.handle_async_request(request)


def test_transport_rejects_url_without_host(rates: list[Rate]) -> None:
    bucket = InMemoryBucket(rates)
    limiter = Limiter(bucket)
    transport = DomainRateLimitedTransport(
        limiter=limiter,
        inner_transport=httpx.MockTransport(_mock_response),
    )
    request = httpx.Request("GET", "/relative/path")

    with pytest.raises(HTTPRateLimitError, match="no host"):
        transport.handle_request(request)
