import json
import logging
from types import MappingProxyType
from typing import Any, Callable, Dict, Final, List, Optional, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field maps: numeric key → (field_name, cast_fn | None)
#
# Each entry encodes both the human-readable name and the type-cast function
# in a single lookup.  Fields whose values are already the correct Python type
# (strings, structured objects) use ``None`` as the cast function.
#
# NOTE: hard_to_borrow / shortable use _i (not _b) because Schwab encodes
#       them as -1=NULL / 0=false / 1=true — bool(-1) would silently lose NULL.
# ---------------------------------------------------------------------------


def _to_bool(v: Any) -> bool:
    """Safe bool cast: handles Python bools and Schwab 'true'/'false' strings."""
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1")


# Compact aliases for type-cast callables used in the map literals below.
_f: Callable[[Any], float] = float
_i: Callable[[Any], int] = int
_b: Callable[[Any], bool] = _to_bool

# Type alias for a single field-map entry.
_FieldEntry = tuple[str, Optional[Callable[[Any], Any]]]

EQUITIES_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("symbol", None),
        "1": ("bid_price", _f),
        "2": ("ask_price", _f),
        "3": ("last_price", _f),
        "4": ("bid_size", _i),
        "5": ("ask_size", _i),
        "6": ("ask_id", None),
        "7": ("bid_id", None),
        "8": ("total_volume", _i),
        "9": ("last_size", _i),
        "10": ("high_price", _f),
        "11": ("low_price", _f),
        "12": ("close_price", _f),
        "13": ("exchange_id", None),
        "14": ("marginable", _b),
        "15": ("description", None),
        "16": ("last_id", None),
        "17": ("open_price", _f),
        "18": ("net_change", _f),
        "19": ("52_week_high", _f),
        "20": ("52_week_low", _f),
        "21": ("pe_ratio", _f),
        "22": ("annual_dividend_amount", _f),
        "23": ("dividend_yield", _f),
        "24": ("nav", _f),
        "25": ("exchange_name", None),
        "26": ("dividend_date", None),
        "27": ("regular_market_quote", _b),
        "28": ("regular_market_trade", _b),
        "29": ("regular_market_last_price", _f),
        "30": ("regular_market_last_size", _i),
        "31": ("regular_market_net_change", _f),
        "32": ("security_status", None),
        "33": ("mark_price", _f),
        "34": ("quote_time", _i),
        "35": ("trade_time", _i),
        "36": ("regular_market_trade_time", _i),
        "37": ("bid_time", _i),
        "38": ("ask_time", _i),
        "39": ("ask_mic_id", None),
        "40": ("bid_mic_id", None),
        "41": ("last_mic_id", None),
        "42": ("net_percent_change", _f),
        "43": ("regular_market_percent_change", _f),
        "44": ("mark_price_net_change", _f),
        "45": ("mark_price_percent_change", _f),
        "46": ("hard_to_borrow_quantity", _i),
        "47": ("hard_to_borrow_rate", _f),
        "48": ("hard_to_borrow", _i),  # -1=NULL sentinel: use int, not bool
        "49": ("shortable", _i),  # -1=NULL sentinel: use int, not bool
        "50": ("post_market_net_change", _f),
        "51": ("post_market_percent_change", _f),
    }
)

