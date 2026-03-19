import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from schwab_api.client import Client
from schwab_api.utils import parse_option_chain_to_df, parse_price_history_to_df

DUMP_DIR = Path("e2e_dumps")
DUMP_DIR.mkdir(exist_ok=True)

# Configure logging
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_data_frames")
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)


def dump_dataframe(name: str, df) -> None:
    """Saves the DataFrame to a CSV file and prints the head."""
    DUMP_DIR.mkdir(exist_ok=True)
    file_path = DUMP_DIR / f"{name}.csv"

    if df is None or df.empty:
        logger.warning(f"DataFrame {name} is empty or None. Not dumping.")
        return

    # Print the content of the data frame (head)
    logger.info(f"--- DataFrame Content: {name} ---")
    print(df.head(10).to_string())
    print("-" * 40)

    # Dump to CSV
    df.to_csv(file_path)
    logger.info(f"Saved DataFrame to {file_path}")


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

    tickers = ["AAPL", "GOOG"]

    for ticker in tickers:
        logger.info(f"--- Processing {ticker} ---")

        # 1. Option Chains
        logger.info(f"Testing parse_option_chain_to_df for {ticker}...")
        try:
            chain_resp = client.option_chains(ticker, strikeCount=10)
            chain_json = chain_resp.json()

            # Convert to DataFrame
            df_chain = parse_option_chain_to_df(chain_json)
            dump_dataframe(f"{ticker}_option_chain", df_chain)
        except Exception as e:
            logger.error(f"Failed to process option chains for {ticker}: {e}")

        # 2. Price History
        logger.info(f"Testing parse_price_history_to_df for {ticker}...")
        try:
            price_resp = client.price_history(
                ticker, periodType="day", period=5, frequencyType="minute", frequency=5
            )
            price_json = price_resp.json()

            # Convert to DataFrame
            df_history = parse_price_history_to_df(price_json)
            dump_dataframe(f"{ticker}_price_history", df_history)
        except Exception as e:
            logger.error(f"Failed to process price history for {ticker}: {e}")


if __name__ == "__main__":
    main()
