import datetime
from enum import Enum
from typing import Any

from pytz import timezone

TIMEZONE_EST = timezone("America/New_York")


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
    """Convert Yahoo Finance ticker format to Schwab ticker format."""
    if not t:
        return t
    if t[0] == "^":
        return "$" + t[1:]
    if len(t) < 3:
        return t
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


def format_list(l: Any | None) -> str | None:
    """Convert python list or iterable to comma-separated string."""
    if l is None:
        return None
    elif isinstance(l, str):
        return l
    elif hasattr(l, "__iter__"):
        return ",".join(map(str, l))
    else:
        return str(l)


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


class UnsuccessfulOrderException(ValueError):
    pass


class AccountHashMismatchException(ValueError):
    pass