OPTIONS_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("symbol", None),
        "1": ("description", None),
        "2": ("bid_price", _f),
        "3": ("ask_price", _f),
        "4": ("last_price", _f),
        "5": ("high_price", _f),
        "6": ("low_price", _f),
        "7": ("close_price", _f),
        "8": ("total_volume", _i),
        "9": ("open_interest", _i),
        "10": ("volatility", _f),
        "11": ("intrinsic_value", _f),
        "12": ("expiration_year", _i),
        "13": ("multiplier", _f),
        "14": ("digits", _i),
        "15": ("open_price", _f),
        "16": ("bid_size", _i),
        "17": ("ask_size", _i),
        "18": ("last_size", _i),
        "19": ("net_change", _f),
        "20": ("strike_price", _f),
        "21": ("contract_type", None),
        "22": ("underlying", None),
        "23": ("expiration_month", _i),
        "24": ("deliverables", None),
        "25": ("time_value", _f),
        "26": ("expiration_day", _i),
        "27": ("days_to_expiration", _i),
        "28": ("delta", _f),
        "29": ("gamma", _f),
        "30": ("theta", _f),
        "31": ("vega", _f),
        "32": ("rho", _f),
        "33": ("security_status", None),
        "34": ("theoretical_option_value", _f),
        "35": ("underlying_price", _f),
        "36": ("uv_expiration_type", None),
        "37": ("mark_price", _f),
        "38": ("quote_time", _i),
        "39": ("trade_time", _i),
        "40": ("exchange", None),
        "41": ("exchange_name", None),
        "42": ("last_trading_day", _i),
        "43": ("settlement_type", None),
        "44": ("net_percent_change", _f),
        "45": ("mark_price_net_change", _f),
        "46": ("mark_price_percent_change", _f),
        "47": ("implied_yield", _f),
        "48": ("is_penny_pilot", _b),
        "49": ("option_root", None),
        "50": ("52_week_high", _f),
        "51": ("52_week_low", _f),
        "52": ("indicative_ask_price", _f),
        "53": ("indicative_bid_price", _f),
        "54": ("indicative_quote_time", _i),
        "55": ("exercise_type", None),
    }
)

FUTURES_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("symbol", None),
        "1": ("bid_price", _f),
        "2": ("ask_price", _f),
        "3": ("last_price", _f),
        "4": ("bid_size", _i),
        "5": ("ask_size", _i),
        "6": ("bid_id", None),
        "7": ("ask_id", None),
        "8": ("total_volume", _i),
        "9": ("last_size", _i),
        "10": ("quote_time", _i),
        "11": ("trade_time", _i),
        "12": ("high_price", _f),
        "13": ("low_price", _f),
        "14": ("close_price", _f),
        "15": ("exchange_id", None),
        "16": ("description", None),
        "17": ("last_id", None),
        "18": ("open_price", _f),
        "19": ("net_change", _f),
        "20": ("future_percent_change", _f),
        "21": ("exchange_name", None),
        "22": ("security_status", None),
        "23": ("open_interest", _i),
        "24": ("mark", _f),
        "25": ("tick", _f),
        "26": ("tick_amount", _f),
        "27": ("product", None),
        "28": ("future_price_format", None),
        "29": ("future_trading_hours", None),
        "30": ("future_is_tradable", _b),
        "31": ("future_multiplier", _f),
        "32": ("future_is_active", _b),
        "33": ("future_settlement_price", _f),
        "34": ("future_active_symbol", None),
        "35": ("future_expiration_date", _i),
        "36": ("expiration_style", None),
        "37": ("ask_time", _i),
        "38": ("bid_time", _i),
        "39": ("quoted_in_session", _b),
        "40": ("settlement_date", _i),
    }
)

FUTURES_OPTIONS_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("symbol", None),
        "1": ("bid_price", _f),
        "2": ("ask_price", _f),
        "3": ("last_price", _f),
        "4": ("bid_size", _i),
        "5": ("ask_size", _i),
        "6": ("bid_id", None),
        "7": ("ask_id", None),
        "8": ("total_volume", _i),
        "9": ("last_size", _i),
        "10": ("quote_time", _i),
        "11": ("trade_time", _i),
        "12": ("high_price", _f),
        "13": ("low_price", _f),
        "14": ("close_price", _f),
        "15": ("last_id", None),
        "16": ("description", None),
        "17": ("open_price", _f),
        "18": ("open_interest", _f),  # documented as "double" in Schwab spec
        "19": ("mark", _f),
        "20": ("tick", _f),
        "21": ("tick_amount", _f),
        "22": ("future_multiplier", _f),
        "23": ("future_settlement_price", _f),
        "24": ("underlying_symbol", None),
        "25": ("strike_price", _f),
        "26": ("future_expiration_date", _i),
        "27": ("expiration_style", None),
        "28": ("contract_type", None),
        "29": ("security_status", None),
        "30": ("exchange", None),
        "31": ("exchange_name", None),
    }
)

