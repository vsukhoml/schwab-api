import datetime
from enum import Enum
from typing import Any

from pytz import timezone

TIMEZONE_EST = timezone("America/New_York")
#: Standard equity option multiplier: each contract represents 100 shares.
OPTION_CONTRACT_SIZE = 100


class TimeFormat(Enum):
    ISO_8601 = "ISO_8601"
    EPOCH = "EPOCH"
    EPOCH_MS = "EPOCH_MS"
    YYYY_MM_DD = "YYYY_MM_DD"


def time_convert(dt, fmt: TimeFormat = TimeFormat.ISO_8601) -> str | int | None:
    """
    Convert a Python date/datetime to the string or integer format required by Schwab endpoints.

    Non-datetime values are passed through unchanged so this function can be called
    unconditionally on raw parameter values without extra ``isinstance`` guards.

    Args:
        dt: Value to convert.  If it is a ``datetime.datetime`` or ``datetime.date``
            the conversion is applied.  Any other type (``str``, ``int``, ``None``)
            is returned as-is.
        fmt (TimeFormat): Target format.

            * ``ISO_8601`` — ``"YYYY-MM-DDTHH:MM:SS.mmmZ"`` (millisecond precision,
              always UTC ``Z`` suffix).  Schwab requires exactly 3 decimal places;
              Python's ``%f`` gives 6, so the last 3 digits are stripped.
            * ``EPOCH`` — Unix timestamp as an ``int`` (seconds since 1970-01-01 UTC).
            * ``EPOCH_MS`` — Unix timestamp as an ``int`` (milliseconds since epoch).
            * ``YYYY_MM_DD`` — Plain date string ``"YYYY-MM-DD"`` for date-range params.

    Returns:
        ``str`` for ISO_8601 / YYYY_MM_DD, ``int`` for EPOCH / EPOCH_MS,
        or the original ``dt`` value if it is not a datetime/date.

    Raises:
        ValueError: If ``fmt`` is not a recognized ``TimeFormat`` member.

    Notes:
        A bare ``datetime.date`` (not ``datetime.datetime``) is promoted to midnight
        UTC before conversion so that epoch values are deterministic regardless of
        the caller's local timezone.
    """
    if dt is None or not (
        isinstance(dt, datetime.datetime) or isinstance(dt, datetime.date)
    ):
        return dt

    if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        dt = datetime.datetime.combine(
            dt, datetime.time.min, tzinfo=datetime.timezone.utc
        )

    if fmt == TimeFormat.ISO_8601:
        # Schwab expects exactly 3 decimals for milliseconds, e.g. "2023-01-01T00:00:00.000Z".
        # Python's .strftime('%f') provides 6 decimals, so we truncate the last 3.
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z"
    elif fmt == TimeFormat.EPOCH:
        return int(dt.timestamp())
    elif fmt == TimeFormat.EPOCH_MS:
        return int(dt.timestamp() * 1000)
    elif fmt == TimeFormat.YYYY_MM_DD:
        return dt.strftime("%Y-%m-%d")
    else:
        raise ValueError(f"Unsupported time format: {fmt}")


