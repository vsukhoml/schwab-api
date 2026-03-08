#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Trading Strategies Example
--------------------------
Demonstrates programmatic options trading strategies using the schwab_api library.
Includes "The Wheel" (Cash-Secured Puts) and Bull Put Credit Spreads.
"""

import os
import sys
import json
import logging
from typing import List, Optional

from schwab_api.client import Client
from schwab_api.trading import OptionChainAnalyzer, PositionAnalyzer
from schwab_api.orders.options import option_sell_to_open_limit, bull_put_vertical_open

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Constants
DEFAULT_CALLBACK_URL = "https://127.0.0.1:8182"


def initialize_client() -> Optional[Client]:
    """Initializes the Schwab API client using environment variables."""
    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    callback_url = os.getenv("SCHWAB_CALLBACK_URL", DEFAULT_CALLBACK_URL)

    if not app_key or not app_secret or app_key == "YOUR_APP_KEY":
        logger.warning(
            "SCHWAB_APP_KEY and SCHWAB_APP_SECRET environment variables are missing. "
            "Please export them. Running in demo mode might fail."
        )
        return None

    return Client(app_key, app_secret, callback_url)


def get_first_account_hash(client: Client) -> Optional[str]:
    """Fetches the first available encrypted account hash."""
    try:
        accounts = client.linked_accounts().json()
        if not accounts:
            logger.error("No linked accounts found.")
            return None
        return accounts[0].get("hashValue")
    except Exception as e:
        logger.error(f"Failed to fetch accounts: {e}")
        return None


def run_wheel_strategy(client: Client, account_hash: str, target_tickers: List[str]) -> None:
    """
    The Wheel Strategy:
    1. Check current positions for options that reached a 50% profit target to close.
    2. Scan target tickers for new 30-45 DTE Cash-Secured Puts at ~0.25 Delta.
    3. Construct STO (Sell-To-Open) orders.
    """
    logger.info("\n--- Running Strategy: The Wheel (Cash-Secured Puts) ---")

    # 1. Evaluate Current Positions
    try:
        positions_response = client.account_details(account_hash, fields="positions").json()
        raw_positions = positions_response.get("securitiesAccount", {}).get("positions", [])
        analyzer = PositionAnalyzer(raw_positions)
        
        # Identify positions that have made 50% or more profit and can be closed early
        winners = analyzer.get_winning_options(min_profit_percentage=50.0)
        for winner in winners:
            logger.info(
                f"Take Profit Opportunity: {winner['symbol']} is up "
                f"{winner['profit_percentage']:.1f}%"
            )
            # You would construct a Buy-To-Close order here
    except Exception as e:
        logger.error(f"Failed to evaluate current positions: {e}")

    # 2. Find new Put Selling Opportunities
    for ticker in target_tickers:
        logger.info(f"Scanning option chains for {ticker}...")
        try:
            chain_json = client.option_chains(ticker, contractType="PUT", strikeCount=15).json()
            chain = OptionChainAnalyzer(chain_json)
            
            # The Wheel Sweet Spot: 30 to 45 Days to Expiration, ~0.20 to ~0.30 Delta
            candidates = chain.get_put_candidates(
                min_dte=30, max_dte=45,
                min_delta=0.20, max_delta=0.30,
                min_premium_percentage=0.01  # Premium is at least 1% of the strike
            )
            
            if candidates.empty:
                logger.info(f"No suitable put candidates found for {ticker}.")
                continue
                
            # Take the best candidate (highest premium for lowest delta in date range)
            best_put = candidates.iloc[0]
            
            logger.info(
                f"Opportunity Identified: Sell {ticker} Put at ${best_put['strike_price']} "
                f"strike, expiring in {best_put['days_to_expiration']} days."
            )
            logger.info(f"Delta: {best_put['delta']:.3f}, Premium (Mid): ${best_put['option_price']:.2f}")
            
            # 3. Construct the STO Order using schwab-api order builder
            symbol = best_put.name # OptionChainAnalyzer sets index to the exact Schwab symbol
            quantity = 1
            limit_price = round(float(best_put['option_price']), 2)
            
            sto_order = option_sell_to_open_limit(symbol, quantity, limit_price).build()
            
            logger.info("Constructed Order JSON:")
            print(json.dumps(sto_order, indent=2))
            
            # Dry run execution...
            # response = client.place_order(account_hash, sto_order)
            # logger.info(f"Order placed: {response.status_code}")
            
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")


def find_credit_spread(client: Client, account_hash: str, ticker: str) -> None:
    """
    Bull Put Credit Spread Strategy:
    Sell an Out-of-the-Money (OTM) Put and Buy a further OTM Put to cap risk.
    """
    logger.info(f"\n--- Running Strategy: Bull Put Credit Spread for {ticker} ---")
    
    try:
        chain_json = client.option_chains(ticker, contractType="PUT", strikeCount=20).json()
        chain = OptionChainAnalyzer(chain_json)
        
        # Get all puts expiring in around 30 days
        puts_30d = chain.filter_options(option_type="PUT", min_dte=25, max_dte=35)
        
        if puts_30d.empty:
            logger.info("No options found in the 30-day window.")
            return
            
        # Group by expiration date so we compare apples to apples
        expirations = puts_30d['expiration_date'].unique()
        target_exp = expirations[0]
        
        options = puts_30d[puts_30d['expiration_date'] == target_exp].sort_values(
            by="strike_price", ascending=False
        )
        
        # We want to sell a put at ~0.30 Delta, and buy a put ~5 dollars below it
        short_put_candidates = options[(options['delta'].abs() >= 0.25) & (options['delta'].abs() <= 0.35)]
        
        if short_put_candidates.empty:
            logger.info("Could not find short leg candidate.")
            return
            
        short_put = short_put_candidates.iloc[0]
        
        # Find long leg (e.g. $5 wide spread)
        target_long_strike = short_put['strike_price'] - 5.0
        long_put_candidates = options[options['strike_price'] <= target_long_strike]
        
        if long_put_candidates.empty:
            logger.info("Could not find long leg candidate.")
            return
            
        long_put = long_put_candidates.iloc[0]
        
        net_credit = short_put['bid'] - long_put['ask']
        
        logger.info(f"Credit Spread Opportunity for {ticker} (Exp: {target_exp}):")
        logger.info(f"  Short Leg: Sell {short_put.name} (${short_put['strike_price']} strike) at ${short_put['bid']:.2f}")
        logger.info(f"  Long Leg:  Buy  {long_put.name} (${long_put['strike_price']} strike) at ${long_put['ask']:.2f}")
        logger.info(f"  Max Risk:  ${(short_put['strike_price'] - long_put['strike_price'] - net_credit) * 100:.2f}")
        logger.info(f"  Net Credit: ${net_credit:.2f}")
        
        if net_credit <= 0:
            logger.info("Spread does not result in a credit, skipping.")
            return

        # Construct complex order using the order builder
        spread_order = bull_put_vertical_open(
            long_put_symbol=long_put.name,
            short_put_symbol=short_put.name,
            quantity=1,
            net_credit=round(float(net_credit), 2)
        ).build()
        
        logger.info("Constructed Complex Order JSON:")
        print(json.dumps(spread_order, indent=2))
        
        # Dry run execution...
        # response = client.place_order(account_hash, spread_order)

    except Exception as e:
        logger.error(f"Error constructing credit spread for {ticker}: {e}")


def main() -> None:
    """Main execution function."""
    client = initialize_client()
    if not client:
        sys.exit(1)
        
    account_hash = get_first_account_hash(client)
    if not account_hash:
        sys.exit(1)

    logger.info(f"Using account hash: {account_hash}")

    # Run strategies
    run_wheel_strategy(client, account_hash, target_tickers=["AAPL", "GOOG"])
    find_credit_spread(client, account_hash, ticker="MSFT")


if __name__ == "__main__":
    main()