FOREX_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("symbol", None),
        "1": ("bid_price", _f),
        "2": ("ask_price", _f),
        "3": ("last_price", _f),
        "4": ("bid_size", _i),
        "5": ("ask_size", _i),
        "6": ("total_volume", _i),
        "7": ("last_size", _i),
        "8": ("quote_time", _i),
        "9": ("trade_time", _i),
        "10": ("high_price", _f),
        "11": ("low_price", _f),
        "12": ("close_price", _f),
        "13": ("exchange", None),
        "14": ("description", None),
        "15": ("open_price", _f),
        "16": ("net_change", _f),
        "17": ("percent_change", _f),
        "18": ("exchange_name", None),
        "19": ("digits", _i),
        "20": ("security_status", None),
        "21": ("tick", _f),
        "22": ("tick_amount", _f),
        "23": ("product", None),
        "24": ("trading_hours", None),
        "25": ("is_tradable", _b),
        "26": ("market_maker", None),
        "27": ("52_week_high", _f),
        "28": ("52_week_low", _f),
        "29": ("mark", _f),
    }
)

CHART_EQUITY_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("key", None),
        "1": ("open_price", _f),
        "2": ("high_price", _f),
        "3": ("low_price", _f),
        "4": ("close_price", _f),
        "5": ("volume", _f),  # documented as "double"
        "6": ("sequence", _i),
        "7": ("chart_time", _i),
        "8": ("chart_day", _i),
    }
)

CHART_FUTURES_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("key", None),
        "1": ("chart_time", _i),
        "2": ("open_price", _f),
        "3": ("high_price", _f),
        "4": ("low_price", _f),
        "5": ("close_price", _f),
        "6": ("volume", _f),  # documented as "double"
    }
)

BOOK_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("symbol", None),
        "1": ("market_snapshot_time", None),
        "2": ("bid_side_levels", None),
        "3": ("ask_side_levels", None),
    }
)

SCREENER_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("symbol", None),
        "1": ("timestamp", None),
        "2": ("sort_field", None),
        "3": ("frequency", None),
        "4": ("items", None),
    }
)

ACCT_ACTIVITY_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("subscription_key", None),
        "seq": ("sequence", None),
        "key": ("key", None),
        "1": ("account", None),
        "2": ("message_type", None),
        "3": ("message_data", None),
    }
)

BOOK_LEVEL_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {
        "0": ("price", None),
        "1": ("aggregate_size", None),
        "2": ("market_maker_count", None),
        "3": ("market_makers", None),
    }
)

MARKET_MAKER_MAP: Final[MappingProxyType[str, _FieldEntry]] = MappingProxyType(
    {"0": ("market_maker_id", None), "1": ("size", None), "2": ("quote_time", None)}
)

SERVICE_MAPPINGS: Final[MappingProxyType[str, MappingProxyType[str, _FieldEntry]]] = (
    MappingProxyType(
        {
            "LEVELONE_EQUITIES": EQUITIES_MAP,
            "LEVELONE_OPTIONS": OPTIONS_MAP,
            "LEVELONE_FUTURES": FUTURES_MAP,
            "LEVELONE_FUTURES_OPTIONS": FUTURES_OPTIONS_MAP,
            "LEVELONE_FOREX": FOREX_MAP,
            "CHART_EQUITY": CHART_EQUITY_MAP,
            "CHART_FUTURES": CHART_FUTURES_MAP,
            "NYSE_BOOK": BOOK_MAP,
            "NASDAQ_BOOK": BOOK_MAP,
            "OPTIONS_BOOK": BOOK_MAP,
            "SCREENER_EQUITY": SCREENER_MAP,
            "SCREENER_OPTION": SCREENER_MAP,
            "ACCT_ACTIVITY": ACCT_ACTIVITY_MAP,
        }
    )
)

# Reverse mappings for converting symbolic names back to numeric IDs.
REVERSE_SERVICE_MAPPINGS: Final[Dict[str, Dict[str, str]]] = {
    service: {entry[0]: k for k, entry in mapping.items()}
    for service, mapping in SERVICE_MAPPINGS.items()
}