def to_schwab(t: str) -> str:
    """
    Convert a Yahoo Finance ticker symbol to its Schwab API equivalent.

    Schwab uses different conventions than Yahoo Finance for indices, preferred
    shares, units, warrants, and rights.  This function maps the most common cases
    so callers can use Yahoo Finance symbols directly with Schwab endpoints.

    Conversion rules applied in order:

    1. Index prefix: ``^`` → ``$``  (e.g. ``^SPX`` → ``$SPX``, ``^VIX`` → ``$VIX``).
    2. Short tickers (fewer than 3 characters) are returned unchanged.
    3. Suffix mapping for special share classes (last 2–3 characters):

       | Yahoo suffix | Schwab suffix | Example |
       |---|---|---|
       | ``.P`` or ``-P`` | ``/PR`` | ``WFC-P`` → ``WFC/PR`` |
       | ``-PA``, ``-PB``, … | ``/PRA``, ``/PRB``, … | ``GS-PB`` → ``GS/PRB`` |
       | ``-A``, ``.B``, … | ``/A``, ``/B`` | ``BRK-B`` → ``BRK/B``, ``BF.A`` → ``BF/A`` |
       | ``-UN`` | ``/U`` | ``PSTH-UN`` → ``PSTH/U`` |
       | ``-WT`` | ``/WS`` | ``AJAX-WT`` → ``AJAX/WS`` |
       | ``-RI`` | ``/RT`` | ``XYZ-RI`` → ``XYZ/RT`` |

    4. If none of the above patterns match, the ticker is returned unchanged.

    Args:
        t (str): Ticker symbol in Yahoo Finance format.

    Returns:
        str: Ticker symbol in Schwab API format.

    Examples:
        >>> to_schwab("^DJI")
        '$DJI'
        >>> to_schwab("BRK-B")
        'BRK/B'
        >>> to_schwab("BF.A")
        'BF/A'
        >>> to_schwab("AAPL")
        'AAPL'
        >>> to_schwab("WFC-PA")
        'WFC/PRA'
    """
    if not t:
        return t
    if t[0] == "^":
        return "$" + t[1:]
    if len(t) < 3:
        return t

    # Preferred shares and other special share classes often use '-' or '.'
    # in Yahoo Finance, but Schwab expects '/' and specific codes like 'PR'.
    match (t[-3], t[-2], t[-1]):
        case (_, ".", "P") | (_, "-", "P"):
            return t[:-2] + "/PR"
        case (_, ".", l) | (_, "-", l):
            return t[:-2] + "/" + l
        case ("-", "P", l):
            return t[:-3] + "/PR" + l
        case ("-", "U", "N"):
            return t[:-3] + "/U"
        case ("-", "W", "T"):
            return t[:-3] + "/WS"
        case ("-", "R", "I"):
            return t[:-3] + "/RT"
    return t


def format_list(lst: Any | None) -> str | None:
    """
    Convert a Python list or any iterable to a comma-separated string for API query parameters.

    Schwab endpoints that accept multiple values (e.g. multiple symbols or field IDs)
    require them as a single comma-delimited string rather than repeated query keys.

    Args:
        lst: Value to format.

            * ``None`` → ``None`` (preserved so ``parse_params`` strips it cleanly).
            * ``str`` → returned as-is (already formatted).
            * Any iterable → each element stringified and joined with ``","`` .
            * Any other scalar → ``str(lst)``.

    Returns:
        A comma-separated ``str``, or ``None`` if the input was ``None``.

    Examples:
        >>> format_list(["AAPL", "MSFT", "GOOG"])
        'AAPL,MSFT,GOOG'
        >>> format_list("AAPL,MSFT")
        'AAPL,MSFT'
        >>> format_list(None)
        None
    """
    if lst is None:
        return None
    elif isinstance(lst, str):
        return lst
    elif hasattr(lst, "__iter__"):
        return ",".join(map(str, lst))
    else:
        return str(lst)


def parse_params(params: dict) -> dict:
    """
    Remove ``None`` entries from a parameter dictionary before passing it to ``requests``.

    ``requests`` would serialize ``None`` as the literal string ``"None"`` in query
    strings, which Schwab endpoints reject.  Stripping ``None`` values here keeps
    all parameter-building code clean: callers can unconditionally include every
    optional key and let this function drop the unset ones.

    Args:
        params (dict): Raw parameter dictionary that may contain ``None`` values.

    Returns:
        dict: A new dictionary containing only key-value pairs where the value is
        not ``None``.
    """
    return {k: v for k, v in params.items() if v is not None}


