"""Shared helpers for sync and async clients."""

from __future__ import annotations

import hashlib
import pathlib

from pyrate_limiter import Rate, validate_rate_list

DEFAULT_CACHE_TTL = 300


def validate_rates(rates: list[Rate]) -> None:
    """Validate rate limit configuration, raising ValueError if invalid."""
    if not validate_rate_list(rates):
        raise ValueError(
            "Invalid rate list: intervals and limits must be ordered from least to "
            "greatest, and limit/interval ratios from greatest to least"
        )


def validate_db_paths(
    cache_db_path: pathlib.Path,
    rate_limiter_db_path: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Validate SQLite database paths and return normalized paths."""
    if not cache_db_path.parent.exists():
        raise FileNotFoundError(
            f"Cache database directory does not exist: {cache_db_path.parent}"
        )
    if cache_db_path.exists() and not cache_db_path.is_file():
        raise FileExistsError(f"Cache database is not a file: {cache_db_path}")

    if not rate_limiter_db_path.parent.exists():
        raise FileNotFoundError(
            f"Rate limiter database directory does not exist: {rate_limiter_db_path.parent}"
        )
    if rate_limiter_db_path.exists() and not rate_limiter_db_path.is_file():
        raise FileExistsError(f"Rate limiter database is not a file: {rate_limiter_db_path}")

    return cache_db_path, rate_limiter_db_path


def cache_key_for_url(url: str) -> str:
    """Return the hishel cache key for a URL string."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()
