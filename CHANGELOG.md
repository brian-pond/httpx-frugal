# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-05-16

### Added

- `AsyncRateLimitedCacheClient` for async httpx pipelines (FastAPI, Dagster, etc.)
- `blocking` and `rate_limit_timeout_seconds` on sync and async clients
- `use_file_lock` for multi-process rate limiter safety
- `tokens_available(domain)` for rate-limit introspection
- `clear_cache_for(url)` for surgical cache invalidation
- `request_with_ttl()` helper and per-request `hishel_ttl` extension support
- `enable_http2` flag (default `False`; opt in with `httpx-frugal[http2]`)

### Fixed

- Path validation used wrong variable when cache parent directory was missing
- `validate_rate_list` now raises `ValueError` instead of `assert` (safe under `python -O`)
- Rate limiting rejects URLs without a host

### Changed

- HTTP/2 disabled by default to avoid requiring `httpx[http2]` on install
- `hishel[async]` included in core dependencies for async SQLite storage

## [0.1.0] - 2026-05-16

### Added

- Initial release: `RateLimitedCacheClient` with SQLite cache and rate limiting
- `would_hit_cache()`, `clear_cache()`, `clear_rate_limiter()`
- `DomainRateLimitedTransport` and `AlwaysCachePolicy`
