from . import orders, utils
from .account_manager import AccountManager
from .client import Client
from .exceptions import (
    AuthError,
    InvalidRequestError,
    RateLimitError,
    ResourceNotFoundError,
    SchwabAPIError,
    ServerError,
    retry_on_transient,
)
from .math import BlackScholesPricer, calculate_gamma_exposure, calculate_vix_like_index
from .stream import StreamClient, StreamClientAsync
from .stream_parsers import (
    StreamResponseHandler,
    get_numeric_fields,
    parse_numeric_fields,
)
from .trading import OptionChainAnalyzer, PositionAnalyzer

__version__ = "0.1.0"
__all__ = [
    "AccountManager",
    "Client",
    "SchwabAPIError",
    "RateLimitError",
    "AuthError",
    "InvalidRequestError",
    "ResourceNotFoundError",
    "ServerError",
    "StreamClient",
    "StreamClientAsync",
    "StreamResponseHandler",
    "retry_on_transient",
    "parse_numeric_fields",
    "get_numeric_fields",
    "OptionChainAnalyzer",
    "PositionAnalyzer",
    "BlackScholesPricer",
    "calculate_gamma_exposure",
    "calculate_vix_like_index",
    "orders",
    "utils",
]
