"""Exceptions raised by httpx-frugal."""


class HTTPRateLimitError(Exception):
    """Raised when the rate limit is exceeded and no token could be acquired."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