def decode_schwab_dates(dct: dict) -> dict:
    """
    JSON ``object_hook`` that automatically converts Schwab date/time values to
    timezone-aware ``datetime`` objects during ``json.loads`` deserialization.

    Pass this function as ``object_hook`` to ``response.json()`` or
    ``json.loads(text, object_hook=decode_schwab_dates)`` to get native Python
    datetimes instead of raw strings and integers throughout the parsed payload.

    Two heuristics are applied to every key-value pair in each decoded JSON object:

    1. **ISO 8601 string detection** — if the key name contains ``"Date"`` or
       ``"Time"`` *and* the value is a string, it is parsed with
       ``datetime.fromisoformat()``.  Naive datetimes are localized to Eastern
       Time (``TIMEZONE_EST``).  Values that are not valid ISO strings are left
       unchanged.

    2. **Epoch-millisecond integer detection** — if the key name contains
       ``"Time"``, ``"Date"``, or is exactly ``"datetime"`` *and* the value is an
       integer greater than ``1_000_000_000_000`` (i.e. 13 digits, consistent with
       a millisecond timestamp after year 2001), it is converted to a UTC
       ``datetime`` and then localized to Eastern Time.

    Args:
        dct (dict): A single JSON object decoded by the standard JSON parser.
            Each nested object is processed independently by the hook.

    Returns:
        dict: The same dictionary with matching values replaced by
        ``datetime`` objects.

    Example:
        >>> import json
        >>> from schwab_api.utils import decode_schwab_dates
        >>> payload = '{"enteredTime": "2024-01-15T09:30:00.000Z", "datetime": 1741789287237}'
        >>> json.loads(payload, object_hook=decode_schwab_dates)
        {'enteredTime': datetime.datetime(2024, 1, 15, 9, 30, tzinfo=<...>),
         'datetime': datetime.datetime(2026, 3, 12, 14, 1, 27, tzinfo=<...>)}
    """
    for k, v in dct.items():
        if isinstance(v, str):
            if "Date" in k or "Time" in k:
                try:
                    dt = datetime.datetime.fromisoformat(v)
                    if dt.tzinfo is None:
                        dt = TIMEZONE_EST.localize(dt)
                    dct[k] = dt
                except ValueError:
                    pass
        elif isinstance(v, int):
            # Schwab uses 13-digit Unix timestamps (milliseconds)
            if ("Time" in k or "Date" in k or k == "datetime") and v > 1000000000000:
                try:
                    dct[k] = datetime.datetime.fromtimestamp(
                        v // 1000, datetime.timezone.utc
                    ).astimezone(TIMEZONE_EST)
                except (ValueError, TypeError, OSError):
                    pass
    return dct


