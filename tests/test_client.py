"""Tests for RateLimitedCacheClient."""

from __future__ import annotations

import pathlib

import httpx
import pytest
from pyrate_limiter import Duration, Rate

from helpers import build_sync_http_client
from httpx_frugal import HTTPRateLimitError, RateLimitedCacheClient, request_with_ttl
from httpx_frugal._common import validate_rates


def _no_store_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"path": str(request.url.path)},
        headers={"cache-control": "no-store"},
    )


@pytest.fixture
def strict_rate() -> list[Rate]:
    return [Rate(1, Duration.SECOND)]


def test_path_validation_missing_parent(tmp_path: pathlib.Path, rates: list[Rate]) -> None:
    missing = tmp_path / "nope" / "cache.sqlite"
    rate_db = tmp_path / "also-nope" / "rate.sqlite"

    with pytest.raises(FileNotFoundError, match="Cache database directory"):
        RateLimitedCacheClient(
            rates=rates,
            cache_db_path=missing,
            rate_limiter_db_path=rate_db,
        )


def test_path_validation_not_a_file(tmp_path: pathlib.Path, rates: list[Rate]) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    rate_db = tmp_path / "rate.sqlite"

    with pytest.raises(FileExistsError, match="not a file"):
        RateLimitedCacheClient(
            rates=rates,
            cache_db_path=cache_dir,
            rate_limiter_db_path=rate_db,
        )


def test_invalid_rates_raise_value_error() -> None:
    bad_rates = [Rate(100, Duration.SECOND), Rate(1, Duration.MINUTE)]
    with pytest.raises(ValueError, match="Invalid rate list"):
        validate_rates(bad_rates)


def test_build_client_rejects_invalid_rates(
    cache_db_path: pathlib.Path,
    rate_db_path: pathlib.Path,
) -> None:
    bad_rates = [Rate(100, Duration.SECOND), Rate(1, Duration.MINUTE)]
    client = RateLimitedCacheClient(
        rates=bad_rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
    )
    with pytest.raises(ValueError, match="Invalid rate list"):
        client._build_client()


def test_cache_hit_on_second_request(
    cache_db_path: pathlib.Path,
    rate_db_path: pathlib.Path,
    rates: list[Rate],
) -> None:
    url = "https://example.com/api/data"
    wrapper = RateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
        cache_ttl=300,
    )
    call_count = 0

    def counting_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return _no_store_response(request)

    http, bucket = build_sync_http_client(wrapper, counting_handler)
    try:
        assert wrapper.would_hit_cache(url) is False
        r1 = http.get(url)
        assert r1.extensions.get("hishel_from_cache") is False
        assert call_count == 1

        assert wrapper.would_hit_cache(url) is True
        r2 = http.get(url)
        assert r2.extensions.get("hishel_from_cache") is True
        assert call_count == 1
    finally:
        http.close()
        bucket.close()


def test_clear_cache(
    cache_db_path: pathlib.Path,
    rate_db_path: pathlib.Path,
    rates: list[Rate],
) -> None:
    url = "https://example.com/clear-me"
    wrapper = RateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
    )
    http, bucket = build_sync_http_client(wrapper, _no_store_response)
    try:
        http.get(url)
        assert wrapper.would_hit_cache(url) is True
        wrapper.clear_cache()
        assert wrapper.would_hit_cache(url) is False
    finally:
        http.close()
        bucket.close()


def test_clear_cache_for_leaves_other_urls(
    cache_db_path: pathlib.Path,
    rate_db_path: pathlib.Path,
    rates: list[Rate],
) -> None:
    url_a = "https://example.com/a"
    url_b = "https://example.com/b"
    wrapper = RateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
    )
    http, bucket = build_sync_http_client(wrapper, _no_store_response)
    try:
        http.get(url_a)
        http.get(url_b)
        wrapper.clear_cache_for(url_a)
        assert wrapper.would_hit_cache(url_a) is False
        assert wrapper.would_hit_cache(url_b) is True
    finally:
        http.close()
        bucket.close()


def test_rate_limit_on_cache_miss(
    cache_db_path: pathlib.Path,
    rate_db_path: pathlib.Path,
    strict_rate: list[Rate],
) -> None:
    wrapper = RateLimitedCacheClient(
        rates=strict_rate,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
        cache_ttl=300,
    )
    http, bucket = build_sync_http_client(wrapper, _no_store_response, rates=strict_rate)
    try:
        http.get("https://example.com/one")
        with pytest.raises(HTTPRateLimitError):
            http.get("https://example.com/two")
    finally:
        http.close()
        bucket.close()


def test_tokens_available(
    cache_db_path: pathlib.Path,
    rate_db_path: pathlib.Path,
    rates: list[Rate],
) -> None:
    wrapper = RateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
    )
    before = wrapper.tokens_available("example.com")
    assert before["5/1000s"] == 5

    http, bucket = build_sync_http_client(wrapper, _no_store_response)
    try:
        http.get("https://example.com/usage")
    finally:
        http.close()
        bucket.close()

    after = wrapper.tokens_available("example.com")
    assert after["5/1000s"] == 4


def test_context_manager_closes_client(
    cache_db_path: pathlib.Path,
    rate_db_path: pathlib.Path,
    rates: list[Rate],
) -> None:
    wrapper = RateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
    )
    with wrapper as http:
        assert not http.is_closed
    assert wrapper._client is None


def test_request_with_ttl_sets_extension() -> None:
    client = httpx.Client()
    try:
        req = request_with_ttl(client, "GET", "https://example.com/x", ttl=42)
        assert req.extensions["hishel_ttl"] == 42
    finally:
        client.close()


def test_per_request_ttl_creates_separate_cache_entries(
    cache_db_path: pathlib.Path,
    rate_db_path: pathlib.Path,
    rates: list[Rate],
) -> None:
    url = "https://example.com/ttl-test"
    wrapper = RateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
        cache_ttl=300,
    )
    http, bucket = build_sync_http_client(wrapper, _no_store_response)
    try:
        http.get(url, extensions={"hishel_ttl": 60})
        http.get(url, extensions={"hishel_ttl": 120})
        assert wrapper.would_hit_cache(url) is True
    finally:
        http.close()
        bucket.close()