def get_numeric_fields(service_type: str, symbolic_names: Union[str, List[str]]) -> str:
    """
    Converts human-readable symbolic field names back into comma-separated numeric IDs.
    Useful for creating subscription requests.
    """
    if isinstance(symbolic_names, str):
        names = [n.strip() for n in symbolic_names.split(",")]
    else:
        names = list(symbolic_names)

    mapping = REVERSE_SERVICE_MAPPINGS.get(service_type, {})
    numeric_ids = []

    for name in names:
        # If the name is already a number, keep it. Otherwise look it up.
        if str(name).isdigit():
            numeric_ids.append(str(name))
        else:
            nid = mapping.get(name)
            if nid is not None:
                numeric_ids.append(str(nid))
            else:
                logger.warning(
                    f"Unknown symbolic field name '{name}' for service {service_type}"
                )
                numeric_ids.append(str(name))

    return ",".join(numeric_ids)


def parse_numeric_fields(
    update_data: Dict[str, Any], service_type: str
) -> Dict[str, Any]:
    """
    Converts raw numeric keys (e.g. ``'1'``, ``'2'``) from the stream into
    human-readable dictionary keys and casts values to their correct Python types
    (``float``, ``int``, ``bool``).

    Each entry in a service map is a ``(field_name, cast_fn | None)`` tuple.
    The name translation and type cast are resolved in a single dict lookup,
    eliminating the secondary type-map look-up used in earlier implementations.

    Fields without a cast function and ``None`` values are passed through unchanged.
    Cast failures (e.g. malformed values from Schwab) silently preserve the raw value.
    """
    mapping = SERVICE_MAPPINGS.get(service_type, MappingProxyType({}))
    parsed: Dict[str, Any] = {"key": update_data.get("key")}

    for key, value in update_data.items():
        if key == "key":
            continue

        entry = mapping.get(key)
        mapped_key, cast_fn = entry if entry is not None else (key, None)

        # Handle nested levels for Book services
        if service_type in ("NYSE_BOOK", "NASDAQ_BOOK", "OPTIONS_BOOK") and key in (
            "2",
            "3",
        ):
            # value is an array of price levels
            levels = []
            for level in value:
                parsed_level: Dict[str, Any] = {}
                for lk, lv in level.items():
                    level_entry = BOOK_LEVEL_MAP.get(str(lk))
                    mlk = level_entry[0] if level_entry is not None else lk
                    if mlk == "market_makers":
                        # Nested array of market makers
                        mms = []
                        for mm in lv:
                            mm_entry_get = MARKET_MAKER_MAP.get
                            mms.append(
                                {
                                    (mm_entry_get(str(mk)) or (mk, None))[0]: mv
                                    for mk, mv in mm.items()
                                }
                            )
                        parsed_level[mlk] = mms
                    else:
                        parsed_level[mlk] = lv
                levels.append(parsed_level)
            parsed[mapped_key] = levels
        else:
            if cast_fn is not None and value is not None:
                try:
                    value = cast_fn(value)
                except (ValueError, TypeError):
                    pass  # preserve raw value on unexpected encoding
            parsed[mapped_key] = value

    return parsed


