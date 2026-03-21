"""
End-to-end test: compute a VIX-style implied volatility for one or more symbols.

Run from the project root:
    source .venv/bin/activate && PYTHONPATH=. python3 tests/e2e_vix.py
"""

import logging
import math
import os
import sys

from dotenv import load_dotenv

from schwab_api.client import Client

log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_vix")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# Also show library warnings
logging.getLogger("schwab_api").setLevel(logging.DEBUG)
logging.getLogger("schwab_api").addHandler(console_handler)


def main():
    load_dotenv()

    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")

    if not app_key or not app_secret:
        logger.error("SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set.")
        sys.exit(1)

    client = Client(app_key, app_secret, logger=logger)
    logger.info("Client initialized.")

    symbols = ["GOOG", "AAPL", "SPY", "$SPX"]

    for symbol in symbols:
        logger.info("--- %s ---", symbol)
        try:
            iv = client.get_implied_volatility(
                symbol,
                target_days=30,
                strike_count=30,
                risk_free_rate=0.05,
            )
            if math.isnan(iv):
                logger.warning("%s: IV computation returned NaN", symbol)
            else:
                logger.info(
                    "%s  30-day IV (VIX-style): %.4f  (%.1f%%)", symbol, iv, iv * 100
                )
                assert iv > 0.0, f"{symbol}: IV must be positive, got {iv}"
                assert iv < 5.0, f"{symbol}: IV unrealistically large, got {iv}"
        except Exception as e:
            logger.error("%s: unexpected error: %s", symbol, e)
            raise


if __name__ == "__main__":
    main()
