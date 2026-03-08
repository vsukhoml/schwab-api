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
