import asyncio
import datetime
import json
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Union, cast

from .stream_parsers import get_numeric_fields
from .utils import format_list
from .ws_clients import get_ws_client

logger = logging.getLogger(__name__)


class StreamBase:
    def __init__(
        self,
        client: Any,
        logger: Optional[logging.Logger] = None,
        streamer_info: Optional[Dict[str, Any]] = None,
    ):
        self._client = client
        self._tokens = client.tokens
        self._logger: logging.Logger = cast(
            logging.Logger,
            logger or getattr(client, "logger", logging.getLogger(__name__)),
        )

        self._ws_client = get_ws_client()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._loop_ready = threading.Event()
        self._should_stop = True
        self._backoff_time = 2.0

        self._streamer_info: Optional[Dict[str, Any]] = streamer_info
        self._request_id = 0

        self.active = False
        self.subscriptions: Dict[str, Dict[str, Any]] = {}

    def _get_streamer_info(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves streaming configuration from the user preferences endpoint.
        This includes the WebSocket URL, Customer ID, and Correlation ID required for authentication.
        """
        try:
            if hasattr(self._client, "user_preferences"):
                prefs = self._client.user_preferences().json()
            else:
                prefs = self._client._request("GET", "/trader/v1/userPreference").json()

            if isinstance(prefs, list):
                streamer_info = prefs[0].get("streamerInfo", [{}])[0]
            else:
                streamer_info = prefs.get("streamerInfo", [{}])[0]

            if not streamer_info:
                raise Exception("No streamerInfo found in user preferences")
            return streamer_info
        except Exception as e:
            self._logger.error(f"Failed to get streamer info: {e}")
            return None

    async def _run_streamer(
        self, receiver_func: Callable, ping_timeout: int = 30, **kwargs: Any
    ) -> None:
        self._event_loop = asyncio.get_running_loop()
        is_async_receiver = (
            True if asyncio.iscoroutinefunction(receiver_func) else False
        )

        async def call_receiver(response, **kwargs):
            try:
                if isinstance(response, str):
                    response = json.loads(response)
                if is_async_receiver:
                    await receiver_func(response, **kwargs)
                else:
                    receiver_func(response, **kwargs)
            except Exception as e:
                self._logger.error(f"Error in stream receiver: {e}")

        self._should_stop = False
        while not self._should_stop:
            try:
                self._streamer_info = self._get_streamer_info()
            except Exception as e:
                self._logger.error("Error getting streamer info, cannot start stream.")
                self._logger.error(e)
                return

            if self._streamer_info is None:
                self._logger.warning(
                    f"Streamer info unavailable, retrying in {self._backoff_time}s..."
                )
                await self._wait_for_backoff()
                continue

            start_time = datetime.datetime.now(datetime.timezone.utc)
            try:
                self._logger.debug("Connecting to streaming server...")
                url = self._streamer_info.get("streamerSocketUrl")
                if not url:
                    raise ValueError("No stream URL available")

                async with self._ws_client as ws:
                    await ws.connect(url, ping_timeout=ping_timeout)
                    self._logger.debug("Connected to streaming server.")

                    login_payload = self.basic_request(
                        service="ADMIN",
                        command="LOGIN",
                        parameters={
                            "Authorization": self._tokens.access_token,
                            "SchwabClientChannel": self._streamer_info.get(
                                "schwabClientChannel"
                            ),
                            "SchwabClientFunctionId": self._streamer_info.get(
                                "schwabClientFunctionId"
                            ),
                        },
                    )
                    await ws.send(json.dumps(login_payload))
                    self._loop_ready.set()

                    await call_receiver(await ws.recv(), **kwargs)
                    self.active = True

                    # State Recovery: If the connection was lost and restored, we replay
                    # all previous subscriptions from the self.subscriptions dictionary
                    # to ensure the stream resumes exactly where it left off.
                    for service, subs in self.subscriptions.items():
                        grouped: dict[str, list[str]] = {}
                        for key, fields in subs.items():
                            fmt_fields = str(format_list(fields))
                            grouped.setdefault(fmt_fields, []).append(key)
                        reqs = []
                        for fields, keys in grouped.items():
                            reqs.append(
                                self.basic_request(
                                    service=service,
                                    command="ADD",
                                    parameters={
                                        "keys": format_list(keys),
                                        "fields": fields,
                                    },
                                )
                            )
                        if reqs:
                            self._logger.debug(f"Sending subscriptions: {reqs}")
                            await ws.send(json.dumps({"requests": reqs}))
                            await call_receiver(await ws.recv(), **kwargs)

                    self._backoff_time = 2.0

                    while self.active and not self._should_stop:
                        await call_receiver(await ws.recv(), **kwargs)

            except Exception as e:
                # Check custom unified exception lists
                if isinstance(e, self._ws_client.get_disconnect_exceptions()):
                    self._logger.info(f"Stream connection closed cleanly. ({e})")
                    break
                elif isinstance(e, self._ws_client.get_error_exceptions()):
                    elapsed = (
                        datetime.datetime.now(datetime.timezone.utc) - start_time
                    ).total_seconds()
                    if elapsed <= 90:
                        self._logger.warning(
                            f"Stream has crashed within 90 seconds, likely no subscriptions, invalid login, or lost connection. Not restarting. {e}"
                        )
                        break
                    else:
                        self._logger.error(
                            f"Stream connection Error. Reconnecting in {self._backoff_time} seconds..."
                        )
                        await self._wait_for_backoff()
                else:
                    self._logger.error(e)
                    self._logger.warning(
                        "Stream connection lost to server, reconnecting..."
                    )
                    await self._wait_for_backoff()
            finally:
                self.active = False

    async def _wait_for_backoff(self):
        await asyncio.sleep(self._backoff_time)
        self._backoff_time = min(self._backoff_time * 2, 120)

    def _record_request(self, request: Dict[str, Any]) -> None:
        try:

            def str_to_list(st):
                return st.split(",") if isinstance(st, str) else st

            service = request.get("service", None)
            command = request.get("command", None)
            parameters = request.get("parameters", None)
            if parameters is not None and service is not None:
                keys = str_to_list(parameters.get("keys", []))
                fields = str_to_list(parameters.get("fields", []))

                if service not in self.subscriptions:
                    self.subscriptions[service] = {}

                if command == "ADD":
                    for key in keys:
                        if key not in self.subscriptions[service]:
                            self.subscriptions[service][key] = fields
                        else:
                            self.subscriptions[service][key] = list(
                                set(fields) | set(self.subscriptions[service][key])
                            )
                elif command == "SUBS":
                    self.subscriptions[service] = {}
                    for key in keys:
                        self.subscriptions[service][key] = fields
                elif command == "UNSUBS":
                    for key in keys:
                        if key in self.subscriptions[service]:
                            del self.subscriptions[service][key]
                elif command == "VIEW":
                    for key in self.subscriptions[service].keys():
                        self.subscriptions[service][key] = fields
        except Exception as e:
            self._logger.error(e)
            self._logger.error("Error recording request - subscription not saved.")

    def basic_request(
        self, service: str, command: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if self._streamer_info is None:
            self._streamer_info = self._get_streamer_info()

        if self._streamer_info is None:
            raise ConnectionError("Streamer info unavailable")

        if parameters is not None:
            for key in list(parameters.keys()):
                if parameters[key] is None:
                    del parameters[key]

        self._request_id += 1
        request = {
            "service": service.upper(),
            "command": command.upper(),
            "requestid": self._request_id,
            "SchwabClientCustomerId": self._streamer_info.get("schwabClientCustomerId"),
            "SchwabClientCorrelId": self._streamer_info.get("schwabClientCorrelId"),
        }
        if parameters is not None and len(parameters) > 0:
            request["parameters"] = parameters
        return request

    # Built-in request builders for convenience
    def level_one_equities(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Level One Equities data.

        **Nuance:** The Schwab Streamer uses numeric string keys (e.g., "1") in
        responses. These mappings are typically hardcoded in the API spec.
        Example numeric fields for Equities:
        - "1": Bid Price
        - "2": Ask Price
        - "3": Last Price
        - "4": Bid Size
        - "5": Ask Size
        - "8": Total Volume

        :param keys: Symbol(s) to subscribe to (e.g. 'GOOG' or ['GOOG', 'AAPL']).
        :param fields: Numeric fields to request (e.g. '0,1,2,3,4,5,8' or [0, 1, 2, 3, 4, 5, 8]).
        :param command: Command type (e.g., 'ADD', 'SUBS', 'UNSUBS', 'VIEW'). Defaults to 'ADD'.
        """
        return self.basic_request(
            "LEVELONE_EQUITIES",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("LEVELONE_EQUITIES", fields),
            },
        )

    def level_one_options(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Level One Options data.

        The streaming response will contain a 'data' array with service 'LEVELONE_OPTIONS'.
        Inside 'content', each item will have a 'key' (the option symbol) and numeric fields.
        Example numeric fields for Options:
        - "1": Description (e.g. 'GOOG 04/11/2025 160.00 C')
        - "2": Bid Price
        - "3": Ask Price
        - "4": Last Price
        - "8": Total Volume
        - "9": Open Interest

        :param keys: Option symbol(s) (e.g. 'GOOG  250411C00160000').
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "LEVELONE_OPTIONS",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("LEVELONE_OPTIONS", fields),
            },
        )

    def level_one_futures(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Level One Futures data.

        **Schwab-standard Futures Symbol format:**
        '/' + 'root symbol' + 'month code' + 'year code'
        - Month codes: F(Jan), G(Feb), H(Mar), J(Apr), K(May), M(Jun), N(Jul), Q(Aug), U(Sep), V(Oct), X(Nov), Z(Dec)
        - Year code: Last two digits of the year (e.g. '25')
        - Example: '/ESH25'

        **Common Symbol Mappings (Index vs. Futures):**
        - **S&P 500**: Index `$SPX`, Futures `/ES`
        - **Nasdaq 100**: Index `$NDX`, Futures `/NQ`
        - **Dow Jones**: Index `$DJI`, Futures `/YM`
        - **Russell 2000**: Index `$RUT`, Futures `/RTY`
        - **Gold**: Index `$XAU`, Futures `/GC`
        - **Oil**: Index `$XOI`, Futures `/CL` or `/BZ` (Schwab specific: `/XOI`)
        - **Aluminum**: Index `$XAL`, Futures `/XAL`
        - **DJ Transportation**: Index `$TRAN`
        - **Other Indices**: `$COMPX`, `$VIX`, `$SOX`, `$OEX`, `$MID`, `$NYA`, `XAX`
        - **Other Futures**: `/SI` (Silver), `/HG` (Copper), `/NG` (Natural Gas), `/ZB` (30Y Bond), `/ZN` (10Y Note), `/ZW` (Wheat), `/ZC` (Corn)

        :param keys: Future symbol(s).
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "LEVELONE_FUTURES",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("LEVELONE_FUTURES", fields),
            },
        )

    def level_one_futures_options(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Level One Futures Options data.

        **Schwab-standard Futures Options Symbol format:**
        '.' + '/' + 'root symbol' + 'month code' + 'year code' + 'Call/Put code' + 'Strike Price'
        - Example: './OZCZ23C565'

        :param keys: Future Option symbol(s).
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "LEVELONE_FUTURES_OPTIONS",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("LEVELONE_FUTURES_OPTIONS", fields),
            },
        )

    def level_one_forex(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Level One Forex data.

        :param keys: Forex pair(s) (e.g., 'EUR/USD').
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "LEVELONE_FOREX",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("LEVELONE_FOREX", fields),
            },
        )

    def nyse_book(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to NYSE Order Book (Level 2) data.

        The streaming response will contain a 'data' array with service 'NYSE_BOOK'.
        Inside 'content', each item represents the order book state.
        Example fields:
        - "1": Timestamp (e.g. 1743000500375)
        - "2": Bids array. Each bid is an object with "0" (Price), "1" (Size), "2" (Number of orders), and "3" (List of exchange breakdown).
        - "3": Asks array. Similar structure to Bids.

        :param keys: Symbol(s) to subscribe to.
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "NYSE_BOOK",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("NYSE_BOOK", fields),
            },
        )

    def nasdaq_book(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to NASDAQ Order Book (Level 2) data.
        Follows the same response structure as NYSE_BOOK.

        :param keys: Symbol(s) to subscribe to.
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "NASDAQ_BOOK",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("NASDAQ_BOOK", fields),
            },
        )

    def options_book(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Options Order Book (Level 2) data.
        Follows a similar response structure as equities order book.

        :param keys: Option symbol(s) to subscribe to.
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "OPTIONS_BOOK",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("OPTIONS_BOOK", fields),
            },
        )

    def chart_equity(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Chart Equity data.

        The streaming response will contain a 'data' array with service 'CHART_EQUITY'.
        Inside 'content', each item will represent a chart candle with numeric fields.
        Example mapping from typical Schwab CHART_EQUITY output:
        - "seq": Sequence Number
        - "1": 225 (Chart mode/type identifier)
        - "2": Open Price (e.g. 488.54)
        - "3": High Price (e.g. 488.58)
        - "4": Low Price (e.g. 488.35)
        - "5": Close Price (e.g. 488.3625)
        - "6": Volume (e.g. 54531.0)
        - "7": Timestamp in ms (e.g. 1743000300000)
        - "8": Additional Chart info

        :param keys: Symbol(s) to subscribe to.
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "CHART_EQUITY",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("CHART_EQUITY", fields),
            },
        )

    def chart_futures(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Chart Futures data.

        Follows standard Schwab Futures Symbol format (e.g. '/ESM24').

        :param keys: Symbol(s) to subscribe to.
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "CHART_FUTURES",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("CHART_FUTURES", fields),
            },
        )

    def screener_equity(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Equity Screener data.

        :param keys: Screener identifier (e.g. '$DOW_JONES_INDUS').
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "SCREENER_EQUITY",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("SCREENER_EQUITY", fields),
            },
        )

    def screener_option(
        self,
        keys: Union[str, List[str]],
        fields: Union[str, List[str]],
        command: str = "ADD",
    ) -> Dict[str, Any]:
        """
        Subscribe to Option Screener data.

        :param keys: Screener identifier.
        :param fields: Numeric fields to request.
        :param command: Command type. Defaults to 'ADD'.
        """
        return self.basic_request(
            "SCREENER_OPTION",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("SCREENER_OPTION", fields),
            },
        )

    def account_activity(
        self,
        keys: Union[str, List[str]],
        fields: Union[
            str, List[str]
        ] = "subscription_key,account,message_type,message_data",
        command: str = "SUBS",
    ) -> Dict[str, Any]:
        """
        Subscribe to Account Activity stream.

        This stream provides real-time updates for account activity such as order fills,
        cancellations, and balance changes.

        :param keys: Streamer subscription keys (often 'Account Activity').
        :param fields: Numeric fields to request. Default is "0,1,2,3" (or their string names).
        :param command: Command type. Defaults to 'SUBS'.
        """
        return self.basic_request(
            "ACCT_ACTIVITY",
            command,
            parameters={
                "keys": format_list(keys),
                "fields": get_numeric_fields("ACCT_ACTIVITY", fields),
            },
        )


