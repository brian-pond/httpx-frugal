"""Rate limit introspection helpers."""

from __future__ import annotations

from pyrate_limiter.buckets.sqlite_bucket import SQLiteBucket


def tokens_available_for_domain(bucket: SQLiteBucket, domain: str) -> dict[str, int]:
    """
    Return remaining request capacity per configured rate for a domain.

    Keys are ``"{limit}/{interval}s"``; values are non-negative remaining counts.
    """
    result: dict[str, int] = {}
    now = bucket.now()

    with bucket.lock:
        for rate in bucket.rates:
            label = f"{rate.limit}/{rate.interval}s"
            query = (
                f"SELECT COUNT(*) FROM '{bucket.table}' "
                "WHERE name = ? AND item_timestamp >= ? - ?"
            )
            cur = bucket.conn.execute(query, (domain, now, rate.interval))
            count = cur.fetchone()[0]
            cur.close()
            result[label] = max(0, rate.limit - count)

    return result
