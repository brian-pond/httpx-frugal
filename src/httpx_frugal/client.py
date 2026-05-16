"""
Sync client with persistent HTTP caching and per-domain rate limiting.

Transport chain::

    RateLimitedCacheClient
      └── SyncCacheTransport (hishel)     ← checked first
             └── DomainRateLimitedTransport  ← only on cache miss
                    └── HTTPTransport
"""

from __future__ import annotations

import pathlib
import sqlite3

import httpx
from hishel import SyncSqliteStorage
from hishel.httpx import SyncCacheTransport
from pyrate_limiter import Limiter, Rate, SQLiteBucket

from httpx_frugal._cache_admin import clear_cache_for_url
from httpx_frugal._cache_lookup import would_hit_cache as _would_hit_cache
from httpx_frugal._common import DEFAULT_CACHE_TTL, validate_db_paths, validate_rates
from httpx_frugal._rate_introspection import tokens_available_for_domain
from httpx_frugal.policy import AlwaysCachePolicy
from httpx_frugal.transport import DomainRateLimitedTransport


class RateLimitedCacheClient:
    """An httpx client for HTTP requests with rate limiting and caching."""

    def __init__(
        self,
        rates: list[Rate],
        cache_db_path: pathlib.Path,
        rate_limiter_db_path: pathlib.Path,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        *,
        use_file_lock: bool = False,
        blocking: bool = False,
        rate_limit_timeout_seconds: float = 10.0,
        enable_http2: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        rates:
            Rate limits applied per domain on cache misses.
        cache_db_path:
            SQLite database path for the hishel response cache.
        rate_limiter_db_path:
            SQLite database path for pyrate-limiter token storage.
        cache_ttl:
            Default cache TTL in seconds.
        use_file_lock:
            Enable SQLite file locking for multi-process rate limiter use.
        blocking:
            When True, wait for a rate-limit token instead of raising immediately.
        rate_limit_timeout_seconds:
            Max seconds to wait when ``blocking=True``.
        enable_http2:
            Use HTTP/2 on the inner transport (requires ``pip install httpx-frugal[http2]``).
        """
        self._rates = rates
        self._cache_ttl = cache_ttl
        self._use_file_lock = use_file_lock
        self._blocking = blocking
        self._rate_limit_timeout_seconds = rate_limit_timeout_seconds
        self._enable_http2 = enable_http2
        self._client: httpx.Client | None = None
        self._limiter: Limiter | None = None

        cache_path, rate_path = validate_db_paths(cache_db_path, rate_limiter_db_path)
        self._cache_db_path = cache_path
        self._rate_limiter_db_path = rate_path

    @staticmethod
    def get_default_cache_ttl() -> int:
        return DEFAULT_CACHE_TTL

    def __enter__(self) -> httpx.Client:
        self._client = self._build_client()
        return self._client

    def __exit__(self, *args: object) -> None:
        if self._client:
            self._client.close()
        self._client = None
        self._limiter = None

    def _cache_storage(self) -> SyncSqliteStorage:
        return SyncSqliteStorage(
            database_path=self._cache_db_path,
            default_ttl=self._cache_ttl,
        )

    def _rate_limiter_bucket(self) -> SQLiteBucket:
        return SQLiteBucket.init_from_file(
            self._rates,
            db_path=str(self._rate_limiter_db_path),
            use_file_lock=self._use_file_lock,
        )

    def clear_cache(self) -> None:
        """Remove all cached HTTP responses from the hishel SQLite database."""
        if not self._cache_db_path.exists():
            return
        conn = sqlite3.connect(self._cache_db_path)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("DELETE FROM entries")
            conn.commit()
        finally:
            conn.close()

    def clear_cache_for(self, url: str, *, method: str = "GET", params: dict | None = None) -> None:
        """Remove cached entries matching a specific URL (and optional query params)."""
        clear_cache_for_url(
            self._cache_db_path,
            self._cache_ttl,
            url,
            method=method,
            params=params,
        )

    def clear_rate_limiter(self) -> None:
        """Remove all rate-limit token records from the pyrate-limiter SQLite database."""
        if not self._rate_limiter_db_path.exists():
            return
        bucket = self._rate_limiter_bucket()
        try:
            bucket.flush()
        finally:
            bucket.close()

    def would_hit_cache(self, url: str, *, method: str = "GET", params: dict | None = None) -> bool:
        """Return whether the request would be served from cache without sending it."""
        storage = self._cache_storage()
        try:
            return _would_hit_cache(storage, url, method=method, params=params)
        finally:
            storage.close()

    def tokens_available(self, domain: str) -> dict[str, int]:
        """
        Return remaining request capacity per configured rate for a domain.

        Keys are human-readable rate descriptions (``"{limit}/{interval}s"``).
        Domains with no prior requests return each rate's full limit.
        """
        bucket = self._get_sqlite_bucket()
        return tokens_available_for_domain(bucket, domain)

    def _get_sqlite_bucket(self) -> SQLiteBucket:
        if self._limiter is not None:
            bucket = self._limiter.bucket
        else:
            bucket = self._rate_limiter_bucket()
        if not isinstance(bucket, SQLiteBucket):
            raise TypeError("tokens_available requires a SQLite-backed rate limiter bucket")
        return bucket

    def _build_client(self) -> httpx.Client:
        validate_rates(self._rates)

        bucket = self._rate_limiter_bucket()
        self._limiter = Limiter(bucket)

        rate_transport = DomainRateLimitedTransport(
            limiter=self._limiter,
            inner_transport=httpx.HTTPTransport(http2=self._enable_http2),
            timeout_seconds=self._rate_limit_timeout_seconds,
            blocking=self._blocking,
        )

        cache_transport = SyncCacheTransport(
            next_transport=rate_transport,
            storage=self._cache_storage(),
            policy=AlwaysCachePolicy(),
        )

        return httpx.Client(transport=cache_transport)