class StreamClient(StreamBase):
    def __init__(
        self,
        client: Any,
        logger: Optional[logging.Logger] = None,
        streamer_info: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(client, logger=logger, streamer_info=streamer_info)

    def start(
        self,
        receiver: Callable = print,
        daemon: bool = True,
        ping_interval: int = 20,
        **kwargs,
    ):
        if self.active and (self._thread and self._thread.is_alive()):
            self._logger.warning("Stream already active.")
            return
        else:
            self._loop_ready.clear()

            def _start_asyncio():
                asyncio.run(self._run_streamer(receiver, ping_interval, **kwargs))

            self._thread = threading.Thread(target=_start_asyncio, daemon=daemon)
            self._thread.start()
            self._loop_ready.wait(timeout=5.0)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def __del__(self):
        self.stop()

    def send(
        self, requests: Union[List[Dict[str, Any]], Dict[str, Any]], record: bool = True
    ) -> None:
        if not isinstance(requests, list):
            requests = [requests]

        if record:
            for request in requests:
                self._record_request(request)

        if self._event_loop is None:
            self._logger.info("Stream event loop not initialized yet; request queued.")
        elif not self.active:
            self._logger.info("Stream is not active, request queued.")
        else:
            future = asyncio.run_coroutine_threadsafe(
                self._ws_client.send(json.dumps({"requests": requests})),
                self._event_loop,
            )

            def log_exception(fut):
                try:
                    fut.result()
                except Exception as e:
                    self._logger.error(f"Failed to send stream request: {e}")

            future.add_done_callback(log_exception)

    def stop(self, clear_subscriptions: bool = True) -> None:
        if clear_subscriptions:
            self.subscriptions = {}

        self._should_stop = True

        if self.active and self._ws_client:
            try:
                self.send(
                    self.basic_request(service="ADMIN", command="LOGOUT"), record=False
                )
            except Exception as e:
                self._logger.error(e)
            finally:
                self.active = False

        if self._event_loop and self._ws_client:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._ws_client.close(), self._event_loop
                ).result(timeout=5)
            except Exception as e:
                self._logger.error(f"Error closing websocket: {e}")
            finally:
                self._event_loop = None

        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


