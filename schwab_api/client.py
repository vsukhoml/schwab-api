import datetime
import logging
import threading
import urllib.parse
from functools import wraps
from typing import Any, Dict, List, Optional, Union

from .exceptions import (
    AuthError,
    InvalidRequestError,
    RateLimitError,
    ResourceNotFoundError,
    SchwabAPIError,
    ServerError,
)
from .tokens import DEFAULT_CONFIG_PATH, Tokens
from .utils import TimeFormat, format_list, parse_params, time_convert

try:
    # Financial APIs often deploy aggressive Cloudflare/WAF bot-protection.
    # curl_cffi mimics real browser TLS/JA3 fingerprints to bypass these protections.
    from curl_cffi import requests as c_requests  # type: ignore[no-redef]

    HAS_CURL_CFFI = True
except ImportError:
    # Fallback to standard requests if curl_cffi is not installed.
    import requests as c_requests  # type: ignore[no-redef]

    HAS_CURL_CFFI = False


logger = logging.getLogger(__name__)


def check_response(func):
    """Decorator to raise exception on bad HTTP response."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        resp = func(*args, **kwargs)

        correl_id = resp.headers.get("Schwab-Client-CorrelId")
        if correl_id:
            logger.debug(f"Schwab-Client-CorrelId: {correl_id}")

        if not resp.ok:
            error_msg = (
                f"Schwab-Client-CorrelId: {correl_id} - {resp.text}"
                if correl_id
                else resp.text
            )
            if resp.status_code == 429:
                raise RateLimitError(f"HTTP 429 Too Many Requests: {error_msg}")
            elif resp.status_code in (401, 403):
                raise AuthError(f"HTTP {resp.status_code} Auth Error: {error_msg}")
            elif resp.status_code == 400:
                raise InvalidRequestError(f"HTTP 400 Bad Request: {error_msg}")
            elif resp.status_code == 404:
                raise ResourceNotFoundError(f"HTTP 404 Not Found: {error_msg}")
            elif resp.status_code >= 500:
                raise ServerError(f"HTTP {resp.status_code} Server Error: {error_msg}")
            else:
                raise SchwabAPIError(f"HTTP {resp.status_code}: {error_msg}")
        return resp

    return wrapper


class Client:
    """
    The main client for interacting with the Charles Schwab Trading API.

    **Schwab Symbology Nuances:**
    - **Indices**: Typically prefixed with `$` (e.g., `$DJI`, `$SPX`, `$COMPX`, `$VIX`, `$RUT`, `$NDX`, `$TRAN`).
    - **Futures**: Prefixed with `/` (e.g., `/ES`, `/NQ`, `/YM`, `/RTY`, `/GC`, `/SI`, `/CL`).
    - **Common Mappings**:
        - Dow Jones: Index `$DJI`, Futures `/YM`
        - S&P 500: Index `$SPX`, Futures `/ES`
        - Nasdaq 100: Index `$NDX`, Futures `/NQ`
        - Russell 2000: Index `$RUT`, Futures `/RTY`
        - Gold: Index `$XAU`, Futures `/GC`
        - NYSE Amex Composite: `XAX`
    """

    _base_api_url = "https://api.schwabapi.com"

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        callback_url: str = "https://127.0.0.1:8182",
        config_path: str = DEFAULT_CONFIG_PATH,
        timeout: int = 10,
        call_for_auth: Optional[Any] = None,
        logger: Optional[logging.Logger] = None,
    ):
        if timeout <= 0:
            raise ValueError("Timeout must be > 0")

        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)

        self.tokens = Tokens(
            app_key,
            app_secret,
            callback_url,
            config_path=config_path,
            call_for_auth=call_for_auth,
            logger=self.logger,
        )
        self.tokens.update_tokens()

        # Using curl_cffi.requests.Session or standard requests.Session
        self._session: Any
        if HAS_CURL_CFFI:
            self._session = c_requests.Session(impersonate="chrome")
        else:
            self._session = c_requests.Session()

        self._session.headers.update(
            {"Authorization": f"Bearer {self.tokens.access_token}"}
        )
        self._session_lock = threading.RLock()

    def update_tokens(
        self, force_access_token: bool = False, force_refresh_token: bool = False
    ) -> bool:
        if self.tokens.update_tokens(force_access_token, force_refresh_token):
            with self._session_lock:
                self._session.headers["Authorization"] = (
                    f"Bearer {self.tokens.access_token}"
                )
            return True
        return False

    def _request(self, method: str, path: str, **kwargs):
        self.update_tokens()
        with self._session_lock:
            return self._session.request(
                method, f"{self._base_api_url}{path}", timeout=self.timeout, **kwargs
            )  # type: ignore[arg-type]

    def close(self):
        try:
            with self._session_lock:
                self._session.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __del__(self):
        self.close()

    # --- Accounts & Trading ---

    @check_response
    def linked_accounts(self) -> Any:
        """
        Get list of account numbers and their encrypted hashes (hashValue).

        **Nuance:** Almost all Schwab endpoints require this encrypted 'hashValue'
        rather than the raw account number. You must call this first to map them.

        Example:
            >>> client = Client(...)
            >>> accounts = client.linked_accounts().json()
            >>> first_account_hash = accounts[0]['hashValue']
            >>> print(f"Hash for account {accounts[0]['accountNumber']}: {first_account_hash}")
        """
        return self._request("GET", "/trader/v1/accounts/accountNumbers")

    @check_response
    def user_preferences(self) -> Any:
        """
        Get user preference information for the logged in user.
        Includes account nicknames, streamer info, and permissions.
        """
        return self._request("GET", "/trader/v1/userPreference")

    @check_response
    def account_details_all(self, fields: Optional[str] = None) -> Any:
        """
        Get linked account(s) balances and positions for the logged in user.

        :param fields: Optional. Set to 'positions' to include position data in the response.
        """
        return self._request(
            "GET", "/trader/v1/accounts/", params=parse_params({"fields": fields})
        )

    @check_response
    def account_details(self, account_hash: str, fields: Optional[str] = None) -> Any:
        """
        Get a specific account balance and positions for the logged in user.

        :param account_hash: The encrypted ID of the account (hashValue from linked_accounts).
        :param fields: Optional. Set to 'positions' to include position data in the response.

        Example:
            >>> details = client.account_details(account_hash, fields="positions").json()
            >>> positions = details['securitiesAccount']['positions']
        """
        return self._request(
            "GET",
            f"/trader/v1/accounts/{account_hash}",
            params=parse_params({"fields": fields}),
        )

    @check_response
    def account_orders(
        self,
        accountHash: str,
        fromEnteredTime: Union[str, datetime.datetime, None] = None,
        toEnteredTime: Union[str, datetime.datetime, None] = None,
        maxResults: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Any:
        """
        Get all orders for a specific account.

        :param accountHash: The encrypted ID of the account.
        :param fromEnteredTime: No orders entered before this time (ISO-8601).
                                Must be set if toEnteredTime is set.
        :param toEnteredTime: No orders entered after this time (ISO-8601).
                              Must be set if fromEnteredTime is set.
        :param maxResults: Max number of orders to retrieve (default 3000).
        :param status: Filter by status (e.g., FILLED, CANCELED, WORKING).
        """
        return self._request(
            "GET",
            f"/trader/v1/accounts/{accountHash}/orders",
            params=parse_params(
                {
                    "fromEnteredTime": time_convert(
                        fromEnteredTime, TimeFormat.ISO_8601
                    ),
                    "toEnteredTime": time_convert(toEnteredTime, TimeFormat.ISO_8601),
                    "maxResults": maxResults,
                    "status": status,
                }
            ),
        )

    @check_response
    def account_orders_all(
        self,
        fromEnteredTime: Union[str, datetime.datetime, None] = None,
        toEnteredTime: Union[str, datetime.datetime, None] = None,
        maxResults: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Any:
        """
        Get all orders for all linked accounts.

        :param fromEnteredTime: No orders entered before this time (ISO-8601).
                                Date must be within 60 days from today.
        :param toEnteredTime: No orders entered after this time (ISO-8601).
        :param maxResults: Max number of orders to retrieve (default 3000).
        :param status: Filter by status (e.g., FILLED, CANCELED, WORKING).
        """
        return self._request(
            "GET",
            "/trader/v1/orders",
            params=parse_params(
                {
                    "fromEnteredTime": time_convert(
                        fromEnteredTime, TimeFormat.ISO_8601
                    ),
                    "toEnteredTime": time_convert(toEnteredTime, TimeFormat.ISO_8601),
                    "maxResults": maxResults,
                    "status": status,
                }
            ),
        )

    @check_response
    def place_order(self, accountHash: str, order: Dict[str, Any]) -> Any:
        """
        Place an order for a specific account.

        :param accountHash: The encrypted ID of the account.
        :param order: The order object. See documentation for the required schema.
        :return: Response with 201 Created status. The order ID can be extracted from
                 the 'Location' header.

        Example:
            >>> from schwab_api.orders.equities import equity_buy_market
            >>> order = equity_buy_market("AAPL", 10).build()
            >>> resp = client.place_order(account_hash, order)
            >>> order_id = resp.headers.get("Location").split("/")[-1]
        """
        return self._request(
            "POST",
            f"/trader/v1/accounts/{accountHash}/orders",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=order,
        )

    @check_response
    def preview_order(self, accountHash: str, order: Dict[str, Any]) -> Any:
        """
        Preview an order for a specific account.

        :param accountHash: The encrypted ID of the account.
        :param order: The order object.
        """
        return self._request(
            "POST",
            f"/trader/v1/accounts/{accountHash}/previewOrder",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=order,
        )

    @check_response
    def order_details(self, accountHash: str, orderId: Union[int, str]) -> Any:
        """
        Get a specific order by its ID, for a specific account.

        :param accountHash: The encrypted ID of the account.
        :param orderId: The ID of the order being retrieved.
        """
        return self._request(
            "GET", f"/trader/v1/accounts/{accountHash}/orders/{orderId}"
        )

    @check_response
    def cancel_order(self, accountHash: str, orderId: Union[int, str]) -> Any:
        """
        Cancel a specific order for a specific account.

        :param accountHash: The encrypted ID of the account.
        :param orderId: The ID of the order to cancel.
        """
        return self._request(
            "DELETE", f"/trader/v1/accounts/{accountHash}/orders/{orderId}"
        )

    @check_response
    def replace_order(
        self, accountHash: str, orderId: Union[int, str], order: Dict[str, Any]
    ) -> Any:
        """
        Replace an existing order for an account.
        The existing order will be canceled and a new order will be created.

        :param accountHash: The encrypted ID of the account.
        :param orderId: The ID of the order to replace.
        :param order: The new order object.
        :return: Response with 201 Created status. The new order ID can be extracted from
                 the 'Location' header.
        """
        return self._request(
            "PUT",
            f"/trader/v1/accounts/{accountHash}/orders/{orderId}",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=order,
        )

    @check_response
    def transactions(
        self,
        accountHash: str,
        startDate: Union[str, datetime.datetime],
        endDate: Union[str, datetime.datetime],
        types: str,
        symbol: Optional[str] = None,
    ) -> Any:
        """
        Get all transactions for a specific account.

        :param accountHash: The encrypted ID of the account.
        :param startDate: No transactions before this time (ISO-8601).
        :param endDate: No transactions after this time (ISO-8601).
        :param types: Comma-separated list of transaction types (e.g., TRADE, MONEY_MARKET).
        :param symbol: Optional. Filter by symbol.
        """
        return self._request(
            "GET",
            f"/trader/v1/accounts/{accountHash}/transactions",
            params=parse_params(
                {
                    "startDate": time_convert(startDate, TimeFormat.ISO_8601),
                    "endDate": time_convert(endDate, TimeFormat.ISO_8601),
                    "types": types,
                    "symbol": symbol,
                }
            ),
        )

    @check_response
    def transaction_details(
        self, accountHash: str, transactionId: Union[int, str]
    ) -> Any:
        """
        Get specific transaction information for a specific account.

        :param accountHash: The encrypted ID of the account.
        :param transactionId: The ID of the transaction being retrieved.
        """
        return self._request(
            "GET", f"/trader/v1/accounts/{accountHash}/transactions/{transactionId}"
        )

    # --- Market Data ---

    @check_response
    def quotes(
        self,
        symbols: Union[List[str], str],
        fields: Optional[str] = None,
        indicative: bool = False,
    ) -> Any:
        """
        Get quotes for a list of one or more symbols.

        :param symbols: Comma-separated list of symbols (e.g., AAPL,BAC,$DJI).
        :param fields: Optional. Subset of data to return (quote, fundamental, extended, reference, regular).
                       By default, returns all fields.
        :param indicative: Optional. Include indicative quotes for ETF symbols ($ABC.IV).

        Example:
            >>> quote = client.quotes("AAPL").json()
            >>> last_price = quote["AAPL"]["quote"]["lastPrice"]
        """
        return self._request(
            "GET",
            "/marketdata/v1/quotes",
            params=parse_params(
                {
                    "symbols": format_list(symbols),
                    "fields": fields,
                    "indicative": indicative,
                }
            ),
        )

    @check_response
    def quote(self, symbol_id: str, fields: Optional[str] = None) -> Any:
        """
        Get a quote for a single symbol.

        :param symbol_id: The symbol to look up (e.g., AAPL).
        :param fields: Optional. Subset of data to return (quote, fundamental, extended, reference, regular).
        """
        return self._request(
            "GET",
            f"/marketdata/v1/{urllib.parse.quote(symbol_id, safe='')}/quotes",
            params=parse_params({"fields": fields}),
        )

    @check_response
    def option_chains(
        self,
        symbol: str,
        contractType: Optional[str] = None,
        strikeCount: Optional[int] = None,
        includeUnderlyingQuote: Optional[bool] = None,
        strategy: Optional[str] = None,
        interval: Optional[float] = None,
        strike: Optional[float] = None,
        range_val: Optional[str] = None,
        fromDate: Union[str, datetime.date, None] = None,
        toDate: Union[str, datetime.date, None] = None,
        volatility: Optional[float] = None,
        underlyingPrice: Optional[float] = None,
        interestRate: Optional[float] = None,
        daysToExpiration: Optional[int] = None,
        expMonth: Optional[str] = None,
        optionType: Optional[str] = None,
        entitlement: Optional[str] = None,
    ) -> Any:
        """
        Get an option chain for a specific underlying symbol.

        :param symbol: The underlying symbol (e.g., AAPL).
        :param contractType: CALL, PUT, or ALL.
        :param strikeCount: Number of strikes to return above and below the at-the-money price.
        :param includeUnderlyingQuote: Whether to include the underlying quote in the response.
        :param strategy: SINGLE, ANALYTICAL, COVERED, VERTICAL, CALENDAR, STRANGLE, STRADDLE,
                         BUTTERFLY, CONDOR, DIAGONAL, COLLAR, ROLL.
        :param interval: Strike interval for spread strategy chains.
        :param strike: Return options only at this specific strike price.
        :param range_val: ITM, NTM, OTM, SAK, SBK, SNK, or ALL.
        :param fromDate: Only return expirations after this date (yyyy-MM-dd).
        :param toDate: Only return expirations before this date (yyyy-MM-dd).
        :param volatility: Volatility to use in calculations (ANALYTICAL strategy only).
        :param underlyingPrice: Underlying price to use in calculations (ANALYTICAL strategy only).
        :param interestRate: Interest rate to use in calculations (ANALYTICAL strategy only).
        :param daysToExpiration: Days to expiration to use in calculations (ANALYTICAL strategy only).
        :param expMonth: JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG, SEP, OCT, NOV, DEC, or ALL.
        :param optionType: S (Standard), NS (Non-Standard), or ALL.
        :param entitlement: PP (PayingPro), NP (NonPro), or PN (NonPayingPro).

        Example:
            >>> chain = client.option_chains("AAPL", contractType="CALL", strikeCount=5).json()
            >>> call_expirations = chain.get('callExpDateMap', {})
        """
        return self._request(
            "GET",
            "/marketdata/v1/chains",
            params=parse_params(
                {
                    "symbol": symbol,
                    "contractType": contractType,
                    "strikeCount": strikeCount,
                    "includeUnderlyingQuote": includeUnderlyingQuote,
                    "strategy": strategy,
                    "interval": interval,
                    "strike": strike,
                    "range": range_val,
                    "fromDate": time_convert(fromDate, TimeFormat.YYYY_MM_DD),
                    "toDate": time_convert(toDate, TimeFormat.YYYY_MM_DD),
                    "volatility": volatility,
                    "underlyingPrice": underlyingPrice,
                    "interestRate": interestRate,
                    "daysToExpiration": daysToExpiration,
                    "expMonth": expMonth,
                    "optionType": optionType,
                    "entitlement": entitlement,
                }
            ),
        )

    @check_response
    def option_expiration_chain(self, symbol: str) -> Any:
        """Get an option expiration chain for a specific underlying symbol."""
        return self._request(
            "GET",
            "/marketdata/v1/expirationchain",
            params=parse_params({"symbol": symbol}),
        )

    @check_response
    def price_history(
        self,
        symbol: str,
        periodType: Optional[str] = None,
        period: Optional[int] = None,
        frequencyType: Optional[str] = None,
        frequency: Optional[int] = None,
        startDate: Union[str, datetime.datetime, None] = None,
        endDate: Union[str, datetime.datetime, None] = None,
        needExtendedHoursData: Optional[bool] = None,
        needPreviousClose: Optional[bool] = None,
    ) -> Any:
        """
        Get historical price data (candles) for a specific symbol.

        :param symbol: Equity symbol to look up (e.g., AAPL).
        :param periodType: The chart period being requested (day, month, year, ytd).
        :param period: The number of chart period types.
                       - day: 1, 2, 3, 4, 5, 10
                       - month: 1, 2, 3, 6
                       - year: 1, 2, 3, 5, 10, 15, 20
                       - ytd: 1
        :param frequencyType: The time frequency type (minute, daily, weekly, monthly).
        :param frequency: The time frequency duration.
                          - minute: 1, 5, 10, 15, 30
                          - daily, weekly, monthly: 1
        :param startDate: Start date as milliseconds since the UNIX epoch.
        :param endDate: End date as milliseconds since the UNIX epoch.
        :param needExtendedHoursData: If true, returns extended hours data.
        :param needPreviousClose: If true, includes previous close price/date in response.

        Example:
            >>> history = client.price_history("AAPL", periodType="day", period=5, frequencyType="minute", frequency=15).json()
            >>> candles = history.get('candles', [])
        """
        return self._request(
            "GET",
            "/marketdata/v1/pricehistory",
            params=parse_params(
                {
                    "symbol": symbol,
                    "periodType": periodType,
                    "period": period,
                    "frequencyType": frequencyType,
                    "frequency": frequency,
                    "startDate": time_convert(startDate, TimeFormat.EPOCH_MS),
                    "endDate": time_convert(endDate, TimeFormat.EPOCH_MS),
                    "needExtendedHoursData": needExtendedHoursData,
                    "needPreviousClose": needPreviousClose,
                }
            ),
        )

    @check_response
    def instruments(self, symbols: Union[str, List[str]], projection: str) -> Any:
        """
        Search for instruments.

        :param symbols: Symbol or search term. Can be a single string or list of strings.
        :param projection: Search type (symbol-search, symbol-regex, desc-search, desc-regex,
                           search, fundamental).
        """
        return self._request(
            "GET",
            "/marketdata/v1/instruments",
            params={"symbol": format_list(symbols), "projection": projection},
        )

    @check_response
    def instrument_cusip(self, cusip_id: Union[str, int]) -> Any:
        """
        Get basic instrument details by CUSIP.

        :param cusip_id: The CUSIP of the security.
        """
        return self._request("GET", f"/marketdata/v1/instruments/{cusip_id}")

    @check_response
    def movers(
        self,
        symbol_id: str,
        sort: Optional[str] = None,
        frequency: Optional[int] = None,
    ) -> Any:
        """
        Get movers for a specific index.

        :param symbol_id: The index symbol (e.g., $DJI, $COMPX, $SPX, NYSE, NASDAQ, OTCBB,
                          INDEX_ALL, EQUITY_ALL, OPTION_ALL, OPTION_PUT, OPTION_CALL).
        :param sort: Attribute to sort by (VOLUME, TRADES, PERCENT_CHANGE_UP, PERCENT_CHANGE_DOWN).
        :param frequency: Frequency in minutes (0, 1, 5, 10, 30, 60).
        """
        return self._request(
            "GET",
            f"/marketdata/v1/movers/{urllib.parse.quote(symbol_id, safe='')}",
            params=parse_params({"sort": sort, "frequency": frequency}),
        )

    @check_response
    def market_hours(
        self,
        markets: Union[List[str], str],
        date: Union[str, datetime.date, None] = None,
    ) -> Any:
        """
        Get Market Hours for different markets.

        :param markets: List of markets (equity, option, bond, future, forex).
        :param date: Date for which to get market hours (yyyy-MM-dd). Defaults to today.
        """
        return self._request(
            "GET",
            "/marketdata/v1/markets",
            params=parse_params(
                {
                    "markets": format_list(markets),
                    "date": time_convert(date, TimeFormat.YYYY_MM_DD),
                }
            ),
        )

    @check_response
    def market_hours_for_market(
        self, market_id: str, date: Union[str, datetime.date, None] = None
    ) -> Any:
        """
        Get Market Hours for a single market.

        Note: The response is still keyed by the market type (e.g., {"equity": {"EQ": ...}}).

        :param market_id: The market ID (equity, option, bond, future, forex).
        :param date: Date for which to get market hours (yyyy-MM-dd). Defaults to today.
        """
        return self._request(
            "GET",
            f"/marketdata/v1/markets/{market_id}",
            params=parse_params({"date": time_convert(date, TimeFormat.YYYY_MM_DD)}),
        )

    # --- Convenience Wrappers ---
    def get_daily_price_history(
        self, symbol: str, start_date: Optional[datetime.datetime] = None
    ) -> Any:
        """Get daily price history for a symbol as a Pandas DataFrame."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for this function. Install it using 'pip install pandas'."
            )

        from .utils import TIMEZONE_EST, parse_price_history_to_df, to_schwab

        schwab_symbol = to_schwab(symbol)
        end_date = datetime.datetime.now(TIMEZONE_EST)
        if end_date.hour < 17:
            end_date = end_date.replace(
                hour=20, minute=59, second=59
            ) - datetime.timedelta(days=1)

        if not start_date:
            start_date = datetime.datetime(1980, 1, 1)

        try:
            resp = self.price_history(
                schwab_symbol,
                frequencyType="daily",
                periodType="year",
                period=20,
                startDate=start_date,
                endDate=end_date,
                needExtendedHoursData=True,
            )
            return parse_price_history_to_df(resp.json())
        except Exception as e:
            self.logger.error(f"Error getting price history for {symbol}: {e}")
            return pd.DataFrame()

    def get_fundamentals(self, tickers: Union[List[str], set]) -> Dict[str, Any]:
        """Get fundamentals for a list of tickers, mapped back to original tickers."""
        from .utils import TIMEZONE_EST, to_schwab

        def parse_date(f, field):
            date_str = f.get(field, None)
            if date_str:
                try:
                    f[field] = datetime.datetime.strptime(
                        date_str, "%Y-%m-%d %H:%M:%S.%f"
                    ).astimezone(TIMEZONE_EST)
                except ValueError:
                    pass

        result = {}
        chunk_size = 127
        schwab_dict = {to_schwab(t): t for t in tickers}
        schwab_tickers = list(schwab_dict.keys())

        for i in range(0, len(schwab_tickers), chunk_size):
            chunk = schwab_tickers[i : i + chunk_size]
            resp = self.instruments(chunk, "fundamental")
            instrument_info = resp.json().get("instruments", [])

            for instrument in instrument_info:
                symbol = instrument.get("symbol", None)
                if not symbol:
                    continue
                ticker = schwab_dict.get(symbol)
                if not ticker:
                    continue

                fundamental = instrument.pop("fundamental", None)
                if not fundamental:
                    continue

                instrument.update(fundamental)
                for date_field in [
                    "dividendDate",
                    "dividendPayDate",
                    "declarationDate",
                    "nextDividendPayDate",
                    "nextDividendDate",
                    "corpactionDate",
                ]:
                    parse_date(instrument, date_field)

                instrument["schwab_updated"] = datetime.datetime.now(TIMEZONE_EST)
                instrument["schwab_symbol"] = symbol
                if "symbol" in instrument:
                    instrument.pop("symbol")

                result[ticker] = instrument

        return result
