import datetime
import logging
from typing import Any, Dict, List, Optional

from schwab_api.utils import parse_schwab_option_position, parse_schwab_equity_position

logger = logging.getLogger(__name__)


class OptionChainAnalyzer:
    """
    A utility class for analyzing option chains.
    Requires pandas to be installed (`pip install schwab_api[pandas]`).

    Example:
        >>> chain_json = client.option_chains("AAPL").json()
        >>> from schwab_api.utils import parse_option_chain_to_df
        >>> df_chain = parse_option_chain_to_df(chain_json)
        >>> analyzer = OptionChainAnalyzer(df_chain)
        >>> df = analyzer.get_put_candidates(min_dte=30, max_dte=45, max_delta=0.30)
    """

    def __init__(
        self,
        option_chain_df: Any,
    ):
        """
        Initializes the analyzer with the parsed Pandas DataFrame.

        :param option_chain_df: A Pandas DataFrame containing option chain data.
        """
        try:
            import pandas as pd  # noqa: F401
        except ImportError:
            raise ImportError(
                "pandas is required for OptionChainAnalyzer. Install it using 'pip install pandas'."
            )

        self.df = option_chain_df

    def filter_options(
        self,
        is_put: Optional[bool] = None,
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

        :param is_put: True to filter for PUTs, False to filter for CALLs. None returns both.
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

        if is_put is not None:
            mask &= self.df["is_put"] == is_put

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
            is_put=True,
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
            is_put=False,
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

    def __init__(
        self,
        account_positions_json: List[Dict[str, Any]],
        evaluation_date: Optional[datetime.date] = None,
    ):
        """
        Initializes the analyzer with the raw JSON payload of an account's positions.

        :param account_positions_json: The list of position dicts returned by the Schwab API.
        :param evaluation_date: The date to use for DTE calculations. Defaults to today.
        """
        self.raw_positions = account_positions_json
        self.evaluation_date = evaluation_date or datetime.date.today()

        self.options: List[Dict[str, Any]] = []
        self.equities: List[Dict[str, Any]] = []

        for pos in self.raw_positions:
            instrument = pos.get("instrument", {})
            asset_type = instrument.get("assetType")

            if asset_type == "OPTION":
                parsed_opt = parse_schwab_option_position(
                    pos, instrument, evaluation_date=self.evaluation_date
                )
                if parsed_opt:
                    self.options.append(parsed_opt)
            elif asset_type == "EQUITY":
                self.equities.append(parse_schwab_equity_position(pos, instrument))

    def to_df(self) -> Any:
        """
        Returns the parsed option positions as a Pandas DataFrame.
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for PositionAnalyzer.to_df(). Install it using 'pip install pandas'."
            )

        if not self.options:
            return pd.DataFrame()

        df = pd.DataFrame(self.options)
        if not df.empty:
            df.set_index("symbol", inplace=True)
        return df

    def get_losing_short_puts(
        self, max_loss_percentage: float = -50.0, max_dte: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Identify short puts that are in danger and might need rolling.

        :param max_loss_percentage: Percentage loss threshold before flagging the put (e.g., -50.0 means lost 50% of premium).
        :param max_dte: Maximum Days to Expiration left before flagging the put. Defaults to 14.
        :return: A list of dicts describing the losing put positions.
        """
        candidates = []
        for opt in self.options:
            if opt["is_put"] and opt["quantity"] < 0:
                if opt["days_to_expiration"] <= max_dte:
                    if opt.get("profit_percentage", 0.0) <= max_loss_percentage:
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