def parse_price_history_to_df(history_json: dict) -> Any:
    """
    Convert a Schwab ``price_history`` JSON response into a Pandas OHLCV DataFrame.

    The raw Schwab response contains a ``"candles"`` list where each element is a
    dict with lowercase field names and a ``"datetime"`` key that holds a Unix
    epoch-millisecond timestamp.  This function normalises the data into a
    DataFrame whose index is a timezone-aware ``datetime`` in Eastern Time and
    whose columns follow the ``Open / High / Low / Close / Volume`` title-case
    convention used by libraries such as ``yfinance`` and ``mplfinance``.

    Args:
        history_json (dict): Parsed JSON body from ``client.price_history().json()``.
            Expected to have a ``"candles"`` key containing a list of OHLCV dicts.

    Returns:
        pandas.DataFrame: Indexed by ``Date`` (timezone-aware, Eastern Time) with
        columns ``Open``, ``High``, ``Low``, ``Close``, ``Volume``.
        Returns an empty ``DataFrame`` if ``"candles"`` is absent or empty.

    Example:
        >>> resp = client.price_history("AAPL", frequencyType="daily", period=1)
        >>> df = parse_price_history_to_df(resp.json())
        >>> print(df.tail())
                                  Open    High     Low   Close    Volume
        Date
        2024-01-12 16:00:00-05:00  185.4  186.2  184.9  185.9  54321000
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "pandas is required for this function. Install it using 'pip install pandas'."
        )

    candles = history_json.get("candles", [])
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["datetime"], unit="ms", utc=True).dt.tz_convert(
            TIMEZONE_EST
        )
        df.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            },
            inplace=True,
        )
        df.set_index("Date", inplace=True)
        if "datetime" in df.columns:
            df.drop(columns=["datetime"], inplace=True)

    return df


def parse_option_chain_to_df(
    option_chains_json: dict, evaluation_date: datetime.date | None = None
) -> Any:
    """
    Convert a Schwab ``option_chains`` JSON response into a flat Pandas DataFrame.

    The raw Schwab option chain is a nested structure keyed by expiry date and
    strike price.  This function flattens it into a single DataFrame with one row
    per option contract, adding derived columns (``is_put``, ``option_price``,
    ``days_to_expiration``) and preserving all key Greeks.

    Args:
        option_chains_json (dict): Parsed JSON body from ``client.option_chains().json()``.
            Must contain ``"callExpDateMap"``, ``"putExpDateMap"``, ``"underlyingPrice"``,
            and ``"symbol"`` keys as returned by the Schwab market-data endpoint.
        evaluation_date (datetime.date | None): Reference date used to compute
            ``days_to_expiration``.  Defaults to ``datetime.date.today()``.  Pass an
            explicit date for back-testing or reproducible unit tests.

    Returns:
        pandas.DataFrame: One row per option contract.  Index is ``symbol`` (the
        Schwab option symbol string, e.g. ``"AAPL  240809C00150000"``).

        Columns:

        * ``ticker`` (str) — underlying symbol (e.g. ``"AAPL"``)
        * ``stock_price`` (float) — underlying price at the time of the API call
        * ``expiration_date`` (datetime.date) — option expiry date
        * ``days_to_expiration`` (int) — calendar days from ``evaluation_date`` to expiry
        * ``is_put`` (bool) — ``True`` for PUT, ``False`` for CALL
        * ``strike_price`` (float) — option strike price
        * ``bid`` (float) — current bid price
        * ``ask`` (float) — current ask price
        * ``last`` (float) — last traded price
        * ``mark`` (float) — mark price as reported by Schwab (typically mid or exchange mark)
        * ``option_price`` (float) — computed mid-price: ``(bid + ask) / 2``
        * ``delta`` (float) — signed delta (negative for puts, positive for calls)
        * ``gamma`` (float) — gamma (always non-negative)
        * ``theta`` (float) — theta per day (typically negative)
        * ``vega`` (float) — vega per 1 % change in IV
        * ``rho`` (float) — rho per 1 % change in interest rate
        * ``volatility`` (float) — implied volatility as a decimal (e.g. 0.25 = 25 %)
        * ``totalVolume`` (int) — total contracts traded today
        * ``openInterest`` (int) — total open contracts
        * ``inTheMoney`` (bool) — ``True`` if the option is currently in the money

        Returns an empty ``DataFrame`` if both ``callExpDateMap`` and ``putExpDateMap``
        are absent or empty.

    Notes:
        ``option_price`` is computed as ``(bid + ask) / 2`` regardless of the
        ``mark`` field, ensuring consistent mid-price semantics for MFIV and
        screening calculations even when the market is closed and Schwab's mark
        deviates from the true mid.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "pandas is required for this function. Install it using 'pip install pandas'."
        )

    evaluation_date = evaluation_date or datetime.date.today()
    underlying_price = option_chains_json.get("underlyingPrice")
    symbol = option_chains_json.get("symbol")

    call_chains = option_chains_json.get("callExpDateMap", {})
    put_chains = option_chains_json.get("putExpDateMap", {})

    columns = [
        "symbol",
        "ticker",
        "stock_price",
        "expiration_date",
        "days_to_expiration",
        "is_put",
        "strike_price",
        "bid",
        "ask",
        "last",
        "mark",
        "option_price",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
        "volatility",
        "totalVolume",
        "openInterest",
        "inTheMoney",
    ]

    chain_data = []
    for opt_type_str, chains in [
        ("CALL", call_chains),
        ("PUT", put_chains),
    ]:
        for exp_date_key, strikes in chains.items():
            parts = exp_date_key.split(":")
            exp_date_str = parts[0]
            exp_date = datetime.datetime.strptime(exp_date_str, "%Y-%m-%d").date()
            dte = (exp_date - evaluation_date).days

            for strike_key, option_list in strikes.items():
                for opt in option_list:
                    bid = opt.get("bid", 0.0)
                    ask = opt.get("ask", 0.0)

                    data = {
                        "symbol": opt.get("symbol"),
                        "ticker": symbol,
                        "stock_price": underlying_price,
                        "expiration_date": exp_date,
                        "days_to_expiration": dte,
                        "is_put": opt_type_str == "PUT",
                        "strike_price": float(strike_key),
                        "bid": bid,
                        "ask": ask,
                        "last": opt.get("last", 0.0),
                        "mark": opt.get("mark", 0.0),
                        "option_price": (bid + ask) / 2.0,  # Mid price
                        "delta": opt.get("delta", 0.0),
                        "gamma": opt.get("gamma", 0.0),
                        "theta": opt.get("theta", 0.0),
                        "vega": opt.get("vega", 0.0),
                        "rho": opt.get("rho", 0.0),
                        "volatility": opt.get("volatility", 0.0),
                        "totalVolume": opt.get("totalVolume", 0),
                        "openInterest": opt.get("openInterest", 0),
                        "inTheMoney": opt.get("inTheMoney", False),
                    }
                    chain_data.append(data)

    df = pd.DataFrame(chain_data, columns=columns)
    if not df.empty:
        df.set_index("symbol", inplace=True)

    return df


