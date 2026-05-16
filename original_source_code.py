 """ http_client.py """

import hashlib
import sqlite3
from dataclasses import dataclass, field
import pathlib

# Third Party Libraries
from hishel import FilterPolicy, SyncSqliteStorage
from hishel.httpx import SyncCacheTransport
from hishel._core._spec import vary_headers_match
from hishel._sync_httpx import _httpx_to_internal

import httpx
from pyrate_limiter import Limiter, Rate, SQLiteBucket, validate_rate_list

# ------------------------------------------------------------
# Composable Transports
# https://www.python-httpx.org/advanced/transports/#custom-transports
#
# RateLimitedCacheClient
#   └── CacheTransport (hishel)         ← checked first
#          └── RateLimitedTransport      ← only called on cache miss
#                 └── HTTPTransport(http2=True)
#
# ------------------------------------------------------------


@dataclass
class AlwaysCachePolicy(FilterPolicy):
    """Cache all responses using storage TTL; ignore RFC 9111 freshness headers."""

    request_filters: list = field(default_factory=list)
    response_filters: list = field(default_factory=list)


class HTTPRateLimitError(Exception):
    """
    Exception raised when the rate limit is exceeded.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)  


class DomainRateLimitedTransport(httpx.BaseTransport):
    def __init__(
        
        self, 
        limiter: Limiter,
        inner_transport: httpx.BaseTransport,
        timeout_seconds: float = 10.0,
        blocking: bool = False,
    ):
        """
        Initialize the transport.

        Parameters
        ----------
        limiter : :class:`~pyrate_limiter.Limiter`
            Limiter used to control request rate.
        inner_transport : :class:`httpx.BaseTransport`
            Inner transport to use for the request.
        timeout_seconds : float
            Timeout in seconds for acquiring a token.
        blocking : bool
            Whether to block the request until the token is acquired.
        """
        self.limiter = limiter
        self.inner_transport = inner_transport
        self.timeout: float = timeout_seconds if blocking else -1  # cannot have a timeout value if not blocking
        self.blocking: bool = blocking
    
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        # Extract domain as the rate limit identity
        domain_name: str = request.url.host  # example: "datahenge.com" or "brianpond.com"

        # Acquire token with explicit timeout
        success = self.limiter.try_acquire(
            name=domain_name,
            blocking=self.blocking,
            timeout=self.timeout
        )

        if not success:
            raise HTTPRateLimitError(
                f"Rate limit exceeded for domain name = {domain_name}, "
                f"could not acquire token within {self.timeout}s"
            )

        # Proceed with actual HTTP request
        return self.inner_transport.handle_request(request)


class RateLimitedCacheClient:
    """
    An httpx client for making HTTP requests with rate limiting and caching.
    """

    @staticmethod
    def get_default_cache_ttl() -> int:
        return 300  # 5 minutes

    def __init__(self, 
                 rates: list[Rate],
                 cache_db_path: pathlib.Path,
                 rate_limiter_db_path: pathlib.Path,
                 cache_ttl: int = get_default_cache_ttl()):
        """
        Parameters
        ----------
        rates : list[Rate]
            The rates to use for rate limiting.
        cache_db_path : pathlib.Path
            The path to the SQLite database to use for caching.
        rate_limiter_db_path : pathlib.Path
            The path to the SQLite database to use for rate limiting.
        cache_ttl : int
            The TTL for the cache in seconds.
        """
        self._rates = rates
        self._cache_ttl = cache_ttl
        self._client: httpx.Client | None = None
        self.__init_paths(cache_db_path, rate_limiter_db_path)

    def __init_paths(self, cache_db_path: pathlib.Path, rate_limiter_db_path: pathlib.Path):
        # Cache database path
        if not cache_db_path.parent.exists():
            raise FileNotFoundError(f"Cache database directory does not exist: {self._cache_db_path.parent}")
        if cache_db_path.exists() and not cache_db_path.is_file():
            raise FileExistsError(f"Cache database is not a file: {cache_db_path}")
        self._cache_db_path = cache_db_path

        # Rate limiter database path
        if not rate_limiter_db_path.parent.exists():
            raise FileNotFoundError(f"Rate limiter database directory does not exist: {rate_limiter_db_path.parent}")
        if rate_limiter_db_path.exists() and not rate_limiter_db_path.is_file():
            raise FileExistsError(f"Rate limiter database is not a file: {rate_limiter_db_path}")
        self._rate_limiter_db_path = rate_limiter_db_path

    def __enter__(self) -> httpx.Client:  # returns the real httpx.Client
        self._client = self._build_client()
        return self._client  # caller gets full httpx.Client

    def __exit__(self, *args):
        if self._client:
            self._client.close()
        self._client = None

    def _cache_storage(self) -> SyncSqliteStorage:
        return SyncSqliteStorage(
            database_path=self._cache_db_path,
            default_ttl=self._cache_ttl,
        )

    def _rate_limiter_bucket(self) -> SQLiteBucket:
        # NOTE: db_path must be set explicitly; otherwise the bucket uses a temp file
        # deleted when the process exits. Set use_file_lock=True for multi-process use.
        return SQLiteBucket.init_from_file(
            self._rates,
            db_path=str(self._rate_limiter_db_path),
            use_file_lock=False,
        )

    @staticmethod
    def _cache_key_for_url(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

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
        """
        Return whether FilterPolicy would serve this request from cache.

        Mirrors the lookup in hishel's ``_handle_request_with_filters`` using
        the same storage path and TTL as :meth:`_build_client`.
        """
        if params is None:
            params = {}

        with httpx.Client() as httpx_client:
            httpx_request = httpx_client.build_request(method, url=url, params=params)
            hishel_request = _httpx_to_internal(httpx_request)

        storage = self._cache_storage()
        try:
            cache_key = self._cache_key_for_url(str(hishel_request.url))
            entries = storage.get_entries(cache_key)
            for entry in entries:
                if (
                    str(entry.request.url) == str(hishel_request.url)
                    and entry.request.method == hishel_request.method
                    and vary_headers_match(hishel_request, entry)
                ):
                    return True
            return False
        finally:
            storage.close()

    def _build_client(self) -> httpx.Client:
        """
        Build the transport chain
        """
        # Part One: Rate limiting

        # NOTE: Rates must be properly ordered:
        #   Rates' intervals & limits must be ordered from least to greatest
        #   Rates' ratio of limit/interval must be ordered from greatest to least
        #   Buckets validate rates during initialization. If using a custom implementation, use the built-in validator:
        assert validate_rate_list(self._rates)

        bucket = self._rate_limiter_bucket()
        rate_limiter = Limiter(bucket)  # rate limit layer (only invoked on cache miss)

        # NOTE: prerequisites for http2=True = install httpx with the http2 extra: `pip install httpx[http2]`
        rate_transport = DomainRateLimitedTransport(limiter=rate_limiter,
                                                    inner_transport=httpx.HTTPTransport(http2=True)
        )

        # ----------------
        # Part Two: Cache Setup
        # ----------------

        cache_transport = SyncCacheTransport(
            next_transport=rate_transport,
            storage=self._cache_storage(),
            policy=AlwaysCachePolicy(),
        )

        # NOTE: Storage also respects the `hishel_ttl` request metadata, useful to set a custom TTL for a specific request.
        return httpx.Client(transport=cache_transport)


def test_http_client():
    """
    Get a recipe from the DummyJSON API.

    If you change the recipe number:
        1. The cache might be missed, depending on the default TTL.
        2. If you rapidly make multiple requests, each with a different recipe number, you might exceed the rate limit.
    """
    import sys
    from pyrate_limiter import Duration, Rate

    recipe_number = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    recipe_url = f"https://dummyjson.com/recipes/{recipe_number}"
    print(f"Recipe URL: {recipe_url}")

    minute_rate = Rate(5, Duration.MINUTE) # 5 requests per minute
    hourly_rate = Rate(15, Duration.HOUR) # 15 requests per hour
    days_rate = Rate(100, Duration.DAY * 2) # 100 requests per 2 days
    my_rates = [minute_rate, hourly_rate, days_rate]

    my_cache_database = pathlib.Path.home() / ".cache/cascadia-watch/http-cache.sqlite"
    my_rate_limiter_database = pathlib.Path.home() / ".cache/cascadia-watch/rate-limiter.sqlite"

    cache_client = RateLimitedCacheClient(
        rates=my_rates,
        cache_db_path=my_cache_database,
        rate_limiter_db_path=my_rate_limiter_database,
    )
    print(f"\nWould hit cache (before request) = {cache_client.would_hit_cache(recipe_url)}")

    with cache_client as http_client:
        response = http_client.get(recipe_url)
        print(f"Response was from cache = {response.extensions['hishel_from_cache']}")
        print(f"Response status code = {response.status_code}")
        # print(f"Response headers = {response.headers}")
        print(f"ResponseCache-Control: {response.headers.get('cache-control', 'not set')}")
        print(f"Response content = {response.text}")


if __name__ == "__main__":
    test_http_client()

