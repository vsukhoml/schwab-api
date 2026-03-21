import logging
import os
import sys
import time

from dotenv import load_dotenv

from schwab_api.account_manager import AccountManager
from schwab_api.client import Client
from schwab_api.stream import StreamClient
from schwab_api.stream_parsers import StreamResponseHandler

# Configure logging
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_account_manager")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)


def main():
    load_dotenv()

    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")

    if not app_key or not app_secret:
        logger.error(
            "SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in the environment or .env file."
        )
        sys.exit(1)

    client = Client(app_key, app_secret, logger=logger)
    logger.info("Client initialized successfully.")

    # Initialize Streamer and AccountManager
    stream_client = StreamClient(client)
    account_manager = AccountManager(client, stream_client)

    # Set up stream handling
    root_handler = StreamResponseHandler()
    root_handler.add_handler(account_manager)

    logger.info("Updating Account Manager via REST...")
    try:
        account_manager.update()
        logger.info(
            f"Loaded {len(account_manager.accounts)} accounts and {len(account_manager.positions)} unique positions."
        )

        for acc_num, acc in account_manager.accounts.items():
            primary = " [PRIMARY]" if acc.get("primaryAccount") else ""
            nick = acc.get("nickName") or "(no nickname)"
            logger.info(
                f"  Account {acc_num}{primary}: {nick!r} | type={acc.get('type')} | "
                f"cash=${acc.get('cashBalance', 0):.2f} | liq=${acc.get('liquidationValue', 0):.2f}"
            )

        if not account_manager.positions:
            logger.warning(
                "No positions found! Stream updates will have nothing to track."
            )
        else:
            for symbol in account_manager.positions.keys():
                totals = account_manager.get_position_totals(symbol)
                logger.info(
                    f"Initial {symbol}: Qty {totals['netQuantity']} | Market Value: ${totals['marketValue']:.2f}"
                )

    except Exception as e:
        logger.error(f"Failed to update AccountManager: {e}")
        return

    import datetime
    import json

    os.makedirs("e2e_dumps", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_file = os.path.join("e2e_dumps", f"stream_dump_{timestamp}.jsonl")

    def raw_dump_receiver(message):
        with open(dump_file, "a") as f:
            if isinstance(message, dict):
                f.write(json.dumps(message) + "\n")
            else:
                f.write(str(message) + "\n")
        root_handler.handle(message)

    logger.info("Starting StreamClient to receive real-time price updates...")
    # This will automatically call _subscribe_positions on the AccountManager
    stream_client.start(receiver=raw_dump_receiver, daemon=True)

    try:
        # Let it stream for 15 seconds
        logger.info("Waiting for stream updates for 15 seconds...")
        for _ in range(3):
            time.sleep(5)
            # Print updated totals
            logger.info("--- Current Real-time Portfolio State ---")
            for symbol in list(account_manager.positions.keys())[
                :5
            ]:  # just print first 5 to avoid spam
                totals = account_manager.get_position_totals(symbol)
                logger.info(
                    f"Live {symbol}: Qty {totals['netQuantity']} | Updated Market Value: ${totals['marketValue']:.2f}"
                )
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        logger.info("Stopping StreamClient...")
        stream_client.stop()


if __name__ == "__main__":
    main()
