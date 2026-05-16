"""httpx-frugal: persistent HTTP caching and per-domain rate limiting for httpx."""

from httpx_frugal.async_client import AsyncRateLimitedCacheClient
from httpx_frugal.client import RateLimitedCacheClient
from httpx_frugal.exceptions import HTTPRateLimitError
from httpx_frugal.ttl import request_with_ttl

__version__ = "0.2.0"

__all__ = [
    "AsyncRateLimitedCacheClient",
    "HTTPRateLimitError",
    "RateLimitedCacheClient",
    "__version__",
    "request_with_ttl",
]
