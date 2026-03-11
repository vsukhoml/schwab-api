import json
import logging
from types import MappingProxyType
from typing import Any, Dict, Final, List, Optional, Union

logger = logging.getLogger(__name__)

# Standard field mappings based on Schwab API documentation.
# We use string keys because JSON keys arrive as strings.
EQUITIES_MAP: Final = MappingProxyType(
    {
        "0": "symbol",
        "1": "bid_price",
        "2": "ask_price",
        "3": "last_price",
        "4": "bid_size",
        "5": "ask_size",
        "6": "ask_id",
        "7": "bid_id",
        "8": "total_volume",
        "9": "last_size",
        "10": "high_price",
        "11": "low_price",
        "12": "close_price",
        "13": "exchange_id",
        "14": "marginable",
        "15": "description",
        "16": "last_id",
        "17": "open_price",
        "18": "net_change",
        "19": "52_week_high",
        "20": "52_week_low",
        "21": "pe_ratio",
        "22": "annual_dividend_amount",
        "23": "dividend_yield",
        "24": "nav",
        "25": "exchange_name",
        "26": "dividend_date",
        "27": "regular_market_quote",
        "28": "regular_market_trade",
        "29": "regular_market_last_price",
        "30": "regular_market_last_size",
        "31": "regular_market_net_change",
        "32": "security_status",
        "33": "mark_price",
        "34": "quote_time",
        "35": "trade_time",
        "36": "regular_market_trade_time",
        "37": "bid_time",
        "38": "ask_time",
        "39": "ask_mic_id",
        "40": "bid_mic_id",
        "41": "last_mic_id",
        "42": "net_percent_change",
        "43": "regular_market_percent_change",
        "44": "mark_price_net_change",
        "45": "mark_price_percent_change",
        "46": "hard_to_borrow_quantity",
        "47": "hard_to_borrow_rate",
        "48": "hard_to_borrow",
        "49": "shortable",
        "50": "post_market_net_change",
        "51": "post_market_percent_change",
    }
)

OPTIONS_MAP: Final = MappingProxyType(
    {
        "0": "symbol",
        "1": "description",
        "2": "bid_price",
        "3": "ask_price",
        "4": "last_price",
        "5": "high_price",
        "6": "low_price",
        "7": "close_price",
        "8": "total_volume",
        "9": "open_interest",
        "10": "volatility",
        "11": "intrinsic_value",
        "12": "expiration_year",
        "13": "multiplier",
        "14": "digits",
        "15": "open_price",
        "16": "bid_size",
        "17": "ask_size",
        "18": "last_size",
        "19": "net_change",
        "20": "strike_price",
        "21": "contract_type",
        "22": "underlying",
        "23": "expiration_month",
        "24": "deliverables",
        "25": "time_value",
        "26": "expiration_day",
        "27": "days_to_expiration",
        "28": "delta",
        "29": "gamma",
        "30": "theta",
        "31": "vega",
        "32": "rho",
        "33": "security_status",
        "34": "theoretical_option_value",
        "35": "underlying_price",
        "36": "uv_expiration_type",
        "37": "mark_price",
        "38": "quote_time",
        "39": "trade_time",
        "40": "exchange",
        "41": "exchange_name",
        "42": "last_trading_day",
        "43": "settlement_type",
        "44": "net_percent_change",
        "45": "mark_price_net_change",
        "46": "mark_price_percent_change",
        "47": "implied_yield",
        "48": "is_penny_pilot",
        "49": "option_root",
        "50": "52_week_high",
        "51": "52_week_low",
        "52": "indicative_ask_price",
        "53": "indicative_bid_price",
        "54": "indicative_quote_time",
        "55": "exercise_type",
    }
)

FUTURES_MAP: Final = MappingProxyType(
    {
        "0": "symbol",
        "1": "bid_price",
        "2": "ask_price",
        "3": "last_price",
        "4": "bid_size",
        "5": "ask_size",
        "6": "bid_id",
        "7": "ask_id",
        "8": "total_volume",
        "9": "last_size",
        "10": "quote_time",
        "11": "trade_time",
        "12": "high_price",
        "13": "low_price",
        "14": "close_price",
        "15": "exchange_id",
        "16": "description",
        "17": "last_id",
        "18": "open_price",
        "19": "net_change",
        "20": "future_percent_change",
        "21": "exchange_name",
        "22": "security_status",
        "23": "open_interest",
        "24": "mark",
        "25": "tick",
        "26": "tick_amount",
        "27": "product",
        "28": "future_price_format",
        "29": "future_trading_hours",
        "30": "future_is_tradable",
        "31": "future_multiplier",
        "32": "future_is_active",
        "33": "future_settlement_price",
        "34": "future_active_symbol",
        "35": "future_expiration_date",
        "36": "expiration_style",
        "37": "ask_time",
        "38": "bid_time",
        "39": "quoted_in_session",
        "40": "settlement_date",
    }
)

