import datetime
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OptionChainAnalyzer:
    """
    A utility class for analyzing option chains returned by the Schwab API.
    Requires pandas to be installed (`pip install schwab_api[pandas]`).

    Example:
        >>> chain_json = client.option_chains("AAPL").json()
        >>> analyzer = OptionChainAnalyzer(chain_json)
        >>> df = analyzer.get_put_candidates(min_dte=30, max_dte=45, max_delta=0.30)
    """

    def __init__(
        self,
        option_chains_json: Dict[str, Any],
        evaluation_date: Optional[datetime.date] = None,
    ):
        """
        Initializes the analyzer with the raw JSON payload from the Schwab Option Chains API.

        :param option_chains_json: The dictionary representing the option chain payload.
        :param evaluation_date: Optional date to compute Days To Expiration against. Defaults to today.
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for OptionChainAnalyzer. Install it using 'pip install pandas'."
            )

        self.option_chains_json = option_chains_json
        self.underlying_price = option_chains_json.get("underlyingPrice")
        self.symbol = option_chains_json.get("symbol")

        self.evaluation_date = evaluation_date or datetime.date.today()

        self.call_chains = option_chains_json.get("callExpDateMap", {})
        self.put_chains = option_chains_json.get("putExpDateMap", {})

        # Parse into DataFrame
        columns = [
            "symbol",
            "ticker",
            "stock_price",
            "expiration_date",
            "days_to_expiration",
            "option_type",
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
            "totalVolume",
            "openInterest",
            "inTheMoney",
        ]

        chain_data = []
        for opt_type_str, chains in [
            ("CALL", self.call_chains),
            ("PUT", self.put_chains),
        ]:
            for exp_date_key, strikes in chains.items():
                # exp_date_key format: "2025-04-25:29" (date:days_to_expiration)
                # However, the backend 'days_to_expiration' is relative to when the API was called,
                # not necessarily current execution time if caching/testing.
                parts = exp_date_key.split(":")
                exp_date_str = parts[0]
                exp_date = datetime.datetime.strptime(exp_date_str, "%Y-%m-%d").date()

                # Compute DTE dynamically based on evaluation date
                dte = (exp_date - self.evaluation_date).days

                for strike_key, option_list in strikes.items():
                    for opt in option_list:
                        bid = opt.get("bid", 0.0)
                        ask = opt.get("ask", 0.0)

                        data = {
                            "symbol": opt.get("symbol"),
                            "ticker": self.symbol,
                            "stock_price": self.underlying_price,
                            "expiration_date": exp_date,
                            "days_to_expiration": dte,
                            "option_type": opt_type_str,
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
                            "totalVolume": opt.get("totalVolume", 0),
                            "openInterest": opt.get("openInterest", 0),
                            "inTheMoney": opt.get("inTheMoney", False),
                        }
                        chain_data.append(data)

        self.df = pd.DataFrame(chain_data, columns=columns)
        if not self.df.empty:
            self.df.set_index("symbol", inplace=True)

    def filter_options(
        self,
        option_type: Optional[str] = None,
        min_dte: Optional[int] = None,
        max_dte: Optional[int] = None,
        min_delta: Optional[float] = None,
        max_delta: Optional[float] = None,
        min_open_interest: int = 0,
        min_volume: int = 0,
        min_option_price: float = 0.0,
        min_premium_percentage: float = 0.0,
        max_bid_ask_spread: Optional[float] = None,
    ) -> Any:
        """
        Filter the options chain based on various criteria to find ideal auto-trading candidates.

        :param option_type: String representing type, e.g. "CALL" or "PUT"
        :param min_dte: Minimum Days to Expiration
        :param max_dte: Maximum Days to Expiration
        :param min_delta: Minimum absolute Delta
        :param max_delta: Maximum absolute Delta
        :param min_open_interest: Minimum number of open contracts
        :param min_volume: Minimum contract trading volume
        :param min_option_price: Minimum mid-price of the option contract
        :param min_premium_percentage: Contract premium as a percentage of the strike price
        :param max_bid_ask_spread: Maximum distance between Bid and Ask
        :return: A Pandas DataFrame containing filtered contracts.
        """
        if self.df.empty:
            return self.df

        import pandas as pd

        mask = pd.Series(True, index=self.df.index)

        if option_type:
            mask &= self.df["option_type"] == option_type.upper()

        if min_dte is not None:
            mask &= self.df["days_to_expiration"] >= min_dte

        if max_dte is not None:
            mask &= self.df["days_to_expiration"] <= max_dte

        if min_delta is not None:
            # We check absolute value for delta (useful for puts where delta is negative)
            mask &= self.df["delta"].abs() >= min_delta

        if max_delta is not None:
            mask &= self.df["delta"].abs() <= max_delta

        if min_open_interest > 0:
            mask &= self.df["openInterest"] >= min_open_interest

        if min_volume > 0:
            mask &= self.df["totalVolume"] >= min_volume

        if min_option_price > 0.0:
            mask &= self.df["option_price"] >= min_option_price

        if min_premium_percentage > 0.0:
            # option_price / strike_price > percentage
            mask &= self.df["option_price"] > (
                self.df["strike_price"] * min_premium_percentage
            )

        if max_bid_ask_spread is not None:
            mask &= (self.df["ask"] - self.df["bid"]) <= max_bid_ask_spread

        filtered = self.df[mask].copy()

        # Sort by best candidates (expiration date, then option price, then delta)
        if not filtered.empty:
            filtered = filtered.sort_values(
                by=["expiration_date", "option_price", "delta"],
                ascending=[True, False, True],
            )

        return filtered

    def get_put_candidates(
        self,
        min_dte: int = 21,
        max_dte: int = 45,
        min_delta: float = 0.15,
        max_delta: float = 0.30,
        **kwargs,
    ) -> Any:
        """
        Helper to find cash-secured put candidates (the 'Wheel' strategy).

        :param min_dte: Minimum Days to Expiration. Defaults to 21.
        :param max_dte: Maximum Days to Expiration. Defaults to 45.
        :param min_delta: Minimum absolute Delta. Defaults to 0.15.
        :param max_delta: Maximum absolute Delta. Defaults to 0.30.
        :param kwargs: Additional filter parameters passed to `filter_options()`.
        :return: A Pandas DataFrame containing filtered put options.
        """
        return self.filter_options(
            option_type="PUT",
            min_dte=min_dte,
            max_dte=max_dte,
            min_delta=min_delta,
            max_delta=max_delta,
            **kwargs,
        )

    def get_call_candidates(
        self,
        min_dte: int = 21,
        max_dte: int = 45,
        min_delta: float = 0.15,
        max_delta: float = 0.30,
        **kwargs,
    ) -> Any:
        """
        Helper to find covered call candidates (the 'Wheel' strategy).

        :param min_dte: Minimum Days to Expiration. Defaults to 21.
        :param max_dte: Maximum Days to Expiration. Defaults to 45.
        :param min_delta: Minimum absolute Delta. Defaults to 0.15.
        :param max_delta: Maximum absolute Delta. Defaults to 0.30.
        :param kwargs: Additional filter parameters passed to `filter_options()`.
        :return: A Pandas DataFrame containing filtered call options.
        """
        return self.filter_options(
            option_type="CALL",
            min_dte=min_dte,
            max_dte=max_dte,
            min_delta=min_delta,
            max_delta=max_delta,
            **kwargs,
        )


class PositionAnalyzer:
    """
    Analyzes an account's positions to calculate Greeks, PnL, and theta decay targets.

    Example:
        >>> positions = client.account_details(account_hash, fields="positions").json()
        >>> analyzer = PositionAnalyzer(positions.get('securitiesAccount', {}).get('positions', []))
        >>> winners = analyzer.get_winning_options(min_profit_percentage=50.0)
    """

    def __init__(self, account_positions_json: List[Dict[str, Any]]):
        """
        Initializes the analyzer with the raw JSON payload of an account's positions.

        :param account_positions_json: The list of position dicts returned by the Schwab API.
        """
        self.raw_positions = account_positions_json

        self.options: List[Dict[str, Any]] = []
        self.equities: List[Dict[str, Any]] = []

        for pos in self.raw_positions:
            instrument = pos.get("instrument", {})
            asset_type = instrument.get("assetType")

            if asset_type == "OPTION":
                self._parse_option_position(pos, instrument)
            elif asset_type == "EQUITY":
                self._parse_equity_position(pos, instrument)

    def _parse_option_position(
        self, pos: Dict[str, Any], instrument: Dict[str, Any]
    ) -> None:
        symbol = str(instrument.get("symbol", ""))
        if not symbol:
            return

        ticker = instrument.get("underlyingSymbol")

        # Parse Schwab option symbol: "RDDT  240719P00050500"
        symbol_split = symbol.split(" ")
        option_part = symbol_split[-1] if len(symbol_split) > 0 else symbol

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

        qty = pos.get("longQuantity", 0) - pos.get("shortQuantity", 0)
        avg_price = pos.get("averagePrice", 0.0)
        market_val = pos.get("marketValue", 0.0)

        # Current option price
        opt_price = 0.0
        if qty != 0:
            opt_price = abs(market_val / (qty * 100))

        profit = opt_price - avg_price if qty > 0 else avg_price - opt_price

        self.options.append(
            {
                "symbol": symbol,
                "ticker": ticker,
                "option_type": "PUT" if opt_type_str == "P" else "CALL",
                "expiration_date": exp_date,
                "strike_price": strike,
                "quantity": qty,
                "average_price": avg_price,
                "current_price": opt_price,
                "profit": profit * 100 * abs(qty),
                "profit_percentage": (
                    (profit / avg_price) * 100 if avg_price > 0 else 0.0
                ),
                "days_to_expiration": (exp_date - datetime.date.today()).days,
            }
        )

    def _parse_equity_position(
        self, pos: Dict[str, Any], instrument: Dict[str, Any]
    ) -> None:
        self.equities.append(
            {
                "ticker": instrument.get("symbol"),
                "quantity": pos.get("longQuantity", 0) - pos.get("shortQuantity", 0),
                "average_price": pos.get("averagePrice", 0.0),
                "current_price": pos.get("marketValue", 0.0)
                / (pos.get("longQuantity", 0) or 1),
            }
        )

    def get_losing_short_puts(
        self, min_extrinsic_percentage: float = 0.005, max_dte: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Identify short puts that are in danger and might need rolling.

        :param min_extrinsic_percentage: Percentage of extrinsic value left before rolling (Placeholder).
        :param max_dte: Maximum Days to Expiration left before flagging the put. Defaults to 14.
        :return: A list of dicts describing the losing put positions.
        """
        candidates = []
        for opt in self.options:
            if opt["option_type"] == "PUT" and opt["quantity"] < 0:
                if opt["days_to_expiration"] <= max_dte:
                    candidates.append(opt)
        return candidates

    def get_winning_options(
        self, min_profit_percentage: float = 50.0
    ) -> List[Dict[str, Any]]:
        """
        Identify options that have reached the profit target and should be closed.

        :param min_profit_percentage: Minimum percentage profit threshold to trigger closing. Defaults to 50.0.
        :return: A list of dicts describing the winning option positions.
        """
        return [
            opt
            for opt in self.options
            if opt["profit_percentage"] >= min_profit_percentage
        ]
