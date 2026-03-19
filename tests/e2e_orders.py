import logging
import os
import sys
import time
from typing import Any, Dict, List

from dotenv import load_dotenv

from schwab_api.client import Client
from schwab_api.orders.common import Duration
from schwab_api.orders.equities import equity_buy_limit, equity_sell_short_limit
from schwab_api.stream import StreamClient
from schwab_api.stream_parsers import StreamResponseHandler

# Configure logging
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_orders")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)


def extract_order_id(response) -> str:
    """Helper to extract the order ID from a successful place_order response."""
    location = response.headers.get("Location")
    if not location:
        return ""
    return location.split("/")[-1]


class OrderStreamTracker(StreamResponseHandler):
    def __init__(self):
        super().__init__()
        self.events: List[Dict[str, Any]] = []

    def on_account_activity(self, update: Dict[str, Any]) -> None:
        logger.info(f"Stream update (Account Activity): {update}")
        self.events.append(update)

    def on_response(self, response: Dict[str, Any]) -> None:
        logger.info(f"Stream response: {response}")

    def on_unknown_event(self, service: str, update: Dict[str, Any]) -> None:
        logger.warning(f"Unknown stream event from {service}: {update}")


def main():
    load_dotenv()
    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")

    if not app_key or not app_secret:
        logger.error("SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set.")
        sys.exit(1)

    client = Client(app_key, app_secret, logger=logger)
    logger.info("Client initialized successfully.")

    # Get linked accounts to get accountHash
    accounts = client.linked_accounts().json()
    if not accounts:
        logger.error("No linked accounts found.")
        return

    # Prioritize account 99415888
    target_account = "99415888"
    account_hash = next(
        (
            acc["hashValue"]
            for acc in accounts
            if acc.get("accountNumber") == target_account
        ),
        accounts[0]["hashValue"],
    )

    logger.info(f"Using account hash: {account_hash}")

    symbol = "AAPL"

    # Get quote
    try:
        quote_resp = client.quote(symbol).json()
        last_price = quote_resp.get(symbol, {}).get("quote", {}).get("lastPrice", 150.0)
        logger.info(f"Current {symbol} price: ${last_price}")
    except Exception as e:
        logger.error(f"Failed to fetch quote for {symbol}: {e}")
        return

    # Setup Stream
    stream_client = StreamClient(client)
    tracker = OrderStreamTracker()

    stream_client.start(receiver=tracker.handle, daemon=True)

    # Wait for login to complete
    time.sleep(3)

    # Subscribe to account activity
    correl_id = stream_client._streamer_info.get(
        "schwabClientCorrelId", "Account Activity"
    )
    stream_client.send(
        stream_client.account_activity(
            keys=correl_id,
            fields="subscription_key,account,message_type,message_data",
            command="SUBS",
        )
    )
    logger.info("Subscribed to Account Activity. Waiting 2 seconds...")
    time.sleep(2)

    active_orders = []

    try:
        # Configuration 1: Equity Sell Short Limit way above price
        sell_price = round(last_price * 2.0, 2)
        logger.info(f"\n--- Testing Equity Sell Short Limit at ${sell_price} ---")
        sell_order = equity_sell_short_limit(symbol, 1, sell_price).build()
        logger.info(f"Placing order payload: {sell_order}")
        resp_sell = client.place_order(account_hash, sell_order)
        sell_id = extract_order_id(resp_sell)

        if sell_id:
            logger.info(f"Successfully placed Sell order: ID {sell_id}")
            active_orders.append(sell_id)
        else:
            logger.error(f"Failed to extract order ID. Response: {resp_sell.text}")

        # Configuration 2: Equity Buy Limit way below price
        buy_price = round(last_price * 0.5, 2)
        logger.info(f"\n--- Testing Equity Buy Limit at ${buy_price} ---")
        buy_order = equity_buy_limit(symbol, 1, buy_price).build()
        logger.info(f"Placing order payload: {buy_order}")
        resp_buy = client.place_order(account_hash, buy_order)
        buy_id = extract_order_id(resp_buy)

        if buy_id:
            logger.info(f"Successfully placed Buy order: ID {buy_id}")
            active_orders.append(buy_id)
        else:
            logger.error(f"Failed to extract order ID. Response: {resp_buy.text}")

        # Configuration 3: Equity Buy Limit GTC way below price
        buy_price_2 = round(last_price * 0.4, 2)
        logger.info(f"\n--- Testing Equity Buy Limit (GTC) at ${buy_price_2} ---")
        buy_gtc_order = (
            equity_buy_limit(symbol, 1, buy_price_2)
            .set_duration(Duration.GOOD_TILL_CANCEL)
            .build()
        )
        logger.info(f"Placing order payload: {buy_gtc_order}")
        resp_buy_2 = client.place_order(account_hash, buy_gtc_order)
        buy_id_2 = extract_order_id(resp_buy_2)

        if buy_id_2:
            logger.info(f"Successfully placed 2nd Buy order: ID {buy_id_2}")
            active_orders.append(buy_id_2)
        else:
            logger.error(f"Failed to extract order ID. Response: {resp_buy_2.text}")

        # Wait to observe the stream updates
        logger.info(
            "\nWaiting 10 seconds to observe stream updates for order creation..."
        )
        time.sleep(10)

        logger.info(
            f"Observed {len(tracker.events)} Account Activity events during this window."
        )
        for idx, event in enumerate(tracker.events):
            logger.info(f"Event {idx + 1}: {event}")

    except Exception as e:
        logger.error(f"Error during order placement/streaming: {e}")

    finally:
        # Cancel all active orders
        logger.info("\n--- Canceling orders ---")
        for order_id in active_orders:
            try:
                client.cancel_order(account_hash, order_id)
                logger.info(f"Successfully canceled order: {order_id}")
            except Exception as e:
                logger.error(f"Failed to cancel order {order_id}: {e}")

        # Wait to observe cancel events on stream
        logger.info("Waiting 10 seconds to observe cancel events...")
        time.sleep(10)

        logger.info(
            f"Observed {len(tracker.events)} total Account Activity events so far."
        )
        for idx, event in enumerate(tracker.events):
            logger.info(f"Event {idx + 1}: {event}")

        stream_client.stop()
        logger.info("Test completed.")


if __name__ == "__main__":
    main()
