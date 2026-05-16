"""Per-request cache TTL helpers."""

from __future__ import annotations

import httpx


def request_with_ttl(
    client: httpx.Client | httpx.AsyncClient,
    method: str,
    url: str,
    *,
    ttl: int,
    **kwargs: object,
) -> httpx.Request:
    """
    Build a request with a custom hishel cache TTL (seconds).

    Pass the returned request to ``client.send(request)`` or use as
    ``extensions={"hishel_ttl": ttl}`` on convenience methods::

        client.get(url, extensions={"hishel_ttl": 60})
    """
    request = client.build_request(method, url, **kwargs)
    request.extensions["hishel_ttl"] = ttl
    return request
