"""Test helpers for building httpx clients with mock transports."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from hishel.httpx import AsyncCacheTransport, SyncCacheTransport
from pyrate_limiter import Limiter, Rate, SQLiteBucket

from httpx_frugal import AsyncRateLimitedCacheClient, RateLimitedCacheClient
from httpx_frugal.policy import AlwaysCachePolicy
from httpx_frugal.transport import AsyncDomainRateLimitedTransport, DomainRateLimitedTransport


def build_sync_http_client(
    wrapper: RateLimitedCacheClient,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    rates: list[Rate] | None = None,
) -> tuple[httpx.Client, SQLiteBucket]:
    """Build httpx.Client with RateLimitedCacheClient stack and a mock inner transport."""
    use_rates = rates if rates is not None else wrapper._rates
    bucket = SQLiteBucket.init_from_file(
        use_rates,
        db_path=str(wrapper._rate_limiter_db_path),
        use_file_lock=wrapper._use_file_lock,
    )
    limiter = Limiter(bucket)
    rate_transport = DomainRateLimitedTransport(
        limiter=limiter,
        inner_transport=httpx.MockTransport(handler),
        timeout_seconds=wrapper._rate_limit_timeout_seconds,
        blocking=wrapper._blocking,
    )
    cache_transport = SyncCacheTransport(
        next_transport=rate_transport,
        storage=wrapper._cache_storage(),
        policy=AlwaysCachePolicy(),
    )
    return httpx.Client(transport=cache_transport), bucket


def build_async_http_client(
    wrapper: AsyncRateLimitedCacheClient,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    rates: list[Rate] | None = None,
) -> tuple[httpx.AsyncClient, SQLiteBucket]:
    use_rates = rates if rates is not None else wrapper._rates
    bucket = SQLiteBucket.init_from_file(
        use_rates,
        db_path=str(wrapper._rate_limiter_db_path),
        use_file_lock=wrapper._use_file_lock,
    )
    limiter = Limiter(bucket)
    rate_transport = AsyncDomainRateLimitedTransport(
        limiter=limiter,
        inner_transport=httpx.MockTransport(handler),
        timeout_seconds=wrapper._rate_limit_timeout_seconds,
        blocking=wrapper._blocking,
    )
    cache_transport = AsyncCacheTransport(
        next_transport=rate_transport,
        storage=wrapper._cache_storage(),
        policy=AlwaysCachePolicy(),
    )
    return httpx.AsyncClient(transport=cache_transport), bucket