def extract_positions(account_details_json: list, format: str = "dict") -> dict:
    """
    Flatten a multi-account ``account_details_all`` response into a symbol-keyed
    position dictionary.

    Iterates over every account in the response, collects all positions, and groups
    them by symbol then by account number.  This is the canonical way to get a
    consolidated view of holdings across all linked accounts.

    Args:
        account_details_json (list): Parsed JSON body from
            ``client.account_details_all(fields="positions").json()``.  Each element
            is one account's ``securitiesAccount`` wrapper.
        format (str): Output format for each per-account position entry.

            * ``"dict"`` (default) — a dict with keys:
              ``longQuantity``, ``shortQuantity``, ``averagePrice``,
              ``settledLongQuantity``, ``settledShortQuantity``,
              ``marketValue``, ``assetType``.
            * ``"tuple"`` — a 5-tuple
              ``(longQuantity, shortQuantity, averagePrice,
              settledLongQuantity, settledShortQuantity)``.
              Omits ``marketValue`` and ``assetType``; useful when only
              quantities are needed and minimal memory allocation matters.

    Returns:
        dict: Nested structure ``Dict[symbol, Dict[account_number, position_data]]``
        where ``account_number`` is the string account number from the API response
        and ``position_data`` is either a dict or a 5-tuple depending on ``format``.

        Returns an empty dict if ``account_details_json`` is empty or no positions
        are present.

    Notes:
        This function replaces positions wholesale on every call — closed positions
        from a previous call do not linger.  Callers that cache the result must
        refresh by calling this function again rather than mutating the returned dict.

    Example:
        >>> details = client.account_details_all(fields="positions").json()
        >>> positions = extract_positions(details, format="dict")
        >>> aapl = positions.get("AAPL", {})
        >>> for acct, pos in aapl.items():
        ...     print(acct, pos["longQuantity"], pos["marketValue"])
    """
    positions: dict[str, dict[str, Any]] = {}
    for account in account_details_json:
        security_account = account.get("securitiesAccount", {})
        account_number = security_account.get("accountNumber")
        if not account_number:
            continue

        account_positions = security_account.get("positions", [])
        for position in account_positions:
            instrument = position.get("instrument", {})
            symbol = instrument.get("symbol")
            if not symbol:
                continue

            if symbol not in positions:
                positions[symbol] = {}

            if format == "tuple":
                positions[symbol][account_number] = (
                    position.get("longQuantity", 0.0),
                    position.get("shortQuantity", 0.0),
                    position.get("averagePrice", 0.0),
                    position.get("settledLongQuantity", 0.0),
                    position.get("settledShortQuantity", 0.0),
                )
            else:
                positions[symbol][account_number] = {
                    "longQuantity": position.get("longQuantity", 0.0),
                    "shortQuantity": position.get("shortQuantity", 0.0),
                    "averagePrice": position.get("averagePrice", 0.0),
                    "settledLongQuantity": position.get("settledLongQuantity", 0.0),
                    "settledShortQuantity": position.get("settledShortQuantity", 0.0),
                    "marketValue": position.get("marketValue", 0.0),
                    "assetType": instrument.get("assetType", "UNKNOWN"),
                }

    return positions


