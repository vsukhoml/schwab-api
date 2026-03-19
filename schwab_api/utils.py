import datetime
from enum import Enum
from typing import Any

from pytz import timezone

TIMEZONE_EST = timezone("America/New_York")
OPTION_CONTRACT_SIZE = 100


class TimeFormat(Enum):
    ISO_8601 = "ISO_8601"
    EPOCH = "EPOCH"
    EPOCH_MS = "EPOCH_MS"
    YYYY_MM_DD = "YYYY_MM_DD"


def time_convert(dt, fmt: TimeFormat = TimeFormat.ISO_8601) -> str | int | None:
    """
    Convert time to the correct format, passthrough if a string, preserve None if None for params parser
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
    Convert Yahoo Finance ticker format to Schwab ticker format.

    Examples:
    - 'BRK-B' -> 'BRK/B'
    - 'AAPL' -> 'AAPL'
    - '^DJI' -> '$DJI'
    - 'O-PB' -> 'O/PRB' (Preferred)
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
    """Convert python list or iterable to comma-separated string."""
    if lst is None:
        return None
    elif isinstance(lst, str):
        return lst
    elif hasattr(lst, "__iter__"):
        return ",".join(map(str, lst))
    else:
        return str(lst)


def parse_params(params: dict) -> dict:
    """Removes None values from dictionary."""
    return {k: v for k, v in params.items() if v is not None}


def decode_schwab_dates(dct: dict) -> dict:
    """
    JSON object_hook to automatically parse Schwab API date/time strings
    and UNIX millisecond timestamps into timezone-aware datetime objects.
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
    """Parse Schwab price history JSON response into a Pandas DataFrame."""
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
    Parse Schwab option chain JSON response into a Pandas DataFrame.

    Returns a DataFrame with the following format:
    - Index: symbol (str) - e.g. "AAPL  240809C00150000"
    - Columns:
        - ticker (str): Underlying symbol
        - stock_price (float): Underlying price at the time of the request
        - expiration_date (datetime.date): Expiration date of the option
        - days_to_expiration (int): DTE calculated against the evaluation_date
        - is_put (bool): True if the option is a PUT, False if CALL
        - strike_price (float): Strike price
        - bid (float): Bid price
        - ask (float): Ask price
        - last (float): Last traded price
        - mark (float): Mark price
        - option_price (float): Mid price ((bid + ask) / 2)
        - delta (float): Delta
        - gamma (float): Gamma
        - theta (float): Theta
        - vega (float): Vega
        - rho (float): Rho
        - totalVolume (int): Total volume
        - openInterest (int): Open interest
        - inTheMoney (bool): True if the option is in the money
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


def extract_positions(account_details_json: list) -> dict:
    """
    Parses a list of account details and extracts a consolidated dictionary of positions.
    Keys are symbols, values are dicts keyed by account_number mapping to position details.
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
    Parses a raw Schwab equity position dict into a generic dictionary.
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
    Parses a Schwab option symbol: "RDDT  240719P00050500"
    Returns a dict with 'expiration_date', 'is_put', and 'strike_price'.
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
    Parses a raw Schwab option position dict into a generic dictionary, calculating
    DTE, Greeks-related hints, and PnL.
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