class StreamClientAsync(StreamBase):
    def __init__(
        self,
        client: Any,
        logger: Optional[logging.Logger] = None,
        streamer_info: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(client, logger=logger, streamer_info=streamer_info)
        self._task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    async def start(
        self, receiver: Callable = print, ping_interval: int = 20, **kwargs
    ):
        if self.active or (self._task and not self._task.done()):
            self._logger.warning("Stream already active.")
            return
        else:
            self._event_loop = asyncio.get_running_loop()
            self._task = self._event_loop.create_task(
                self._run_streamer(
                    receiver_func=receiver,
                    ping_timeout=ping_interval,
                    **kwargs,
                )
            )

    async def send(
        self, requests: Union[List[Dict[str, Any]], Dict[str, Any]], record: bool = True
    ) -> None:
        if not isinstance(requests, list):
            requests = [requests]

        if record:
            for req in requests:
                self._record_request(req)

        if self._event_loop is None:
            self._logger.info("Stream event loop not initialized yet; request queued.")
        elif not self.active:
            self._logger.info("Stream is not active, request queued.")
        else:
            await self._ws_client.send(json.dumps({"requests": requests}))

    async def stop(self, clear_subscriptions: bool = True) -> None:
        if clear_subscriptions:
            self.subscriptions = {}

        self._should_stop = True

        if self.active and self._ws_client is not None:
            try:
                await self.send(self.basic_request("ADMIN", "LOGOUT"), record=False)
            except Exception as e:
                self._logger.error(f"Error sending LOGOUT: {e}")
            finally:
                self.active = False

        if self._ws_client is not None:
            try:
                await self._ws_client.close()
            except Exception as e:
                self._logger.error(f"Error closing websocket: {e}")
            finally:
                self._event_loop = None

        if self._task is not None:
            try:
                await self._task
            except Exception as e:
                self._logger.error(f"Stream task error on shutdown: {e}")
            finally:
                self._task = None