def parse_schwab_equity_position(pos: dict, instrument: dict) -> dict:
    """
    Normalise a single raw Schwab equity position into a standard flat dict.

    Computes the current price-per-share from ``marketValue`` and the net quantity
    so that the caller does not need to handle the signed-quantity arithmetic.

    Args:
        pos (dict): Raw position dict from ``securitiesAccount.positions[]``
            as returned by the Schwab account-details endpoints.  Expected keys:
            ``longQuantity``, ``shortQuantity``, ``averagePrice``, ``marketValue``.
        instrument (dict): The ``instrument`` sub-dict from the same position entry.
            Expected keys: ``symbol``.

    Returns:
        dict: Normalised equity position with keys:

        * ``ticker`` (str) — equity symbol
        * ``quantity`` (float) — signed net quantity; positive = long, negative = short
        * ``average_price`` (float) — average cost basis per share
        * ``current_price`` (float) — current market price per share derived from
          ``abs(marketValue) / abs(net_quantity)``; ``0.0`` if quantity is zero
    """
    qty = abs(pos.get("longQuantity", 0) - pos.get("shortQuantity", 0))
    return {
        "ticker": instrument.get("symbol"),
        "quantity": pos.get("longQuantity", 0) - pos.get("shortQuantity", 0),
        "average_price": pos.get("averagePrice", 0.0),
        "current_price": abs(pos.get("marketValue", 0.0) / (qty if qty != 0 else 1)),
    }


def parse_schwab_option_symbol(symbol: str) -> dict:
    """
    Decode a Schwab option symbol into its component parts.

    Schwab encodes all option contract details into a fixed-width 21-character
    symbol string with the format::

        RRRRRR YYMMDD S WWWWWDDD

    Where:

    * ``RRRRRR`` — underlying ticker, left-aligned, padded to 6 characters with spaces
    * ``YYMMDD`` — expiration date (2-digit year, month, day)
    * ``S`` — option type: ``C`` for call, ``P`` for put
    * ``WWWWWDDD`` — strike price × 1000, zero-padded to 8 digits
      (e.g. strike 150.0 → ``00150000``, strike 0.5 → ``00000500``)

    Examples::

        "AAPL  240809C00150000"  →  expiry=2024-08-09, is_put=False, strike=150.00
        "RDDT  240719P00050500"  →  expiry=2024-07-19, is_put=True,  strike=50.50
        "GOOG  260327C00287500"  →  expiry=2026-03-27, is_put=False, strike=287.50

    Args:
        symbol (str): Full Schwab option symbol string (21 characters).

    Returns:
        dict: Decoded option components:

        * ``expiration_date`` (datetime.date) — parsed expiry date; falls back to
          ``datetime.date.today()`` if the date string is malformed
        * ``is_put`` (bool) — ``True`` for put, ``False`` for call
        * ``strike_price`` (float) — strike price in dollars; ``0.0`` on parse error

    Notes:
        The function always returns a dict (never raises).  Callers that need to
        detect malformed symbols should check whether ``strike_price`` is ``0.0``
        or ``expiration_date`` equals today.
    """
    option_part = symbol[-15:]

    exp_date_str = option_part[:6]
    opt_type_str = option_part[6:7]  # 'P' or 'C'
    strike_str = option_part[7:]

    try:
        exp_date = datetime.datetime.strptime(exp_date_str, "%y%m%d").date()
    except ValueError:
        exp_date = datetime.date.today()

    try:
        strike = int(strike_str) / 1000.0
    except ValueError:
        strike = 0.0

    return {
        "expiration_date": exp_date,
        "is_put": opt_type_str == "P",
        "strike_price": strike,
    }