class StreamResponseHandler:
    """
    A base class for handling parsed stream events.
    Subclass this and override the specific `on_*` methods you need.
    It can also act as a dispatcher to multiple sub-handlers via chaining.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._handlers: List["StreamResponseHandler"] = []

    def add_handler(self, handler: "StreamResponseHandler") -> None:
        """
        Adds a sub-handler that will receive all parsed stream events.
        Useful for chaining multiple independent modules that rely on the same stream.

        Args:
            handler (StreamResponseHandler): The handler instance to add to the chain.
        """
        if handler not in self._handlers:
            self._handlers.append(handler)

    def remove_handler(self, handler: "StreamResponseHandler") -> None:
        """
        Removes a previously attached sub-handler from the chain.

        Args:
            handler (StreamResponseHandler): The handler instance to remove.
        """
        if handler in self._handlers:
            self._handlers.remove(handler)

    def handle(self, raw_message: Union[str, Dict[str, Any]]) -> None:
        """
        Main entry point. Call this from the stream client's receiver callback.
        Parses raw API stream messages and dispatches them to appropriate typed events.

        Args:
            raw_message (Union[str, Dict[str, Any]]): The raw JSON string or dict from the stream.
        """
        try:
            if isinstance(raw_message, str):
                # Replace Schwab's custom infinity symbol before parsing
                data = json.loads(raw_message.replace("∞", "9999999"))
            else:
                data = raw_message

            # Process data payloads
            payloads = data.get("data", [])
            for payload in payloads:
                service = payload.get("service")
                content = payload.get("content", [])

                for update in content:
                    parsed_update = parse_numeric_fields(update, service)
                    self._dispatch(service, parsed_update)

            # Process response payloads
            responses = data.get("response", [])
            for response in responses:
                self.on_response(response)
                for h in self._handlers:
                    h.on_response(response)

        except Exception as e:
            self._logger.error(f"Error handling stream message: {e}")

    def _dispatch(self, service: str, update: Dict[str, Any]) -> None:
        """
        Routes the parsed update to the corresponding specific handler and all attached sub-handlers.

        Args:
            service (str): The Schwab streaming service type (e.g. 'LEVELONE_EQUITIES').
            update (Dict[str, Any]): The parsed, human-readable update dictionary.
        """
        match service:
            case "LEVELONE_EQUITIES":
                self.on_level_one_equity(update)
                for h in self._handlers:
                    h.on_level_one_equity(update)
            case "LEVELONE_OPTIONS":
                self.on_level_one_option(update)
                for h in self._handlers:
                    h.on_level_one_option(update)
            case "LEVELONE_FUTURES":
                self.on_level_one_future(update)
                for h in self._handlers:
                    h.on_level_one_future(update)
            case "LEVELONE_FUTURES_OPTIONS":
                self.on_level_one_future_option(update)
                for h in self._handlers:
                    h.on_level_one_future_option(update)
            case "LEVELONE_FOREX":
                self.on_level_one_forex(update)
                for h in self._handlers:
                    h.on_level_one_forex(update)
            case "CHART_EQUITY":
                self.on_chart_equity(update)
                for h in self._handlers:
                    h.on_chart_equity(update)
            case "CHART_FUTURES":
                self.on_chart_future(update)
                for h in self._handlers:
                    h.on_chart_future(update)
            case "SCREENER_EQUITY" | "SCREENER_OPTION":
                # Screeners contain a list of items under the 'items' key
                key = str(update.get("key", ""))
                items = update.get("items", [])
                for item in items:
                    self.on_screener_item(service, key, item)
                    for h in self._handlers:
                        h.on_screener_item(service, key, item)
            case "NYSE_BOOK" | "NASDAQ_BOOK" | "OPTIONS_BOOK":
                self.on_book_update(service, update)
                for h in self._handlers:
                    h.on_book_update(service, update)
            case "ACCT_ACTIVITY":
                self.on_account_activity(update)
                for h in self._handlers:
                    h.on_account_activity(update)
            case _:
                self.on_unknown_event(service, update)
                for h in self._handlers:
                    h.on_unknown_event(service, update)

    # --- Methods to override in subclasses ---

    def on_level_one_equity(self, update: Dict[str, Any]) -> None:
        pass

    def on_level_one_option(self, update: Dict[str, Any]) -> None:
        pass

    def on_level_one_future(self, update: Dict[str, Any]) -> None:
        pass

    def on_level_one_future_option(self, update: Dict[str, Any]) -> None:
        pass

    def on_level_one_forex(self, update: Dict[str, Any]) -> None:
        pass

    def on_chart_equity(self, update: Dict[str, Any]) -> None:
        pass

    def on_chart_future(self, update: Dict[str, Any]) -> None:
        pass

    def on_screener_item(
        self, service: str, screener_key: str, item: Dict[str, Any]
    ) -> None:
        pass

    def on_book_update(self, service: str, update: Dict[str, Any]) -> None:
        pass

    def on_account_activity(self, update: Dict[str, Any]) -> None:
        pass

    def on_response(self, response: Dict[str, Any]) -> None:
        pass

    def on_unknown_event(self, service: str, update: Dict[str, Any]) -> None:
        pass
