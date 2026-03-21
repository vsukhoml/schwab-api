import datetime
import logging
import math
from typing import Any, Optional

from schwab_api.utils import OPTION_CONTRACT_SIZE

logger = logging.getLogger(__name__)


class BlackScholesPricer:
    """
    Standalone Black-Scholes-Merton (BSM) options pricing calculator for theoretical Greeks.

    Implements the continuous dividend yield extension of Black-Scholes (Merton 1973).
    All Greeks are computed from precomputed ``_d1`` / ``_d2`` values to avoid redundant
    calculations when calling multiple Greek methods on the same instance.

    Requires ``scipy`` (``pip install scipy`` or ``pip install schwab_api[scipy]``).

    Example::

        from schwab_api.math import BlackScholesPricer
        import datetime

        pricer = BlackScholesPricer(
            stock_price=450.0, strike_price=460.0,
            expiration_date=datetime.date(2025, 6, 20),
            is_put=False, volatility=0.18, risk_free_rate=0.05,
        )
        print(pricer.compute_all())
        # {'delta': 0.44, 'gamma': 0.012, 'theta': -0.08, 'vega': 0.18, 'rho': 0.19}
    """

    def __init__(
        self,
        stock_price: float,
        strike_price: float,
        expiration_date: datetime.date,
        is_put: bool,
        volatility: float,
        risk_free_rate: float = 0.05,
        dividend_yield: float = 0.0,
        evaluation_date: Optional[datetime.date] = None,
    ):
        """
        Initializes the pricer and precomputes d1/d2.

        Args:
            stock_price (float): Current price of the underlying asset (S).
            strike_price (float): Strike price of the option (K).
            expiration_date (datetime.date): Expiration date of the option.
            is_put (bool): True for a put option, False for a call option.
            volatility (float): Implied volatility as a decimal (e.g. ``0.20`` for 20%).
                Clamped to a small positive value if non-positive to avoid division by zero.
            risk_free_rate (float): Annualised continuous risk-free rate (e.g. ``0.05`` for 5%).
                Defaults to 0.05.
            dividend_yield (float): Continuous annualised dividend yield (q). Defaults to 0.0.
            evaluation_date (datetime.date | None): Date from which to measure time to
                expiration. Defaults to ``datetime.date.today()``.

        Raises:
            ImportError: If ``scipy`` is not installed.
        """
        try:
            from scipy.stats import norm

            self.norm = norm
        except ImportError:
            raise ImportError(
                "scipy is required for BlackScholesPricer. Install it using 'pip install scipy'."
            )

        self.stock_price = float(stock_price)
        self.strike_price = float(strike_price)
        self.expiration_date = expiration_date
        self.is_put = bool(is_put)
        self.volatility = float(volatility)
        self.risk_free_rate = float(risk_free_rate)
        self.dividend_yield = float(dividend_yield)
        self.evaluation_date = evaluation_date or datetime.date.today()

        # Precompute common elements
        self._d1: float = 0.0
        self._d2: float = 0.0
        self._t: float = 0.0
        self._calculate_d1_d2()

    def _calculate_d1_d2(self) -> None:
        if self.volatility <= 0:
            self.volatility = 1e-8

        # Calculate time to expiration in years
        # If the option expires today, assume a minimal fractional day remaining to avoid div by zero
        delta = (self.expiration_date - self.evaluation_date).days
        self._t = delta / 365.0
        if self._t <= 0:
            self._t = 1e-8

        S = self.stock_price
        K = self.strike_price
        t = self._t
        r = self.risk_free_rate
        q = self.dividend_yield
        v = self.volatility

        self._d1 = (math.log(S / K) + (r - q + 0.5 * v**2) * t) / (v * math.sqrt(t))
        self._d2 = self._d1 - v * math.sqrt(t)

    def delta(self) -> float:
        """
        Theoretical Delta — rate of change of option price with respect to the underlying.

        Formula (Merton continuous dividend extension):
            Call: Δ = e^{-q·T} · N(d1)
            Put:  Δ = -e^{-q·T} · N(-d1)

        Returns:
            float: Delta in the range (-1, 0) for puts and (0, 1) for calls.
                At-the-money options have |Δ| ≈ 0.50; deep-in-the-money options
                approach ±1.
        """
        if not self.is_put:
            return math.exp(-self.dividend_yield * self._t) * self.norm.cdf(self._d1)
        else:
            return -math.exp(-self.dividend_yield * self._t) * self.norm.cdf(-self._d1)

    def gamma(self) -> float:
        """
        Theoretical Gamma — rate of change of Delta with respect to the underlying.

        Formula:
            Γ = e^{-q·T} · N'(d1) / (S · σ · √T)

        where N'(x) is the standard normal PDF.

        Returns:
            float: Gamma (always non-negative). Highest for at-the-money options near
                expiration. Used to estimate the convexity of the position; large gamma
                means delta hedges require frequent rebalancing.
        """
        return (
            math.exp(-self.dividend_yield * self._t)
            * self.norm.pdf(self._d1)
            / (self.stock_price * self.volatility * math.sqrt(self._t))
        )

    def theta(self) -> float:
        """
        Theoretical Theta — time decay of option price per calendar day.

        Formula (per year, then divided by 365):
            Call: Θ/yr = -(S·σ·e^{-q·T}·N'(d1))/(2√T) - r·K·e^{-r·T}·N(d2) + q·S·e^{-q·T}·N(d1)
            Put:  Θ/yr = -(S·σ·e^{-q·T}·N'(d1))/(2√T) + r·K·e^{-r·T}·N(-d2) - q·S·e^{-q·T}·N(-d1)

        Returns:
            float: Daily theta in dollars per option contract (before multiplying by
                ``OPTION_CONTRACT_SIZE``). Almost always negative for long options,
                meaning the option loses value as time passes. Short-option sellers
                profit from positive time decay.
        """
        S = self.stock_price
        K = self.strike_price
        r = self.risk_free_rate
        q = self.dividend_yield
        v = self.volatility
        t = self._t
        d1 = self._d1
        d2 = self._d2

        if not self.is_put:
            theta_annual = (
                -(S * v * math.exp(-q * t) * self.norm.pdf(d1)) / (2 * math.sqrt(t))
                - r * K * math.exp(-r * t) * self.norm.cdf(d2)
                + q * S * math.exp(-q * t) * self.norm.cdf(d1)
            )
        else:
            theta_annual = (
                -(S * v * math.exp(-q * t) * self.norm.pdf(d1)) / (2 * math.sqrt(t))
                + r * K * math.exp(-r * t) * self.norm.cdf(-d2)
                - q * S * math.exp(-q * t) * self.norm.cdf(-d1)
            )
        return theta_annual / 365.0

    def vega(self) -> float:
        """
        Theoretical Vega — option price sensitivity to a 1% change in implied volatility.

        Formula:
            V = S · e^{-q·T} · √T · N'(d1) / 100

        The division by 100 converts from "per unit σ" to "per 1% σ", matching the
        market convention where vega is quoted per percentage-point move in IV.

        Returns:
            float: Dollar change in option value for a +1 percentage-point increase in
                IV (e.g. vega=0.18 means the option gains $0.18 when IV rises from 20%
                to 21%). Vega is always positive and symmetric for calls and puts.
        """
        return (
            self.stock_price
            * math.exp(-self.dividend_yield * self._t)
            * math.sqrt(self._t)
            * self.norm.pdf(self._d1)
            / 100.0
        )

    def rho(self) -> float:
        """
        Theoretical Rho — option price sensitivity to a 1% change in the risk-free rate.

        Formula:
            Call: ρ = K·T·e^{-r·T}·N(d2) / 100
            Put:  ρ = -K·T·e^{-r·T}·N(-d2) / 100

        The division by 100 converts from "per unit r" to "per 1% r".

        Returns:
            float: Dollar change in option value for a +1 percentage-point rise in the
                risk-free rate. Calls have positive rho (higher rates → call worth more);
                puts have negative rho. Rho is usually the smallest Greek for short-dated
                options but becomes meaningful for long-dated LEAPS.
        """
        if not self.is_put:
            return (
                self.strike_price
                * self._t
                * math.exp(-self.risk_free_rate * self._t)
                * self.norm.cdf(self._d2)
                / 100.0
            )
        else:
            return (
                -self.strike_price
                * self._t
                * math.exp(-self.risk_free_rate * self._t)
                * self.norm.cdf(-self._d2)
                / 100.0
            )

    def compute_all(self) -> dict:
        """
        Returns all five theoretical Greeks as a single dict.

        Returns:
            dict: Keys are ``'delta'``, ``'gamma'``, ``'theta'``, ``'vega'``, ``'rho'``.
                Each value is computed once from the precomputed d1/d2 values.
                See individual methods for units and interpretation.
        """
        return {
            "delta": self.delta(),
            "gamma": self.gamma(),
            "theta": self.theta(),
            "vega": self.vega(),
            "rho": self.rho(),
        }


