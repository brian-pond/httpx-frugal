# httpx-frugal

An [httpx](https://www.python-httpx.org/) client with persistent caching ([hishel](https://hishel.com/)) and per-domain rate limiting ([pyrate-limiter](https://pyratelimiter.readthedocs.io/)), designed for data pipelines that need to conserve API quota across process restarts.

Cache is checked **before** rate limiting, so cached responses do not consume rate-limit tokens.

## Install

```bash
pip install httpx-frugal
```

Optional extras:

```bash
pip install httpx-frugal[http2]   # HTTP/2 inner transport
```

## Quickstart (sync)

```python
import pathlib

from pyrate_limiter import Duration, Rate

from httpx_frugal import RateLimitedCacheClient

rates = [Rate(5, Duration.MINUTE)]
cache_db = pathlib.Path("~/.cache/myapp/http-cache.sqlite").expanduser()
rate_db = pathlib.Path("~/.cache/myapp/rate-limiter.sqlite").expanduser()
cache_db.parent.mkdir(parents=True, exist_ok=True)
rate_db.parent.mkdir(parents=True, exist_ok=True)

client_wrapper = RateLimitedCacheClient(
    rates=rates,
    cache_db_path=cache_db,
    rate_limiter_db_path=rate_db,
)

if client_wrapper.would_hit_cache("https://api.example.com/data"):
    print("served from cache on next request")

with client_wrapper as client:
    response = client.get("https://api.example.com/data")
    print(response.extensions.get("hishel_from_cache"))
```

## Async

```python
from httpx_frugal import AsyncRateLimitedCacheClient

async with AsyncRateLimitedCacheClient(
    rates=rates,
    cache_db_path=cache_db,
    rate_limiter_db_path=rate_db,
) as client:
    response = await client.get("https://api.example.com/data")
```

## Blocking mode

Wait for a rate-limit token instead of raising immediately:

```python
client_wrapper = RateLimitedCacheClient(
    rates=rates,
    cache_db_path=cache_db,
    rate_limiter_db_path=rate_db,
    blocking=True,
    rate_limit_timeout_seconds=30.0,
)
```

## Per-request cache TTL

Override TTL for a single request via httpx extensions:

```python
with client_wrapper as client:
    client.get("https://api.example.com/short-lived", extensions={"hishel_ttl": 60})
```

Or use the helper:

```python
from httpx_frugal import request_with_ttl

with client_wrapper as client:
    req = request_with_ttl(client, "GET", "https://api.example.com/x", ttl=120)
    client.send(req)
```

## Rate limit introspection

```python
remaining = client_wrapper.tokens_available("api.example.com")
# e.g. {"5/60000s": 3}
```

## Cache invalidation

```python
client_wrapper.clear_cache()                    # all entries
client_wrapper.clear_cache_for("https://...")  # one URL
client_wrapper.clear_rate_limiter()            # reset tokens
```

## Multi-process pipelines

Enable SQLite file locking on the rate limiter bucket:

```python
RateLimitedCacheClient(..., use_file_lock=True)
```

## `would_hit_cache` caveat

`would_hit_cache()` uses hishel internal APIs and may break if hishel changes them. Prefer checking `response.extensions["hishel_from_cache"]` after requests when possible. httpx-frugal pins `hishel>=1.2,<2`.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```

## License

MIT
