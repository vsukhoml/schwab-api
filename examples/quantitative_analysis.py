#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quantitative Analysis Example
-----------------------------
Demonstrates quantitative analysis using Black-Scholes theoretical pricing
and Gamma Exposure (GEX) analysis using the schwab_api library.
"""

import os
import datetime
import logging
from typing import Optional

from schwab_api.client import Client
from schwab_api.math import BlackScholesPricer, calculate_gamma_exposure
from schwab_api.utils import parse_option_chain_to_df

# Setup basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Optional dependency check for plotting
try:
    import matplotlib.pyplot as plt
    import seaborn as sns

    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False

DEFAULT_CALLBACK_URL = "https://127.0.0.1:8182"


def initialize_client() -> Optional[Client]:
    """Initializes the Schwab API client using environment variables."""
    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    callback_url = os.getenv("SCHWAB_CALLBACK_URL", DEFAULT_CALLBACK_URL)

    if not app_key or not app_secret or app_key == "YOUR_APP_KEY":
        logger.warning(
            "SCHWAB_APP_KEY and SCHWAB_APP_SECRET environment variables are missing. "
            "Skipping live API data fetch and using mock data instead."
        )
        return None

    return Client(app_key, app_secret, callback_url)


def run_black_scholes_demo() -> None:
    """Demonstrates offline Black-Scholes pricing."""
    logger.info("\n--- Running Black-Scholes Options Pricing ---")

    # Parameters for an At-The-Money Call option
    S = 150.0  # Spot Price
    K = 150.0  # Strike Price
    expiration = datetime.date.today() + datetime.timedelta(days=30)
    iv = 0.25  # 25% Implied Volatility

    logger.info(f"Pricer Parameters: Spot=${S}, Strike=${K}, DTE=30, IV={iv * 100}%")

    pricer = BlackScholesPricer(
        stock_price=S,
        strike_price=K,
        expiration_date=expiration,
        is_put=False,
        volatility=iv,
    )

    greeks = pricer.compute_all()
    logger.info("Theoretical Call Greeks:")
    for greek, value in greeks.items():
        logger.info(f"  {greek.capitalize()}: {value:.5f}")


def plot_gamma_exposure(gex_df, ticker: str) -> None:
    """Plots the Gamma Exposure DataFrame using Matplotlib."""
    if not HAS_PLOT:
        logger.info("matplotlib/seaborn not installed. Skipping plot generation.")
        return

    logger.info("Generating Gamma Exposure plot...")

    plt.figure(figsize=(12, 6))
    sns.set_theme(style="darkgrid")

    # Sort for plotting
    df_plot = gex_df.sort_values(by="strike_price")

    colors = ["#2ecc71" if x > 0 else "#e74c3c" for x in df_plot["gamma_exposure"]]

    plt.bar(
        df_plot["strike_price"],
        df_plot["gamma_exposure"] / 1e6,
        color=colors,
        width=1.5,
    )

    plt.axhline(0, color="black", linewidth=1)
    plt.title(f"{ticker} Net Gamma Exposure (GEX) by Strike", fontsize=16)
    plt.xlabel("Strike Price ($)", fontsize=12)
    plt.ylabel("Net GEX (Millions)", fontsize=12)

    plt.tight_layout()
    plot_path = f"{ticker}_gex_plot.png"
    plt.savefig(plot_path)
    logger.info(f"Plot saved to: {plot_path}")


def run_gamma_exposure_demo(client: Optional[Client], ticker: str = "SPY") -> None:
    """Demonstrates fetching an option chain and calculating Gamma Exposure."""
    logger.info(f"\n--- Running Gamma Exposure (GEX) Analysis for {ticker} ---")

    if client:
        logger.info("Fetching real option chains from Schwab...")
        try:
            # Fetch ALL chains (calls and puts) to calculate net exposure
            chain_resp = client.option_chains(ticker, contractType="ALL")
            chain_json = chain_resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch option chain: {e}")
            return
    else:
        logger.info("Using mock option chain data...")
        chain_json = {
            "symbol": ticker,
            "underlyingPrice": 500.0,
            "callExpDateMap": {
                "2023-11-17:15": {
                    "490.0": [
                        {
                            "symbol": f"{ticker}_C490",
                            "gamma": 0.02,
                            "openInterest": 15000,
                        }
                    ],
                    "500.0": [
                        {
                            "symbol": f"{ticker}_C500",
                            "gamma": 0.05,
                            "openInterest": 50000,
                        }
                    ],
                    "510.0": [
                        {
                            "symbol": f"{ticker}_C510",
                            "gamma": 0.03,
                            "openInterest": 25000,
                        }
                    ],
                }
            },
            "putExpDateMap": {
                "2023-11-17:15": {
                    "490.0": [
                        {
                            "symbol": f"{ticker}_P490",
                            "gamma": 0.03,
                            "openInterest": 40000,
                        }
                    ],
                    "500.0": [
                        {
                            "symbol": f"{ticker}_P500",
                            "gamma": 0.05,
                            "openInterest": 30000,
                        }
                    ],
                    "510.0": [
                        {
                            "symbol": f"{ticker}_P510",
                            "gamma": 0.02,
                            "openInterest": 10000,
                        }
                    ],
                }
            },
        }

    try:
        df_chain = parse_option_chain_to_df(chain_json)

        # Calculate net exposure per strike
        gex_df = calculate_gamma_exposure(df_chain, plot_strikes=20, net_exposure=True)

        if gex_df.empty:
            logger.info("No data found to calculate GEX.")
            return

        underlying_price = (
            df_chain["stock_price"].iloc[0] if not df_chain.empty else 0.0
        )
        logger.info(f"Current Underlying Price: ${underlying_price:.2f}")
        logger.info("Top Net Gamma Exposure Strikes:")

        # Print top 5 absolute exposures
        top_strikes = gex_df.reindex(
            gex_df["gamma_exposure"].abs().sort_values(ascending=False).index
        ).head(5)
        for _, row in top_strikes.iterrows():
            gex_mil = row["gamma_exposure"] / 1_000_000
            logger.info(
                f"  Strike ${row['strike_price']:>6.1f} | Net GEX: ${gex_mil:>8.2f}M"
            )

        # Optionally plot
        plot_gamma_exposure(gex_df, ticker)

    except ImportError:
        logger.error(
            "pandas is required for gamma exposure calculation. Install with: pip install pandas"
        )
    except Exception as e:
        logger.error(f"Error during GEX analysis: {e}")


def main() -> None:
    client = initialize_client()

    run_black_scholes_demo()
    run_gamma_exposure_demo(client, ticker="SPY")


if __name__ == "__main__":
    main()
