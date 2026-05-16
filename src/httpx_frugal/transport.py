"""HTTPX transports with per-domain rate limiting."""

import logging

import httpx
from pyrate_limiter import Limiter

from httpx_frugal.exceptions import HTTPRateLimitError

logger = logging.getLogger(__name__)


class DomainRateLimitedTransport(httpx.BaseTransport):
    """Rate-limit requests by URL host before delegating to an inner transport."""

    def __init__(
        self,
        limiter: Limiter,
        inner_transport: httpx.BaseTransport,
        timeout_seconds: float = 10.0,
        blocking: bool = False,
    ) -> None:
        self.limiter = limiter
        self.inner_transport = inner_transport
        self.timeout: float = timeout_seconds if blocking else -1
        self.blocking = blocking

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        domain_name = request.url.host
        if not domain_name:
            raise HTTPRateLimitError("Request URL has no host for rate limiting")

        success = self.limiter.try_acquire(
            name=domain_name,
            blocking=self.blocking,
            timeout=self.timeout,
        )

        if not success:
            raise HTTPRateLimitError(
                f"Rate limit exceeded for domain name = {domain_name}, "
                f"could not acquire token within {self.timeout}s"
            )

        logger.debug("Rate limit token acquired for domain %s", domain_name)
        return self.inner_transport.handle_request(request)


class AsyncDomainRateLimitedTransport(httpx.AsyncBaseTransport):
    """Async rate-limit transport keyed by URL host."""

    def __init__(
        self,
        limiter: Limiter,
        inner_transport: httpx.AsyncBaseTransport,
        timeout_seconds: float = 10.0,
        blocking: bool = False,
    ) -> None:
        self.limiter = limiter
        self.inner_transport = inner_transport
        self.timeout: float = timeout_seconds if blocking else -1
        self.blocking = blocking

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        domain_name = request.url.host
        if not domain_name:
            raise HTTPRateLimitError("Request URL has no host for rate limiting")

        success = self.limiter.try_acquire(
            name=domain_name,
            blocking=self.blocking,
            timeout=self.timeout,
        )

        if not success:
            raise HTTPRateLimitError(
                f"Rate limit exceeded for domain name = {domain_name}, "
                f"could not acquire token within {self.timeout}s"
            )

        logger.debug("Rate limit token acquired for domain %s", domain_name)
        return await self.inner_transport.handle_async_request(request)
