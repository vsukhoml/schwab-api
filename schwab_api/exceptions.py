import functools
import logging
import random
import time
from typing import Callable, Optional, Tuple, Type, TypeVar

_F = TypeVar("_F", bound=Callable)

_logger = logging.getLogger(__name__)


class SchwabAPIError(Exception):
    """Base exception for all Schwab API errors."""

    pass


class RateLimitError(SchwabAPIError):
    """Raised when the Schwab API returns a 429 Too Many Requests status."""

    pass


class AuthError(SchwabAPIError):
    """Raised when authentication fails (401 Unauthorized or 403 Forbidden)."""

    pass


class InvalidRequestError(SchwabAPIError):
    """Raised when the request is invalid (400 Bad Request)."""

    pass


class ResourceNotFoundError(SchwabAPIError):
    """Raised when the requested resource is not found (404 Not Found)."""

    pass


class ServerError(SchwabAPIError):
    """Raised when the Schwab API returns a 5xx Server Error."""

    pass


def retry_on_transient(
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable: Optional[Tuple[Type[Exception], ...]] = None,
) -> Callable[[_F], _F]:
    """
    Decorator factory that retries a function on transient Schwab API errors.

    Uses exponential backoff (doubling each attempt, capped at ``max_delay``).
    Optional jitter adds uniform noise in ``[0, delay]`` to spread retries
    across concurrent callers (avoids thundering herd).

    By default retries on :class:`ServerError` (5xx) and
    :class:`RateLimitError` (429). Auth, bad-request, and not-found errors
    are permanent and are never retried.

    Args:
        max_attempts: Total attempts including the first call (``1`` = no retry).
        base_delay: Sleep duration in seconds before the first retry.
        max_delay: Maximum sleep duration in seconds.
        jitter: If True, adds ``uniform(0, delay)`` noise to each sleep.
        retryable: Tuple of exception types to catch and retry.
            Defaults to ``(ServerError, RateLimitError)``.

    Example::

        from schwab_api.exceptions import retry_on_transient

        @retry_on_transient(max_attempts=4, base_delay=2.0)
        def place_trade():
            return client.place_order(account_hash, order)

    """
    _retryable: Tuple[Type[Exception], ...] = (
        retryable if retryable is not None else (ServerError, RateLimitError)
    )

    def decorator(func: _F) -> _F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exc: Optional[Exception] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except _retryable as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break

                    sleep = min(delay, max_delay)
                    if jitter:
                        sleep += random.uniform(0.0, sleep)

                    _logger.warning(
                        "%s attempt %d/%d failed: %s. Retrying in %.2fs",
                        func.__qualname__,
                        attempt,
                        max_attempts,
                        exc,
                        sleep,
                    )
                    time.sleep(sleep)
                    delay = min(delay * 2.0, max_delay)

            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
