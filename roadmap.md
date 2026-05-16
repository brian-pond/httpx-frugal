# httpx-frugal: PyPI Package Roadmap

An httpx client with persistent caching and rate limiting, designed for data pipelines that need to conserve API quota across process restarts.

---

## Bugs / Issues to Fix Before Publishing

- **`would_hit_cache` uses private hishel APIs.** `_httpx_to_internal` and `vary_headers_match` are underscore-prefixed internals. A hishel breaking release will silently break this method. Either find a stable alternative or document the fragility prominently.

- **`assert validate_rate_list` is unsafe.** `assert` statements are removed in optimized mode (`python -O`). Replace with an explicit `ValueError`.

- **`use_file_lock=False` is hardcoded.** Multi-process safety should be a constructor parameter, not a buried constant.

- **Print statements in `DomainRateLimitedTransport`.** Not appropriate for a library. Replace with `logging.getLogger(__name__)`.

- **`test_http_client` lives in the library file.** Move to `tests/`.

---

## Missing Core Features

- **Async support.** `httpx.AsyncClient`, `AsyncCacheTransport`, `AsyncSqliteStorage`. Without this the library blocks the event loop and cannot be used in FastAPI, Dagster async ops, or any async pipeline framework.

- **`blocking` mode exposed.** Currently hardcoded to `False`. Pipeline users often want to wait for a token rather than immediately raise an exception.

- **Rate limit introspection.** No way for the caller to ask "how many tokens do I have left?" Useful for pipelines that want to throttle proactively or log quota status.

- **Per-request TTL override.** hishel already supports `hishel_ttl` as a request extension. Expose this cleanly so callers can set a different TTL for specific endpoints.

- **Cache invalidation by URL.** `clear_cache()` deletes everything. Add `clear_cache_for(url)` for surgical invalidation.

---

## Storage Backends to Add

| Backend | Use case |
|---|---|
| SQLite (current) | Single-process, local pipeline |
| In-memory | Testing, short-lived scripts |
| Redis | Multi-process, multi-host (Celery workers, Kubernetes jobs) |
| Filesystem | Simple persistence without SQLite dependency |

Both hishel and pyrate-limiter already support Redis — it is mostly wiring.

---

## Nice-to-Have Features

- **Retry with backoff.** When `blocking=True` and the rate limit is hit, exponential backoff before retrying rather than immediately raising.

- **Observability hooks.** Callbacks or log events for cache hits, cache misses, rate limit waits, and rate limit errors. Useful for monitoring pipeline health.

- **Custom cache key function.** Allow the caller to override how cache keys are computed (e.g., to normalize URL query parameter ordering).

---

## Packaging Checklist

- [ ] `pyproject.toml` with proper metadata, classifiers, and optional dependency groups (`redis`, `async`)
- [ ] `README.md` with quickstart example
- [ ] `CHANGELOG.md`
- [ ] `tests/` directory with at least one integration test using a mock transport
- [ ] GitHub Actions CI (lint, test, publish to PyPI on tag)
- [ ] Minimum Python version declaration (currently uses 3.10+ union syntax `X | Y`)
- [ ] Pin or bound hishel and pyrate-limiter versions given reliance on their internals

---

## Recommended Package Name

**`httpx-frugal`**

Distinctive, searchable, and communicates the value proposition: don't waste rate limit tokens.