"""Shared pytest fixtures."""

from __future__ import annotations

import pathlib

import pytest
from pyrate_limiter import Duration, Rate


@pytest.fixture
def rates() -> list[Rate]:
    return [Rate(5, Duration.SECOND)]


@pytest.fixture
def db_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def cache_db_path(db_dir: pathlib.Path) -> pathlib.Path:
    return db_dir / "http-cache.sqlite"


@pytest.fixture
def rate_db_path(db_dir: pathlib.Path) -> pathlib.Path:
    return db_dir / "rate-limiter.sqlite"