FUTURES_OPTIONS_MAP: Final = MappingProxyType(
    {
        "0": "symbol",
        "1": "bid_price",
        "2": "ask_price",
        "3": "last_price",
        "4": "bid_size",
        "5": "ask_size",
        "6": "bid_id",
        "7": "ask_id",
        "8": "total_volume",
        "9": "last_size",
        "10": "quote_time",
        "11": "trade_time",
        "12": "high_price",
        "13": "low_price",
        "14": "close_price",
        "15": "last_id",
        "16": "description",
        "17": "open_price",
        "18": "open_interest",
        "19": "mark",
        "20": "tick",
        "21": "tick_amount",
        "22": "future_multiplier",
        "23": "future_settlement_price",
        "24": "underlying_symbol",
        "25": "strike_price",
        "26": "future_expiration_date",
        "27": "expiration_style",
        "28": "contract_type",
        "29": "security_status",
        "30": "exchange",
        "31": "exchange_name",
    }
)

FOREX_MAP: Final = MappingProxyType(
    {
        "0": "symbol",
        "1": "bid_price",
        "2": "ask_price",
        "3": "last_price",
        "4": "bid_size",
        "5": "ask_size",
        "6": "total_volume",
        "7": "last_size",
        "8": "quote_time",
        "9": "trade_time",
        "10": "high_price",
        "11": "low_price",
        "12": "close_price",
        "13": "exchange",
        "14": "description",
        "15": "open_price",
        "16": "net_change",
        "17": "percent_change",
        "18": "exchange_name",
        "19": "digits",
        "20": "security_status",
        "21": "tick",
        "22": "tick_amount",
        "23": "product",
        "24": "trading_hours",
        "25": "is_tradable",
        "26": "market_maker",
        "27": "52_week_high",
        "28": "52_week_low",
        "29": "mark",
    }
)

CHART_EQUITY_MAP: Final = MappingProxyType(
    {
        "0": "key",
        "1": "open_price",
        "2": "high_price",
        "3": "low_price",
        "4": "close_price",
        "5": "volume",
        "6": "sequence",
        "7": "chart_time",
        "8": "chart_day",
    }
)

CHART_FUTURES_MAP: Final = MappingProxyType(
    {
        "0": "key",
        "1": "chart_time",
        "2": "open_price",
        "3": "high_price",
        "4": "low_price",
        "5": "close_price",
        "6": "volume",
    }
)

BOOK_MAP: Final = MappingProxyType(
    {
        "0": "symbol",
        "1": "market_snapshot_time",
        "2": "bid_side_levels",
        "3": "ask_side_levels",
    }
)

SCREENER_MAP: Final = MappingProxyType(
    {"0": "symbol", "1": "timestamp", "2": "sort_field", "3": "frequency", "4": "items"}
)

ACCT_ACTIVITY_MAP: Final = MappingProxyType(
    {
        "seq": "sequence",
        "key": "key",
        "1": "account",
        "2": "message_type",
        "3": "message_data",
    }
)

BOOK_LEVEL_MAP: Final = MappingProxyType(
    {
        "0": "price",
        "1": "aggregate_size",
        "2": "market_maker_count",
        "3": "market_makers",
    }
)

MARKET_MAKER_MAP: Final = MappingProxyType(
    {"0": "market_maker_id", "1": "size", "2": "quote_time"}
)

SERVICE_MAPPINGS: Final[MappingProxyType[str, MappingProxyType[str, str]]] = (
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

# Reverse mappings for converting symbolic names back to numeric IDs
REVERSE_SERVICE_MAPPINGS: Final[Dict[str, Dict[str, str]]] = {
    service: {v: k for k, v in mapping.items()}
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
            if nid:
                numeric_ids.append(nid)
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
    Converts raw numeric keys (e.g. '1', '2') from the stream into human-readable dictionary keys.
    """
    mapping = SERVICE_MAPPINGS.get(service_type, MappingProxyType({}))
    parsed = {"key": update_data.get("key")}

    for key, value in update_data.items():
        if key == "key":
            continue

        mapped_key = mapping.get(key, key)

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
                    mlk = BOOK_LEVEL_MAP.get(str(lk), lk)
                    if mlk == "market_makers":
                        # Nested array of market makers
                        mms = []
                        for mm in lv:
                            parsed_mm: Dict[str, Any] = {}
                            for mk, mv in mm.items():
                                parsed_mm[MARKET_MAKER_MAP.get(str(mk), mk)] = mv
                            mms.append(parsed_mm)
                        parsed_level[mlk] = mms
                    else:
                        parsed_level[mlk] = lv
                levels.append(parsed_level)
            parsed[mapped_key] = levels
        else:
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
