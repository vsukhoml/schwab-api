import datetime
import json
import logging
import os
import sys
import time
from typing import Any, Dict

from dotenv import load_dotenv

from schwab_api.client import Client
from schwab_api.stream import StreamClient
from schwab_api.stream_parsers import StreamResponseHandler

# Configure logging
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_stream")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

os.makedirs("e2e_dumps", exist_ok=True)
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
dump_file_raw = os.path.join("e2e_dumps", f"stream_all_raw_{timestamp}.jsonl")
dump_file_parsed = os.path.join("e2e_dumps", f"stream_all_parsed_{timestamp}.jsonl")


class AllStreamsHandler(StreamResponseHandler):
    def __init__(self, parsed_file_path: str):
        super().__init__()
        self.parsed_file_path = parsed_file_path

    def _log_parsed(self, event_type: str, data: Any):
        with open(self.parsed_file_path, "a") as f:
            f.write(json.dumps({"event_type": event_type, "data": data}) + "\n")

    def on_level_one_equity(self, update: Dict[str, Any]) -> None:
        logger.info(f"LEVELONE_EQUITIES: {update.get('key')}")
        self._log_parsed("LEVELONE_EQUITIES", update)

    def on_level_one_option(self, update: Dict[str, Any]) -> None:
        logger.info(f"LEVELONE_OPTIONS: {update.get('key')}")
        self._log_parsed("LEVELONE_OPTIONS", update)

    def on_level_one_future(self, update: Dict[str, Any]) -> None:
        logger.info(f"LEVELONE_FUTURES: {update.get('key')}")
        self._log_parsed("LEVELONE_FUTURES", update)

    def on_level_one_future_option(self, update: Dict[str, Any]) -> None:
        logger.info(f"LEVELONE_FUTURES_OPTIONS: {update.get('key')}")
        self._log_parsed("LEVELONE_FUTURES_OPTIONS", update)

    def on_level_one_forex(self, update: Dict[str, Any]) -> None:
        logger.info(f"LEVELONE_FOREX: {update.get('key')}")
        self._log_parsed("LEVELONE_FOREX", update)

    def on_chart_equity(self, update: Dict[str, Any]) -> None:
        logger.info(f"CHART_EQUITY: {update.get('key')}")
        self._log_parsed("CHART_EQUITY", update)

    def on_chart_future(self, update: Dict[str, Any]) -> None:
        logger.info(f"CHART_FUTURES: {update.get('key')}")
        self._log_parsed("CHART_FUTURES", update)

    def on_screener_item(self, service: str, key: str, item: Dict[str, Any]) -> None:
        logger.info(f"SCREENER ({service} - {key}): {item.get('symbol')}")
        self._log_parsed(f"SCREENER_{service}", {"key": key, "item": item})

    def on_book_update(self, service: str, update: Dict[str, Any]) -> None:
        logger.info(f"BOOK ({service}): {update.get('key')}")
        self._log_parsed(f"BOOK_{service}", update)

    def on_account_activity(self, update: Dict[str, Any]) -> None:
        logger.info(
            f"ACCT_ACTIVITY: {update.get('key')} | {update.get('message_type')}"
        )
        self._log_parsed("ACCT_ACTIVITY", update)

    def on_response(self, response: Dict[str, Any]) -> None:
        logger.info(
            f"RESPONSE: {response.get('service')} - {response.get('command')} - {response.get('content', {}).get('msg')}"
        )
        self._log_parsed("RESPONSE", response)

    def on_unknown_event(self, service: str, update: Dict[str, Any]) -> None:
        logger.warning(f"UNKNOWN EVENT: {service} - {update.get('key')}")
        self._log_parsed("UNKNOWN_EVENT", {"service": service, "update": update})


def main():
    load_dotenv()

    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")

    if not app_key or not app_secret:
        logger.error("SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set.")
        sys.exit(1)

    client = Client(app_key, app_secret, logger=logger)
    logger.info("Client initialized successfully.")

    # Get a valid option symbol from the chain
    option_symbol = ""
    try:
        chain = client.option_chains("AAPL").json()
        if "callExpDateMap" in chain and chain["callExpDateMap"]:
            first_date = list(chain["callExpDateMap"].keys())[0]
            first_strike = list(chain["callExpDateMap"][first_date].keys())[0]
            option_symbol = chain["callExpDateMap"][first_date][first_strike][0][
                "symbol"
            ]
            logger.info(f"Found option symbol: {option_symbol}")
    except Exception as e:
        logger.error(f"Failed to fetch option chain: {e}")

    stream_client = StreamClient(client)
    handler = AllStreamsHandler(dump_file_parsed)

    def raw_dump_receiver(message):
        with open(dump_file_raw, "a") as f:
            if isinstance(message, dict):
                f.write(json.dumps(message) + "\n")
            else:
                f.write(str(message) + "\n")
        handler.handle(message)

    stream_client.start(receiver=raw_dump_receiver, daemon=True)
    time.sleep(3)  # Wait for login

    correl_id = stream_client._streamer_info.get(
        "schwabClientCorrelId", "Account Activity"
    )

    # Send subscriptions
    stream_client.send(
        stream_client.level_one_equities(keys="AAPL,MSFT,QQQ", fields="0,1,2,3")
    )

    if option_symbol:
        stream_client.send(
            stream_client.level_one_options(keys=option_symbol, fields="0,1,2,3")
        )
        stream_client.send(
            stream_client.options_book(keys=option_symbol, fields="0,1,2,3")
        )

    stream_client.send(stream_client.level_one_futures(keys="/ES", fields="0,1,2,3"))
    stream_client.send(stream_client.level_one_forex(keys="EUR/USD", fields="0,1,2,3"))
    stream_client.send(stream_client.chart_equity(keys="AAPL,MSFT", fields="0,1,2,3"))
    stream_client.send(stream_client.chart_futures(keys="/ES", fields="0,1,2,3"))
    stream_client.send(stream_client.nyse_book(keys="AAPL", fields="0,1,2,3"))
    stream_client.send(stream_client.nasdaq_book(keys="QQQ", fields="0,1,2,3"))
    stream_client.send(stream_client.screener_equity(keys="$SPX", fields="0,1,2,3,4"))
    stream_client.send(stream_client.screener_option(keys="$SPX", fields="0,1,2,3,4"))

    stream_client.send(
        stream_client.account_activity(
            keys=correl_id, fields="subscription_key,account,message_type,message_data"
        )
    )

    logger.info("Subscriptions sent. Waiting 20 seconds for data...")
    time.sleep(20)

    stream_client.stop()
    logger.info(
        f"Test completed. Raw data dumped to {dump_file_raw} and parsed to {dump_file_parsed}"
    )


if __name__ == "__main__":
    main()
