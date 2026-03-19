import datetime
import logging
import math
from typing import Any, Optional

from schwab_api.utils import OPTION_CONTRACT_SIZE

logger = logging.getLogger(__name__)


class BlackScholesPricer:
    """
    A standalone Black-Scholes options pricing calculator for generating theoretical Greeks.
    Does not depend on external APIs, relying solely on provided parameters.
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
        Initializes the pricer.

        :param stock_price: Current price of the underlying asset.
        :param strike_price: Strike price of the option.
        :param expiration_date: Expiration date of the option.
        :param is_put: True if the option is a put, False if it is a call.
        :param volatility: Implied volatility as a decimal (e.g. 0.20 for 20%).
        :param risk_free_rate: Annual risk-free interest rate as a decimal (default 0.05 for 5%).
        :param dividend_yield: Annual continuous dividend yield as a decimal (default 0.0).
        :param evaluation_date: Date to evaluate from (default is today).
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
        """Calculates theoretical Delta."""
        if not self.is_put:
            return math.exp(-self.dividend_yield * self._t) * self.norm.cdf(self._d1)
        else:
            return -math.exp(-self.dividend_yield * self._t) * self.norm.cdf(-self._d1)

    def gamma(self) -> float:
        """Calculates theoretical Gamma."""
        return (
            math.exp(-self.dividend_yield * self._t)
            * self.norm.pdf(self._d1)
            / (self.stock_price * self.volatility * math.sqrt(self._t))
        )

    def theta(self) -> float:
        """Calculates theoretical Theta (decay per day)."""
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
        """Calculates theoretical Vega (price change per 1% change in IV)."""
        return (
            self.stock_price
            * math.exp(-self.dividend_yield * self._t)
            * math.sqrt(self._t)
            * self.norm.pdf(self._d1)
            / 100.0
        )

    def rho(self) -> float:
        """Calculates theoretical Rho (price change per 1% change in interest rate)."""
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
        """Returns a dictionary containing all Greeks."""
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
    Calculates Gamma Exposure (GEX) across option chains, allowing for visualization
    of dealer positioning.

    :param df: Pandas DataFrame containing option chain data (e.g. from parse_option_chain_to_df).
    :param plot_strikes: Number of strike_prices closest to the money to include.
    :param net_exposure: Whether to calculate net gamma exposure per strike.
    :return: Pandas DataFrame with gamma exposure data.
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
    import warnings
    import numpy as np

    """
    Calculates the Model-Free Implied Volatility (MFIV) for a single expiration
    date, based on the methodology implemented in the R script R.MFIV/R/MFIV.R
    (https://github.com/m-g-h/R.MFIV).

    This represents the volatility derived from the options for one specific
    maturity. A full VIX-like index requires calculating this for two maturities
    bracketing the target period (e.g., 30 days) and then interpolating.

    Args:
        stock_price (float): Current price of the underlying asset.
        strike_prices (Any): Array of option strike prices.
        time_to_maturity (float): Time to expiration in years (e.g., 30/365.0).
        option_prices (Any): Array of option market prices (mid-price).
                                          Must correspond to the strike_prices array.
        is_puts (Any): Array of boolean values (True for put, False for call).
                                           Must correspond to the strike_prices array.
        risk_free_rate (float): The risk-free interest rate corresponding to the
                                time_to_maturity (annualized).
        dividend_yield (float, optional): Continuous annualized dividend yield.
                                          Defaults to 0.0.

    Returns:
        float: The calculated model-free implied volatility (annualized, not %).
               Returns np.nan if calculation cannot be completed (e.g., insufficient data).

    Raises:
        ValueError: If input arrays have inconsistent lengths or time_to_maturity <= 0.
    """

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


def calculate_mfiv_from_df(
    df: Any, time_to_maturity: float, risk_free_rate: float, dividend_yield: float = 0.0
) -> float:
    """
    Helper function to calculate MFIV directly from a DataFrame.
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
