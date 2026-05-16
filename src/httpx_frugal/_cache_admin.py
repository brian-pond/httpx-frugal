"""Cache administration helpers shared by sync and async clients."""

from __future__ import annotations

import pathlib

import httpx
from hishel import SyncSqliteStorage

from httpx_frugal._common import cache_key_for_url


def clear_cache_for_url(
    cache_db_path: pathlib.Path,
    cache_ttl: int,
    url: str,
    *,
    method: str = "GET",
    params: dict | None = None,
) -> None:
    """Remove cached entries matching a specific URL from the hishel SQLite database."""
    if params is None:
        params = {}

    if not cache_db_path.exists():
        return

    with httpx.Client() as httpx_client:
        httpx_request = httpx_client.build_request(method, url=url, params=params)
        target_url = str(httpx_request.url)
        target_method = httpx_request.method

    cache_key = cache_key_for_url(target_url)
    storage = SyncSqliteStorage(database_path=cache_db_path, default_ttl=cache_ttl)
    try:
        entries = storage.get_entries(cache_key)
        for entry in entries:
            if str(entry.request.url) == target_url and entry.request.method == target_method:
                storage.remove_entry(entry.id)
    finally:
        storage.close()
