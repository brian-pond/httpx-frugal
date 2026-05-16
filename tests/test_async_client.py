"""Tests for AsyncRateLimitedCacheClient."""

import httpx
import pytest
from pyrate_limiter import Rate

from helpers import build_async_http_client
from httpx_frugal import AsyncRateLimitedCacheClient


def _no_store_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True}, headers={"cache-control": "no-store"})


@pytest.mark.asyncio
async def test_async_cache_hit(
    cache_db_path,
    rate_db_path,
    rates: list[Rate],
) -> None:
    url = "https://example.com/async"
    wrapper = AsyncRateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _no_store_response(request)

    http, bucket = build_async_http_client(wrapper, handler)
    try:
        r1 = await http.get(url)
        assert r1.extensions.get("hishel_from_cache") is False
        r2 = await http.get(url)
        assert r2.extensions.get("hishel_from_cache") is True
        assert calls == 1
    finally:
        await http.aclose()
        bucket.close()


@pytest.mark.asyncio
async def test_async_context_manager(
    cache_db_path,
    rate_db_path,
    rates: list[Rate],
) -> None:
    wrapper = AsyncRateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
    )
    async with wrapper as http:
        assert not http.is_closed
    assert wrapper._client is None


@pytest.mark.asyncio
async def test_async_tokens_available(
    cache_db_path,
    rate_db_path,
    rates: list[Rate],
) -> None:
    wrapper = AsyncRateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
    )
    before = wrapper.tokens_available("example.com")
    assert before["5/1000s"] == 5

    http, bucket = build_async_http_client(wrapper, _no_store_response)
    try:
        await http.get("https://example.com/async-usage")
    finally:
        await http.aclose()
        bucket.close()

    after = wrapper.tokens_available("example.com")
    assert after["5/1000s"] == 4
