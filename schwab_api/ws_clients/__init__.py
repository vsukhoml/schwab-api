from abc import ABC, abstractmethod
from typing import Optional


class BaseWSClient(ABC):
    """Abstract base class for WebSocket clients."""

    @abstractmethod
    async def connect(self, url: str, ping_timeout: int) -> None:
        """Establish the WebSocket connection."""
        pass

    @abstractmethod
    async def send(self, payload: str) -> None:
        """Send a string payload."""
        pass

    @abstractmethod
    async def recv(self) -> str:
        """Receive a string payload."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the WebSocket connection."""
        pass

    @abstractmethod
    def get_disconnect_exceptions(self) -> tuple:
        """Return a tuple of exceptions that indicate a normal/expected disconnect."""
        pass

    @abstractmethod
    def get_error_exceptions(self) -> tuple:
        """Return a tuple of exceptions that indicate a forced/unexpected disconnect."""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class WebsocketsClient(BaseWSClient):
    """Implementation using the standard 'websockets' library."""

    def __init__(self):
        import websockets
        import websockets.exceptions

        self.websockets = websockets
        self.ws = None

    async def connect(self, url: str, ping_timeout: int) -> None:
        self.ws = await self.websockets.connect(url, ping_timeout=ping_timeout)

    async def send(self, payload: str) -> None:
        if self.ws:
            await self.ws.send(payload)

    async def recv(self) -> str:
        if self.ws:
            return await self.ws.recv()
        raise ConnectionError("WebSocket is not connected")

    async def close(self) -> None:
        if self.ws:
            await self.ws.close()
            self.ws = None

    def get_disconnect_exceptions(self) -> tuple:
        return (
            self.websockets.exceptions.ConnectionClosedOK,
            self.websockets.exceptions.ConnectionClosed,
        )

    def get_error_exceptions(self) -> tuple:
        return (self.websockets.exceptions.ConnectionClosedError,)


class CurlCffiWSClient(BaseWSClient):
    """Implementation using 'curl_cffi' AsyncWebSocket."""

    def __init__(self):
        from curl_cffi.curl import CurlError
        from curl_cffi.requests import AsyncSession
        from curl_cffi.requests.websockets import WebSocketClosed

        self.AsyncSession = AsyncSession
        self.CurlError = CurlError
        self.WebSocketClosed = WebSocketClosed
        self.session: Optional[AsyncSession] = None
        self.ws = None

    async def connect(self, url: str, ping_timeout: int) -> None:
        self.session = self.AsyncSession(impersonate="chrome")
        self.ws = await self.session.ws_connect(url)

    async def send(self, payload: str) -> None:
        if self.ws:
            await self.ws.send_str(payload)

    async def recv(self) -> str:
        if self.ws:
            # curl_cffi recv_str returns a tuple (bytes, frame_type) or string depending on version,
            # but usually send_str/recv_str are symmetric wrappers.
            res = await self.ws.recv_str()
            # Handle potential tuple returns based on varying curl_cffi implementations
            if isinstance(res, tuple):
                return (
                    res[0].decode("utf-8") if isinstance(res[0], bytes) else str(res[0])
                )
            return res
        raise ConnectionError("WebSocket is not connected")

    async def close(self) -> None:
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        if self.session:
            try:
                await self.session.close()
            except TypeError as e:
                if "cdata pointer" not in str(e):
                    raise
            except Exception:
                pass
            self.session = None

    def get_disconnect_exceptions(self) -> tuple:
        return (self.WebSocketClosed,)

    def get_error_exceptions(self) -> tuple:
        return (self.CurlError, ConnectionError, OSError)


def get_ws_client() -> BaseWSClient:
    """Factory to get the best available WebSocket client."""
    try:
        import curl_cffi  # noqa: F401

        return CurlCffiWSClient()
    except ImportError:
        return WebsocketsClient()