def calculate_gamma_exposure(
    df: Any, plot_strikes: int = 50, net_exposure: bool = False
) -> Any:
    """
    Calculates Dealer Gamma Exposure (GEX) across an option chain.

    GEX estimates the aggregate dollar-gamma that market-makers must hedge for each
    strike level.  When dealers are net-short gamma (typically from selling puts to
    retail) they must buy the underlying as it falls and sell as it rises, *amplifying*
    moves.  When net-long gamma they act as a stabilising force.

    **Formula (per option row):**

        GEX = S · Γ_signed · OI · contract_size · S · 0.01

    where ``Γ_signed = +Γ`` for calls and ``-Γ`` for puts, reflecting the
    SqueezeMetrics convention that dealers are assumed short calls / long puts.
    The two ``S`` multiplications and the ``0.01`` factor convert raw gamma (Δ/$ per
    $ move) to a dollar exposure for a 1% move in the underlying.

    Args:
        df (Any): Pandas DataFrame produced by ``parse_option_chain_to_df``.
            Must contain columns: ``strike_price``, ``gamma``, ``is_put``,
            ``openInterest``, ``stock_price``.
        plot_strikes (int): Number of strikes closest to the current underlying price
            to include in the result. Defaults to 50.
        net_exposure (bool): If ``True``, sum call and put GEX per strike into a single
            net value (positive = dealers net-long gamma at that strike).
            If ``False`` (default), return one row per option contract.

    Returns:
        pandas.DataFrame: Sorted descending by ``gamma_exposure``.

        When ``net_exposure=False`` columns are:
            ``symbol``, ``strike_price``, ``gamma_exposure``, ``expiration_date``, ``is_call``

        When ``net_exposure=True`` columns are:
            ``strike_price``, ``gamma_exposure``

        Returns an empty DataFrame if ``df`` is empty.

    Raises:
        ValueError: If ``df`` does not contain a ``stock_price`` column.

    Example::

        from schwab_api.utils import parse_option_chain_to_df
        from schwab_api.math import calculate_gamma_exposure

        df_chain = parse_option_chain_to_df(client.option_chains("SPY").json())
        gex = calculate_gamma_exposure(df_chain, net_exposure=True)
        # Positive strikes are "gamma walls"; negative are dealer short-gamma zones.
        print(gex.head())
    """
    import pandas as pd

    if df.empty:
        return pd.DataFrame()

    # Determine underlying price (should be consistent across the chain)
    if "stock_price" in df.columns:
        underlying_price = df["stock_price"].iloc[0]
    else:
        raise ValueError("DataFrame must contain a 'stock_price' column.")

    all_strike_prices = sorted(list(set(df["strike_price"].tolist())))
    all_strike_prices.sort(key=lambda x: abs(x - underlying_price))
    target_strike_prices = set(all_strike_prices[:plot_strikes])

    gamma_exposures: dict[Any, Any] = {}

    for idx, row in df.iterrows():
        strike = row["strike_price"]
        if strike not in target_strike_prices:
            continue

        raw_gamma = row.get("gamma", 0.0)
        is_call = not row.get("is_put", False)

        # Dealers are typically short calls and long puts based on retail flows,
        # but standard GEX formula from SqueezeMetrics assumes Call Gamma - Put Gamma.
        gamma_val = raw_gamma if is_call else -raw_gamma
        open_interest = row.get("openInterest", 0)

        exposure = (
            underlying_price
            * gamma_val
            * open_interest
            * OPTION_CONTRACT_SIZE
            * underlying_price
            * 0.01
        )

        if net_exposure:
            if strike in gamma_exposures:
                gamma_exposures[strike] += exposure
            else:
                gamma_exposures[strike] = exposure
        else:
            if strike not in gamma_exposures:
                gamma_exposures[strike] = []

            # handle index name for symbol
            symbol_val = row.get("symbol", idx) if hasattr(row, "get") else idx
            if getattr(df.index, "name", None) == "symbol":
                symbol_val = idx

            gamma_exposures[strike].append(
                {
                    "symbol": symbol_val,
                    "strike_price": strike,
                    "gamma_exposure": exposure,
                    "expiration_date": row.get("expiration_date"),
                    "is_call": is_call,
                }
            )

    if net_exposure:
        data = [
            {"strike_price": k, "gamma_exposure": v} for k, v in gamma_exposures.items()
        ]
    else:
        data = [exp for exposures in gamma_exposures.values() for exp in exposures]

    res_df = pd.DataFrame(data)
    if not res_df.empty:
        res_df = res_df.sort_values(by="gamma_exposure", ascending=False)
    return res_df