def parse_schwab_option_position(
    pos: dict, instrument: dict, evaluation_date: datetime.date | None = None
) -> dict | None:
    """
    Normalise a raw Schwab option position into a standard flat dict with P&L.

    Combines symbol decoding (via ``parse_schwab_option_symbol``) with live
    position data to produce a single dict suitable for DataFrame construction
    and algorithmic analysis.

    P&L semantics:

    * **Long position** (``quantity > 0``): profit is positive when current price
      exceeds the average purchase price.
    * **Short position** (``quantity < 0``): profit is positive when current price
      is *below* the average sale price (the premium was sold for more than it now
      costs to buy back).

    ``profit_percentage`` is calculated as ``(profit_per_share / average_price) * 100``
    and represents the percentage of the original premium that has been captured
    (for shorts) or gained (for longs).

    Args:
        pos (dict): Raw position dict from ``securitiesAccount.positions[]``.
            Expected keys: ``longQuantity``, ``shortQuantity``, ``averagePrice``,
            ``marketValue``.
        instrument (dict): The ``instrument`` sub-dict from the same position entry.
            Expected keys: ``symbol`` (full Schwab option symbol), ``underlyingSymbol``.
        evaluation_date (datetime.date | None): Reference date for DTE calculation.
            Defaults to ``datetime.date.today()``.

    Returns:
        dict | None: Normalised option position, or ``None`` if ``symbol`` is missing
        or empty.  Keys:

        * ``symbol`` (str) — full Schwab option symbol
        * ``ticker`` (str) — underlying equity symbol
        * ``is_put`` (bool) — ``True`` for put
        * ``expiration_date`` (datetime.date) — option expiry
        * ``strike_price`` (float) — option strike
        * ``quantity`` (float) — signed net quantity (negative = short)
        * ``average_price`` (float) — average cost/sale price per share (not per contract)
        * ``current_price`` (float) — current market price per share derived from
          ``abs(marketValue) / (abs(quantity) * OPTION_CONTRACT_SIZE)``
        * ``profit`` (float) — total dollar P&L:
          ``profit_per_share * OPTION_CONTRACT_SIZE * abs(quantity)``
        * ``profit_percentage`` (float) — percentage of premium captured or gained;
          ``0.0`` if ``average_price`` is zero
        * ``days_to_expiration`` (int) — calendar days from ``evaluation_date`` to expiry
    """
    symbol = str(instrument.get("symbol", ""))
    if not symbol:
        return None

    ticker = instrument.get("underlyingSymbol")
    evaluation_date = evaluation_date or datetime.date.today()

    parsed = parse_schwab_option_symbol(symbol)
    exp_date = parsed["expiration_date"]
    is_put = parsed["is_put"]
    strike = parsed["strike_price"]

    qty = pos.get("longQuantity", 0) - pos.get("shortQuantity", 0)
    avg_price = pos.get("averagePrice", 0.0)
    market_val = pos.get("marketValue", 0.0)

    # Current option price
    opt_price = 0.0
    if qty != 0:
        opt_price = abs(market_val / (qty * OPTION_CONTRACT_SIZE))

    profit = opt_price - avg_price if qty > 0 else avg_price - opt_price

    return {
        "symbol": symbol,
        "ticker": ticker,
        "is_put": is_put,
        "expiration_date": exp_date,
        "strike_price": strike,
        "quantity": qty,
        "average_price": avg_price,
        "current_price": opt_price,
        "profit": profit * OPTION_CONTRACT_SIZE * abs(qty),
        "profit_percentage": ((profit / avg_price) * 100 if avg_price > 0 else 0.0),
        "days_to_expiration": (exp_date - evaluation_date).days,
    }


class UnsuccessfulOrderException(ValueError):
    pass


class AccountHashMismatchException(ValueError):
    pass


