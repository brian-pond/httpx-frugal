"""Ported demo from original_source_code.py using mocks (no network)."""

import pathlib

import httpx
from pyrate_limiter import Duration, Rate

from helpers import build_sync_http_client
from httpx_frugal import RateLimitedCacheClient


def test_recipe_style_demo(
    cache_db_path: pathlib.Path,
    rate_db_path: pathlib.Path,
) -> None:
    """Exercise cache probe + GET flow like the original CLI demo."""
    recipe_url = "https://dummyjson.com/recipes/1"
    rates = [
        Rate(5, Duration.MINUTE),
        Rate(15, Duration.HOUR),
        Rate(100, Duration.DAY * 2),
    ]

    cache_client = RateLimitedCacheClient(
        rates=rates,
        cache_db_path=cache_db_path,
        rate_limiter_db_path=rate_db_path,
    )

    assert cache_client.would_hit_cache(recipe_url) is False

    def recipe_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": 1, "name": "Test Recipe"},
            headers={"cache-control": "no-cache"},
        )

    http, bucket = build_sync_http_client(cache_client, recipe_handler, rates=rates)
    try:
        response = http.get(recipe_url)
        assert response.extensions.get("hishel_from_cache") is False
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "no-cache"

        response2 = http.get(recipe_url)
        assert response2.extensions.get("hishel_from_cache") is True
    finally:
        http.close()
        bucket.close()

    assert cache_client.would_hit_cache(recipe_url) is True