def calculate_mfiv_single_expiry(
    stock_price: float,
    strike_prices: Any,
    time_to_maturity: float,
    option_prices: Any,
    is_puts: Any,  # List/array of boolean values
    risk_free_rate: float,
    dividend_yield: float = 0.0,
) -> float:
    """
    Calculates the Model-Free Implied Volatility (MFIV) for a **single** expiration,
    following the CBOE VIX White Paper methodology as implemented in the R package
    ``R.MFIV`` (https://github.com/m-g-h/R.MFIV).

    Unlike Black-Scholes IV, MFIV does not assume a model for the underlying's price
    process. Instead it integrates the entire observed option smile:

        σ² = (2/T) · Σᵢ (ΔKᵢ / Kᵢ²) · e^{rT} · Q(Kᵢ)  −  (1/T) · (F/K₀ − 1)²

    where Q(Kᵢ) is the out-of-the-money option price at strike Kᵢ, ΔKᵢ is the
    half-distance to neighbouring strikes (trapezoidal integration), F is the forward
    price, and K₀ is the highest strike at or below F.

    **This function computes the MFIV for one expiry.** To produce a VIX-like 30-day
    index, call this function for the near and far bracketing expiries and then call
    ``calculate_vix_like_index`` to interpolate.

    Args:
        stock_price (float): Current spot price of the underlying (S > 0).
        strike_prices (Any): 1-D array-like of option strike prices. Does not need to
            be sorted; the function sorts internally.
        time_to_maturity (float): Time to expiration in years (e.g., ``30/365.0``).
            Must be > 0.
        option_prices (Any): 1-D array-like of mid-prices ``(bid+ask)/2`` for each
            option. Must be the same length as ``strike_prices``.
        is_puts (Any): 1-D array-like of booleans — ``True`` for put, ``False`` for
            call. Must be the same length as ``strike_prices``.
        risk_free_rate (float): Annualised, continuously-compounded risk-free rate
            matching the option's tenor (e.g. ``0.05`` for 5%).
        dividend_yield (float): Continuous annualised dividend yield. Defaults to 0.0.

    Returns:
        float: Annualised model-free implied volatility as a decimal (e.g. ``0.18``
            means 18%). Returns ``numpy.nan`` when the calculation cannot complete
            due to insufficient contributing strikes (< 2) or all-zero prices.

    Raises:
        ValueError: If any of the three arrays have inconsistent lengths, if
            ``time_to_maturity <= 0``, or if ``stock_price <= 0``.

    Notes:
        - Options with prices ≤ 1e-6 are dropped as illiquid before integration.
        - Duplicate strikes emit a ``warnings.warn`` but are not rejected; the
          duplicate at K₀ is averaged (call + put) as per the VIX methodology.
        - A negative variance can result from poor data quality (wide spreads, sparse
          strikes). The function clamps to 0 and warns rather than returning ``nan``.

    Example::

        from schwab_api.math import calculate_mfiv_single_expiry
        import numpy as np

        iv = calculate_mfiv_single_expiry(
            stock_price=450.0,
            strike_prices=[420, 430, 440, 450, 460, 470, 480],
            time_to_maturity=30/365.0,
            option_prices=[30.1, 21.4, 13.2, 7.5, 3.8, 1.6, 0.5],
            is_puts=[True]*4 + [False]*3,
            risk_free_rate=0.05,
        )
        print(f"30-day MFIV: {iv:.4f}")  # e.g. 0.1823
    """
    import warnings
    import numpy as np

    # --- Input Validation and Preparation ---
    if not (len(strike_prices) == len(option_prices) == len(is_puts)):
        raise ValueError(
            "Input arrays (strike_prices, option_prices, is_puts) must have the same length."
        )
    if time_to_maturity <= 0:
        raise ValueError("Time to maturity must be positive.")
    if stock_price <= 0:
        raise ValueError("Spot price must be positive.")

    strike_prices = np.asarray(strike_prices)
    option_prices = np.asarray(option_prices)
    is_puts = np.asarray(is_puts, dtype=bool)  # Ensure boolean

    # Remove options with non-positive prices (often indicates bad data or illiquidity)
    valid_price_mask = (
        option_prices > 1e-6
    )  # Use a small threshold instead of strict > 0
    strike_prices = strike_prices[valid_price_mask]
    option_prices = option_prices[valid_price_mask]
    is_puts = is_puts[valid_price_mask]

    if len(strike_prices) == 0:
        warnings.warn("No options with positive prices provided.")
        return np.nan

    # Sort options by strike price (essential for processing)
    sort_indices = np.argsort(strike_prices)
    strike_prices = strike_prices[sort_indices]
    option_prices = option_prices[sort_indices]
    is_puts = is_puts[sort_indices]

    # Check for duplicate strike_prices - R code warns but proceeds. We do the same.
    unique_strike_prices, counts = np.unique(strike_prices, return_counts=True)
    if np.any(counts > 1):
        warnings.warn(
            f"Duplicate strike_prices found: {unique_strike_prices[counts > 1]}. Ensure prices/types are correct for duplicates."
        )

    # --- Forward Price Calculation ---
    forward_price = stock_price * np.exp(
        (risk_free_rate - dividend_yield) * time_to_maturity
    )

    # --- Determine K0 (Strike immediately below or equal to Forward Price) ---
    k0_candidates = strike_prices[strike_prices <= forward_price]
    if len(k0_candidates) == 0:
        # If F is below the lowest strike, VIX methodology might use the lowest strike.
        # R code's behavior isn't explicit here. Let's use the minimum strike and warn.
        warnings.warn(
            f"Forward price {forward_price:.2f} is below the lowest strike {strike_prices[0]:.2f}. Using lowest strike as K0."
        )
        k0 = strike_prices[0]
    else:
        k0 = k0_candidates[-1]  # Highest strike <= forward_price

    # --- Select Contributing Options and Handle K0 Price ---
    # 1. Filter puts <= K0
    put_mask = (strike_prices <= k0) & is_puts
    # 2. Filter calls >= K0
    call_mask = (strike_prices >= k0) & ~is_puts

    # 3. Combine masks and get relevant options
    combined_mask = put_mask | call_mask
    contrib_strike_prices = strike_prices[combined_mask]
    contrib_prices = option_prices[combined_mask]
    contrib_is_puts = is_puts[combined_mask]  # Keep track for potential debugging

    # Ensure unique strike_prices after filtering (should already be due to sorting and K0 logic)
    # Sort contributing options by strike (essential for Delta K calculation loop)
    sort_idx_contrib = np.argsort(contrib_strike_prices)
    contrib_strike_prices = contrib_strike_prices[sort_idx_contrib]
    contrib_prices = contrib_prices[sort_idx_contrib]
    contrib_is_puts = contrib_is_puts[sort_idx_contrib]  # Keep aligned

    # 4. Handle the price at K0: Average if both call and put exist at K0
    k0_contrib_indices = np.where(contrib_strike_prices == k0)[0]
    final_contrib_strike_prices = []
    final_contrib_prices = []

    processed_k0 = False
    for i in range(len(contrib_strike_prices)):
        strike = contrib_strike_prices[i]
        price = contrib_prices[i]

        if strike == k0:
            if not processed_k0:
                if len(k0_contrib_indices) > 1:  # Both call and put were selected
                    avg_price_k0 = np.mean(contrib_prices[k0_contrib_indices])
                    final_contrib_strike_prices.append(strike)
                    final_contrib_prices.append(avg_price_k0)
                else:  # Only one type (call or put) at K0 was selected
                    final_contrib_strike_prices.append(strike)
                    final_contrib_prices.append(price)
                processed_k0 = True
            # else: skip subsequent entries if K0 already processed
        else:
            final_contrib_strike_prices.append(strike)
            final_contrib_prices.append(price)

    contrib_strike_prices = np.array(final_contrib_strike_prices)
    contrib_prices = np.array(final_contrib_prices)
    n_contrib = len(contrib_strike_prices)

    if n_contrib < 2:
        # VIX/MFIV calculation generally requires at least two distinct strike prices
        # for Delta K calculation. R code might implicitly fail or give odd results.
        warnings.warn(
            f"Calculation requires at least 2 distinct contributing strike prices after filtering, found {n_contrib}. Cannot calculate MFIV."
        )
        return np.nan

    # --- Calculate Sum of Variance Contributions ---
    sum_contribution = 0.0
    discount_factor = np.exp(risk_free_rate * time_to_maturity)

    for i in range(n_contrib):
        k_i = contrib_strike_prices[i]
        price_i = contrib_prices[i]

        # Calculate Delta K for strike k_i based on the *contributing* strike_prices list
        # This matches the R code's approach.
        if i == 0:  # Lowest strike
            delta_k_i = contrib_strike_prices[i + 1] - contrib_strike_prices[i]
        elif i == n_contrib - 1:  # Highest strike
            delta_k_i = contrib_strike_prices[i] - contrib_strike_prices[i - 1]
        else:  # Intermediate strike_prices
            delta_k_i = (
                contrib_strike_prices[i + 1] - contrib_strike_prices[i - 1]
            ) / 2.0

        if k_i <= 0:  # Avoid division by zero or issues with zero strike
            warnings.warn(f"Skipping contribution for non-positive strike K={k_i}")
            continue

        term = (delta_k_i / (k_i**2)) * discount_factor * price_i
        sum_contribution += term

    # --- Final Variance Calculation ---
    # Ensure k0 is positive before division
    if k0 <= 0:
        warnings.warn(
            f"K0 strike ({k0}) is not positive. Cannot complete variance calculation."
        )
        return np.nan

    try:
        variance = (2.0 / time_to_maturity) * sum_contribution - (
            1.0 / time_to_maturity
        ) * ((forward_price / k0) - 1.0) ** 2
    except ZeroDivisionError:
        warnings.warn(
            "Division by zero encountered during final variance calculation (check K0)."
        )
        return np.nan

    # Handle potential negative variance due to data/numerical issues
    if variance < 0:
        # This often happens with poor quality data / wide spreads / sparse strike_prices
        warnings.warn(
            f"Calculated variance is negative ({variance:.4f}). Returning 0. Check input data quality/liquidity/strike_prices."
        )
        variance = 0.0

    # --- Return Volatility (sqrt of variance) ---
    volatility = np.sqrt(variance)
    return volatility