def get_last_complete_trading_day(tz: Any = TIMEZONE_EST) -> datetime.date:
    """
    Return the date of the most recently *completed* US equity trading session.

    A trading day is considered complete once the market close at 4:00 PM Eastern
    has passed.  This function uses 5:00 PM as a conservative cutoff to allow
    time for after-hours data to settle.

    Rules applied in order:

    1. If the current local time (in ``tz``) is before 5:00 PM, roll back one
       calendar day (today's session has not yet closed).
    2. If the resulting date is a Saturday, roll back one more day to Friday.
    3. If the resulting date is a Sunday, roll back two days to Friday.

    Args:
        tz: Timezone to use for determining the current time of day.
            Defaults to ``TIMEZONE_EST`` (``America/New_York``).

    Returns:
        datetime.date: Date of the last complete trading session.

    Notes:
        **Market holidays are not accounted for.**  On the trading day immediately
        following a holiday (e.g. the Tuesday after Memorial Day Monday), this
        function will return the holiday date, which has no trading data.
        Callers that need holiday-aware logic must apply their own calendar check.
    """
    now = datetime.datetime.now(tz)

    # If before 5 PM, consider the current trading day incomplete
    if now.hour < 17:
        now -= datetime.timedelta(days=1)

    # Roll back weekends to Friday
    if now.weekday() == 5:  # Saturday
        now -= datetime.timedelta(days=1)
    elif now.weekday() == 6:  # Sunday
        now -= datetime.timedelta(days=2)

    return now.date()


def parse_options_expiration_to_df(expiration_json: dict) -> Any:
    """
    Convert a Schwab option expiration chain response into a Pandas DataFrame.

    The ``/marketdata/v1/expirationchain`` endpoint returns a list of available
    expiration dates for a given underlying, including their type (weekly, monthly,
    quarterly, LEAPS), settlement style, and whether they are standard expirations.
    This function parses that list into a flat DataFrame for easy filtering.

    Args:
        expiration_json (dict): Parsed JSON body from
            ``client.option_expiration_chain(symbol).json()``.
            Expected to have an ``"expirationList"`` key containing a list of
            expiration-date entries, each with ``"expirationDate"`` (``"YYYY-MM-DD"``),
            ``"expirationType"``, ``"settlementType"``, and ``"standard"`` fields.

    Returns:
        pandas.DataFrame: One row per expiration date.  Columns:

        * ``Date`` (datetime, timezone-aware EST) — expiration date localized to
          Eastern Time (midnight on the expiry date)
        * ``Type`` (str) — expiration type code returned by Schwab
          (e.g. ``"R"`` for regular monthly, ``"W"`` for weekly, ``"Q"`` for quarterly)
        * ``Settlement`` (str) — settlement style (e.g. ``"P"`` for PM-settled,
          ``"A"`` for AM-settled)
        * ``Standard`` (bool) — ``True`` for standard (third-Friday monthly) expirations

        Returns an empty DataFrame (with the correct columns) if
        ``"expirationList"`` is absent or all entries have unparseable dates.

    Example:
        >>> exp = client.option_expiration_chain("AAPL").json()
        >>> df = parse_options_expiration_to_df(exp)
        >>> monthlies = df[df["Standard"] == True]
        >>> print(monthlies[["Date", "Type"]].head())
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "pandas is required for this function. Install it using 'pip install pandas'."
        )

    expiration_list = expiration_json.get("expirationList", [])
    data = []
    for exp in expiration_list:
        try:
            exp_date = TIMEZONE_EST.localize(
                datetime.datetime.strptime(exp.get("expirationDate"), "%Y-%m-%d")
            )
        except (ValueError, TypeError):
            continue

        data.append(
            {
                "Date": exp_date,
                "Type": exp.get("expirationType", ""),
                "Settlement": exp.get("settlementType", ""),
                "Standard": exp.get("standard", False),
            }
        )

    df = pd.DataFrame(data, columns=["Date", "Type", "Settlement", "Standard"])
    return df
