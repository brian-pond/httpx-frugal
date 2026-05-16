"""Caching policies."""

from dataclasses import dataclass, field

from hishel import FilterPolicy


@dataclass
class AlwaysCachePolicy(FilterPolicy):
    """Cache all responses using storage TTL; ignore RFC 9111 freshness headers."""

    request_filters: list = field(default_factory=list)
    response_filters: list = field(default_factory=list)