def calculate_vix_like_index(
    near_df: Any,
    far_df: Any,
    t1: float,
    t2: float,
    risk_free_rate: float,
    target_days: int = 30,
    dividend_yield: float = 0.0,
) -> float:
    """
    Calculates a VIX-like implied volatility index by interpolating between two
    expiry MFIVs using the CBOE VIX methodology.

    The CBOE formula weights near- and far-term variances proportionally so the
    result represents the implied volatility for exactly ``target_days`` days:

        σ² = [T1·σ1²·w1 + T2·σ2²·w2] · (365 / target_days)

    where w1 = (T2 - T_target)/(T2 - T1) and w2 = (T_target - T1)/(T2 - T1).

    Args:
        near_df (Any): DataFrame for the near-term expiry (output of
            ``parse_option_chain_to_df``). Must contain a single expiration.
        far_df (Any): DataFrame for the far-term expiry. Must contain a single
            expiration distinct from ``near_df``.
        t1 (float): Time to near-term expiry in years (e.g. 23/365.0).
        t2 (float): Time to far-term expiry in years (e.g. 37/365.0).
            Must satisfy t2 > t1 > 0.
        risk_free_rate (float): Annualised risk-free rate (e.g. 0.05 for 5%).
        target_days (int): Target interpolation horizon in calendar days.
            Defaults to 30 (standard VIX convention).
        dividend_yield (float): Continuous annualised dividend yield. Defaults to 0.0.

    Returns:
        float: Annualised implied volatility as a decimal (e.g. 0.18 means 18%).
            Returns ``np.nan`` if either leg produces a NaN MFIV.

    Raises:
        ValueError: If t1 >= t2, t1 <= 0, or target_days <= 0.
        ValueError: If the target horizon falls outside [t1, t2].
    """
    import numpy as np

    if t1 <= 0 or t2 <= t1:
        raise ValueError(f"Require 0 < t1 < t2, got t1={t1}, t2={t2}.")
    if target_days <= 0:
        raise ValueError(f"target_days must be positive, got {target_days}.")

    t_target = target_days / 365.0
    if not (t1 <= t_target <= t2):
        raise ValueError(
            f"Target horizon {t_target:.4f} yr ({target_days}d) must lie within "
            f"[t1={t1:.4f}, t2={t2:.4f}]."
        )

    sigma1 = calculate_mfiv_from_df(near_df, t1, risk_free_rate, dividend_yield)
    sigma2 = calculate_mfiv_from_df(far_df, t2, risk_free_rate, dividend_yield)

    if np.isnan(sigma1) or np.isnan(sigma2):
        return np.nan

    var1 = sigma1**2
    var2 = sigma2**2

    # CBOE interpolation weights
    w1 = (t2 - t_target) / (t2 - t1)
    w2 = (t_target - t1) / (t2 - t1)

    # Annualise to target_days horizon
    interpolated_variance = (t1 * var1 * w1 + t2 * var2 * w2) * (365.0 / target_days)
    return float(np.sqrt(max(interpolated_variance, 0.0)))


