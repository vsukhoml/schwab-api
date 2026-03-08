#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Portfolio Overview Example
--------------------------
Retrieves and displays portfolio statistics, open positions, and working orders
for all linked Schwab accounts using the schwab_api library.
"""

import os
import sys
import logging
import datetime
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from schwab_api.client import Client

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Constants
DEFAULT_CALLBACK_URL = "https://127.0.0.1:8182"


def initialize_client() -> Optional[Client]:
    """
    Initializes the Schwab API client using environment variables.
    """
    load_dotenv()

    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    callback_url = os.getenv("SCHWAB_CALLBACK_URL", DEFAULT_CALLBACK_URL)

    if not app_key or not app_secret:
        logger.error(
            "SCHWAB_APP_KEY and SCHWAB_APP_SECRET environment variables are missing. "
            "Please export them or add them to a .env file."
        )
        return None

    logger.info("Initializing Schwab API Client...")
    return Client(app_key, app_secret, callback_url)


def print_account_header(account_number: str) -> None:
    """Prints a formatted header for an account."""
    header_line = "=" * 60
    masked_acc = f"*******{account_number[-4:]}" if len(account_number) >= 4 else account_number
    print(f"\n{header_line}")
    print(f"Account: {masked_acc}")
    print(f"{header_line}")


def display_portfolio_stats(balances: Dict[str, Any], positions: List[Dict[str, Any]]) -> None:
    """Parses and prints total equity, cash balance, and open position details."""
    total_equity = balances.get("liquidationValue", 0.0)
    cash_balance = balances.get("cashBalance", 0.0)

    print("Portfolio Statistics:")
    print(f"  Total Equity: ${total_equity:,.2f}")
    print(f"  Cash Balance: ${cash_balance:,.2f}")
    print(f"  Total Open Positions: {len(positions)}")
    print("-" * 60)

    if not positions:
        print("No open positions.")
        return

    print(f"{'Symbol':<20} {'Asset Type':<15} {'Quantity':<10} {'Market Value':<15}")
    print("-" * 65)

    for pos in positions:
        instrument = pos.get("instrument", {})
        symbol = instrument.get("symbol", "N/A")
        asset_type = instrument.get("assetType", "N/A")

        long_qty = pos.get("longQuantity", 0)
        short_qty = pos.get("shortQuantity", 0)
        qty = long_qty - short_qty

        market_value = pos.get("marketValue", 0.0)

        print(f"{symbol:<20} {asset_type:<15} {qty:<10} ${market_value:>10,.2f}")


def display_working_orders(orders: List[Dict[str, Any]]) -> None:
    """Parses and prints outstanding (WORKING) orders."""
    print("\nOutstanding Orders (WORKING status):")
    if not orders:
        print("  No outstanding orders.")
        return

    print(f"{'Order ID':<15} {'Status':<15} {'Entered Time':<25} {'Instruction':<25}")
    print("-" * 80)

    for order in orders:
        order_id = str(order.get("orderId", "N/A"))
        status = order.get("status", "N/A")
        entered_time = order.get("enteredTime", "N/A")

        order_legs = order.get("orderLegCollection", [])
        instruction = "Complex/Unknown"

        if order_legs:
            leg = order_legs[0]
            leg_inst = leg.get("instruction", "")
            leg_sym = leg.get("instrument", {}).get("symbol", "")
            leg_qty = leg.get("quantity", 0)
            
            instruction = f"{leg_inst} {leg_qty} {leg_sym}"
            extra_legs = len(order_legs) - 1
            if extra_legs > 0:
                instruction += f" (+{extra_legs} legs)"

        print(f"{order_id:<15} {status:<15} {entered_time:<25} {instruction:<25}")


def process_account(client: Client, account_hash: str, account_number: str) -> None:
    """Fetches and displays details and orders for a single account."""
    print_account_header(account_number)

    try:
        details_resp = client.account_details(account_hash, fields="positions")
        details = details_resp.json()

        securities_account = details.get("securitiesAccount", {})
        balances = securities_account.get("currentBalances", {})
        positions = securities_account.get("positions", [])

        display_portfolio_stats(balances, positions)
    except Exception as e:
        logger.error(f"Error fetching account details: {e}")

    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        thirty_days_ago = now - datetime.timedelta(days=30)
        
        orders_resp = client.account_orders(
            account_hash, 
            status="WORKING",
            fromEnteredTime=thirty_days_ago,
            toEnteredTime=now
        )
        orders = orders_resp.json()

        display_working_orders(orders)
    except Exception as e:
        logger.error(f"Error fetching outstanding orders: {e}")


def main() -> None:
    """Main execution function."""
    client = initialize_client()
    if not client:
        sys.exit(1)

    try:
        logger.info("Fetching Linked Accounts...")
        accounts_resp = client.linked_accounts()
        accounts = accounts_resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch linked accounts: {e}")
        sys.exit(1)

    if not accounts:
        logger.info("No linked accounts found.")
        return

    for acc in accounts:
        acc_hash = acc.get("hashValue")
        acc_num = acc.get("accountNumber", "Unknown")
        
        if acc_hash:
            process_account(client, acc_hash, acc_num)
        else:
            logger.warning(f"Account {acc_num} is missing a hash value; skipping.")


if __name__ == "__main__":
    main()