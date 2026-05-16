"""
Cache lookup helpers.

.. warning::

   ``would_hit_cache`` uses hishel private APIs (``_httpx_to_internal``,
   ``vary_headers_match``). These may break on hishel minor releases.
   httpx-frugal pins ``hishel>=1.2,<2`` accordingly. Prefer checking
   ``response.extensions["hishel_from_cache"]`` after a request when possible.
"""

from __future__ import annotations

import httpx
from hishel import SyncSqliteStorage
from hishel._core._spec import vary_headers_match  # noqa: PLC2701
from hishel._sync_httpx import _httpx_to_internal  # noqa: PLC2701

from httpx_frugal._common import cache_key_for_url


def would_hit_cache(
    storage: SyncSqliteStorage,
    url: str,
    *,
    method: str = "GET",
    params: dict | None = None,
) -> bool:
    """
    Return whether a request would be served from cache for the given storage.

    Mirrors hishel's internal lookup used during transport handling.
    """
    if params is None:
        params = {}

    with httpx.Client() as httpx_client:
        httpx_request = httpx_client.build_request(method, url=url, params=params)
        hishel_request = _httpx_to_internal(httpx_request)

    cache_key = cache_key_for_url(str(hishel_request.url))
    entries = storage.get_entries(cache_key)
    for entry in entries:
        if (
            str(entry.request.url) == str(hishel_request.url)
            and entry.request.method == hishel_request.method
            and vary_headers_match(hishel_request, entry)
        ):
            return True
    return False
