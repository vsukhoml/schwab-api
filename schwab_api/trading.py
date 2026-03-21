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
        Filter the option chain with multiple simultaneous criteria.

        All filters are applied with logical AND.  Delta comparisons use the
        **absolute value** of delta so the same ``min_delta``/``max_delta`` bounds
        work identically for puts (negative delta) and calls (positive delta).

        Args:
            is_put (bool | None): ``True`` → puts only, ``False`` → calls only,
                ``None`` (default) → both.
            min_dte (int | None): Minimum days to expiration (inclusive).
            max_dte (int | None): Maximum days to expiration (inclusive).
            min_delta (float | None): Minimum absolute delta (e.g. ``0.15``).
            max_delta (float | None): Maximum absolute delta (e.g. ``0.30``).
            min_open_interest (int): Minimum open interest. 0 = no filter.
            min_volume (int): Minimum daily contract volume. 0 = no filter.
            min_option_price (float): Minimum mid-price ``(bid+ask)/2``. 0.0 = no filter.
            min_premium_percentage (float): Minimum ratio of option_price to strike_price
                (e.g. ``0.01`` = 1% of strike). 0.0 = no filter.
            max_bid_ask_spread (float | None): Maximum allowable ``ask - bid`` spread.
                ``None`` = no filter.

        Returns:
            pandas.DataFrame: Filtered rows sorted by
                ``(expiration_date ASC, option_price DESC, delta ASC)``.
                Returns the original (empty) DataFrame if ``self.df`` is empty.

                Columns mirror the output of ``parse_option_chain_to_df``:
                ``expiration_date``, ``days_to_expiration``, ``stock_price``,
                ``strike_price``, ``is_put``, ``delta``, ``gamma``, ``theta``,
                ``vega``, ``bid``, ``ask``, ``option_price``, ``openInterest``,
                ``totalVolume``.
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

    def get_iron_condors(
        self,
        min_dte: int = 21,
        max_dte: int = 45,
        min_short_delta: float = 0.15,
        max_short_delta: float = 0.30,
        min_wing_width: float = 1.0,
        max_wing_width: Optional[float] = None,
        min_credit: float = 0.0,
        min_credit_to_width_ratio: float = 0.0,
        min_open_interest: int = 0,
        max_bid_ask_spread: Optional[float] = None,
        symmetric_wings: bool = False,
    ) -> Any:
        """
        Finds Iron Condor candidates by combining short put spreads with short call spreads.

        An Iron Condor consists of four legs on the same expiry:
            Long put (protection) < Short put < underlying < Short call < Long call (protection)

        The method enumerates all valid put-spread / call-spread combinations, computes
        per-condor metrics, and returns them sorted by ``credit_to_width_ratio`` descending
        so the best risk/reward candidates appear first.

        Args:
            min_dte (int): Minimum days to expiration per leg. Defaults to 21.
            max_dte (int): Maximum days to expiration per leg. Defaults to 45.
            min_short_delta (float): Minimum absolute delta for the short legs. Defaults to 0.15.
            max_short_delta (float): Maximum absolute delta for the short legs. Defaults to 0.30.
            min_wing_width (float): Minimum width (in dollars) for each spread wing.
                Defaults to 1.0.
            max_wing_width (float | None): Maximum wing width. Defaults to None (no limit).
            min_credit (float): Minimum total net credit to include a condor. Defaults to 0.0.
            min_credit_to_width_ratio (float): Minimum ratio of net_credit to the narrower wing
                width (e.g. 0.25 = 25% credit of width). Defaults to 0.0.
            min_open_interest (int): Minimum open interest for every leg. Defaults to 0.
            max_bid_ask_spread (float | None): Maximum bid-ask spread per leg. Defaults to None.
            symmetric_wings (bool): If True, only return condors where put_width == call_width.
                Defaults to False.

        Returns:
            pandas.DataFrame: One row per Iron Condor candidate.  Columns:

            * ``expiration_date``, ``days_to_expiration``, ``stock_price``
            * ``short_put_symbol``, ``short_put_strike``, ``short_put_delta``, ``short_put_mark``
            * ``long_put_symbol``, ``long_put_strike``, ``long_put_mark``
            * ``put_width``
            * ``short_call_symbol``, ``short_call_strike``, ``short_call_delta``, ``short_call_mark``
            * ``long_call_symbol``, ``long_call_strike``, ``long_call_mark``
            * ``call_width``
            * ``net_credit`` — total premium collected (short marks - long marks)
            * ``max_loss`` — max(put_width, call_width) - net_credit
            * ``credit_to_width_ratio`` — net_credit / min(put_width, call_width)
            * ``break_even_lower`` — short_put_strike - net_credit
            * ``break_even_upper`` — short_call_strike + net_credit

            Returns an empty DataFrame when no candidates satisfy the filters.
        """
        import pandas as pd

        if self.df.empty:
            return pd.DataFrame()

        # --- Per-leg quality gate ---
        mask = (self.df["days_to_expiration"] >= min_dte) & (
            self.df["days_to_expiration"] <= max_dte
        )
        if min_open_interest > 0:
            mask &= self.df["openInterest"] >= min_open_interest
        if max_bid_ask_spread is not None:
            mask &= (self.df["ask"] - self.df["bid"]) <= max_bid_ask_spread

        # Reset index so 'symbol' is a plain column
        df = self.df[mask].reset_index()[
            [
                c
                for c in [
                    "symbol",
                    "expiration_date",
                    "days_to_expiration",
                    "stock_price",
                    "strike_price",
                    "is_put",
                    "delta",
                    "option_price",
                ]
                if c in self.df.reset_index().columns
            ]
        ]

        if df.empty:
            return pd.DataFrame()

        delta_abs = df["delta"].abs()
        short_mask = (delta_abs >= min_short_delta) & (delta_abs <= max_short_delta)

        # --- Short put legs ---
        sp = df[df["is_put"] & short_mask][
            [
                "symbol",
                "expiration_date",
                "days_to_expiration",
                "stock_price",
                "strike_price",
                "delta",
                "option_price",
            ]
        ].rename(
            columns={
                "symbol": "short_put_symbol",
                "strike_price": "short_put_strike",
                "delta": "short_put_delta",
                "option_price": "short_put_mark",
            }
        )

        # --- Long put legs (all puts; filtered by strike after merge) ---
        lp = df[df["is_put"]][
            ["symbol", "expiration_date", "strike_price", "option_price"]
        ].rename(
            columns={
                "symbol": "long_put_symbol",
                "strike_price": "long_put_strike",
                "option_price": "long_put_mark",
            }
        )

        # --- Short call legs ---
        sc = df[~df["is_put"] & short_mask][
            [
                "symbol",
                "expiration_date",
                "days_to_expiration",
                "stock_price",
                "strike_price",
                "delta",
                "option_price",
            ]
        ].rename(
            columns={
                "symbol": "short_call_symbol",
                "strike_price": "short_call_strike",
                "delta": "short_call_delta",
                "option_price": "short_call_mark",
            }
        )

        # --- Long call legs (all calls; filtered by strike after merge) ---
        lc = df[~df["is_put"]][
            ["symbol", "expiration_date", "strike_price", "option_price"]
        ].rename(
            columns={
                "symbol": "long_call_symbol",
                "strike_price": "long_call_strike",
                "option_price": "long_call_mark",
            }
        )

        if sp.empty or lp.empty or sc.empty or lc.empty:
            return pd.DataFrame()

        # --- Build put credit spreads ---
        put_spreads = sp.merge(lp, on="expiration_date")
        put_spreads = put_spreads[
            put_spreads["long_put_strike"] < put_spreads["short_put_strike"]
        ]
        put_spreads["put_width"] = (
            put_spreads["short_put_strike"] - put_spreads["long_put_strike"]
        )
        put_spreads = put_spreads[put_spreads["put_width"] >= min_wing_width]
        if max_wing_width is not None:
            put_spreads = put_spreads[put_spreads["put_width"] <= max_wing_width]

        # --- Build call credit spreads ---
        call_spreads = sc.merge(lc, on="expiration_date")
        call_spreads = call_spreads[
            call_spreads["long_call_strike"] > call_spreads["short_call_strike"]
        ]
        call_spreads["call_width"] = (
            call_spreads["long_call_strike"] - call_spreads["short_call_strike"]
        )
        call_spreads = call_spreads[call_spreads["call_width"] >= min_wing_width]
        if max_wing_width is not None:
            call_spreads = call_spreads[call_spreads["call_width"] <= max_wing_width]

        if put_spreads.empty or call_spreads.empty:
            return pd.DataFrame()

        # Keep only columns needed for the final join
        put_spreads = put_spreads[
            [
                "expiration_date",
                "days_to_expiration",
                "stock_price",
                "short_put_symbol",
                "short_put_strike",
                "short_put_delta",
                "short_put_mark",
                "long_put_symbol",
                "long_put_strike",
                "long_put_mark",
                "put_width",
            ]
        ]
        call_spreads = call_spreads[
            [
                "expiration_date",
                "short_call_symbol",
                "short_call_strike",
                "short_call_delta",
                "short_call_mark",
                "long_call_symbol",
                "long_call_strike",
                "long_call_mark",
                "call_width",
            ]
        ]

        # --- Combine into Iron Condors (same expiry, no leg overlap) ---
        ic = put_spreads.merge(call_spreads, on="expiration_date")
        ic = ic[ic["short_call_strike"] > ic["short_put_strike"]]

        if ic.empty:
            return pd.DataFrame()

        # --- Compute condor-level metrics ---
        ic["net_credit"] = (
            ic["short_put_mark"]
            + ic["short_call_mark"]
            - ic["long_put_mark"]
            - ic["long_call_mark"]
        )
        min_width = ic[["put_width", "call_width"]].min(axis=1)
        max_width = ic[["put_width", "call_width"]].max(axis=1)
        ic["max_loss"] = max_width - ic["net_credit"]
        ic["credit_to_width_ratio"] = ic["net_credit"] / min_width
        ic["break_even_lower"] = ic["short_put_strike"] - ic["net_credit"]
        ic["break_even_upper"] = ic["short_call_strike"] + ic["net_credit"]

        # --- Condor-level filters ---
        if min_credit > 0.0:
            ic = ic[ic["net_credit"] >= min_credit]
        if min_credit_to_width_ratio > 0.0:
            ic = ic[ic["credit_to_width_ratio"] >= min_credit_to_width_ratio]
        if symmetric_wings:
            ic = ic[(ic["put_width"] - ic["call_width"]).abs() < 0.01]

        if ic.empty:
            return pd.DataFrame()

        return ic.sort_values(
            by=["expiration_date", "credit_to_width_ratio"],
            ascending=[True, False],
        ).reset_index(drop=True)

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
        Returns the parsed option positions as a Pandas DataFrame indexed by symbol.

        Returns:
            pandas.DataFrame: One row per option position, indexed by the Schwab
                option symbol string.  Columns produced by ``parse_schwab_option_position``:

                * ``underlying_symbol`` — e.g. ``"GOOG"``
                * ``expiration_date`` — ISO date string ``"YYYY-MM-DD"``
                * ``strike_price`` — float
                * ``is_put`` — bool (True = put, False = call)
                * ``quantity`` — signed integer (negative = short)
                * ``average_price`` — premium received/paid per share (not per contract)
                * ``current_price`` — current mid-price per share
                * ``profit_percentage`` — realised P&L as a % of the initial premium:
                    ``(average_price - current_price) / average_price * 100`` for short,
                    ``(current_price - average_price) / average_price * 100`` for long
                * ``days_to_expiration`` — integer DTE from ``evaluation_date``

                Returns an empty DataFrame if no option positions were parsed.

        Raises:
            ImportError: If ``pandas`` is not installed.
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
        Identify short put positions that are at risk and may need rolling or closing.

        A position is flagged only when **both** criteria are met simultaneously:

        1. **DTE criterion** — ``days_to_expiration ≤ max_dte``: the put is close enough
           to expiry that there is limited time for the position to recover.
        2. **Loss criterion** — ``profit_percentage ≤ max_loss_percentage``: the position
           has moved against the seller by at least the specified percentage.  A negative
           value means a loss (e.g. ``-50.0`` means the option is now worth ≥ 2× the
           original premium, so the seller has lost 50% of potential max profit).

        Only short puts (``quantity < 0`` and ``is_put == True``) are considered.
        Long puts and short calls are ignored.

        Args:
            max_loss_percentage (float): Loss threshold as a percentage of the original
                premium received.  Must be ≤ 0 (e.g. ``-50.0`` = 50% loss).
                Defaults to -50.0.
            max_dte (int): Maximum days to expiration to consider. Defaults to 14.
                Positions with DTE > max_dte are excluded even if they show a large loss,
                because time value may still recover.

        Returns:
            list[dict]: Each dict is a position record as returned by
                ``parse_schwab_option_position``.  See ``to_df()`` for the field list.
                Returns an empty list when no positions meet both criteria.
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
        Identify option positions that have reached their profit target and should be closed.

        Applies to **all** option positions (calls and puts, long and short).
        ``profit_percentage`` is direction-aware:

        - **Short options** (qty < 0): profit = ``(average_price - current_price) / average_price * 100``
          A short option profits when the current price drops below the sold premium.
          50% profit means you can buy it back for half of what you collected.
        - **Long options** (qty > 0): profit = ``(current_price - average_price) / average_price * 100``
          A long option profits when the current price rises above cost basis.

        The standard Wheel / theta-decay strategy closes short options at 50% profit
        to eliminate the asymmetric risk of holding through expiration.

        Args:
            min_profit_percentage (float): Minimum ``profit_percentage`` to include a
                position in the result.  Defaults to 50.0 (50% of max profit captured).

        Returns:
            list[dict]: Each dict is a position record as returned by
                ``parse_schwab_option_position``.  See ``to_df()`` for the field list.
                Returns an empty list when no positions meet the threshold.
        """
        return [
            opt
            for opt in self.options
            if opt["profit_percentage"] >= min_profit_percentage
        ]