def calculate_mfiv_from_df(
    df: Any, time_to_maturity: float, risk_free_rate: float, dividend_yield: float = 0.0
) -> float:
    """
    Convenience wrapper that computes MFIV directly from a parsed option-chain DataFrame.

    Extracts the required arrays from a DataFrame produced by
    ``parse_option_chain_to_df`` and delegates to ``calculate_mfiv_single_expiry``.
    Prefer this over calling ``calculate_mfiv_single_expiry`` directly when working
    with Schwab API responses.

    Args:
        df (Any): Pandas DataFrame for a **single** expiry as returned by
            ``parse_option_chain_to_df``.  Must contain columns:
            ``stock_price``, ``strike_price``, ``option_price``, ``is_put``.
        time_to_maturity (float): Time to expiration in years (e.g. ``23/365.0``).
        risk_free_rate (float): Annualised risk-free rate (e.g. ``0.05`` for 5%).
        dividend_yield (float): Continuous annualised dividend yield. Defaults to 0.0.

    Returns:
        float: Annualised MFIV as a decimal (e.g. ``0.18``), or ``numpy.nan`` if
            ``df`` is empty or the calculation fails.

    Raises:
        ValueError: If ``df`` contains multiple expiration dates (MFIV requires a
            single expiry per call) or if required columns are missing.

    Example::

        from schwab_api.utils import parse_option_chain_to_df
        from schwab_api.math import calculate_mfiv_from_df

        df = parse_option_chain_to_df(client.option_chains("SPY", fromDate="2025-05-16",
                                                            toDate="2025-05-16").json())
        iv = calculate_mfiv_from_df(df, time_to_maturity=23/365.0, risk_free_rate=0.05)
        print(f"SPY 23-day MFIV: {iv:.4f}")
    """
    import numpy as np

    if df.empty:
        return np.nan

    if "expiration_date" in df.columns and len(df["expiration_date"].unique()) > 1:
        raise ValueError(
            "DataFrame contains multiple expiration dates. MFIV requires a single expiry."
        )

    if (
        "stock_price" not in df.columns
        or "strike_price" not in df.columns
        or "option_price" not in df.columns
        or "is_put" not in df.columns
    ):
        raise ValueError("DataFrame missing required columns.")

    stock_price = float(df["stock_price"].iloc[0])
    strike_prices = df["strike_price"].values
    option_prices = df["option_price"].values
    is_puts = df["is_put"].values

    return calculate_mfiv_single_expiry(
        stock_price=stock_price,
        strike_prices=strike_prices,
        time_to_maturity=time_to_maturity,
        option_prices=option_prices,
        is_puts=is_puts,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )
