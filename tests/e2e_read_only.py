import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from schwab_api.client import Client
from schwab_api.stream import StreamClient

DUMP_DIR = Path("e2e_dumps")
DUMP_DIR.mkdir(exist_ok=True)

# Configure logging
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e_test")
logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler(DUMP_DIR / "e2e_test.log")
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)


def dump_response(name: str, data: any):
    """Saves the response data to a JSON file for analysis."""
    DUMP_DIR.mkdir(exist_ok=True)
    file_path = DUMP_DIR / f"{name}.json"

    # Handle DataFrame if pandas is installed and data is a DataFrame
    try:
        import pandas as pd

        if isinstance(data, pd.DataFrame):
            data.to_json(file_path, orient="records", date_format="iso", indent=2)
            logger.info(f"Saved DataFrame to {file_path}")
            return
    except ImportError:
        pass

    with open(file_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Saved {name} to {file_path}")


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

    # 1. Linked Accounts
    logger.info("Testing linked_accounts...")
    try:
        accounts_resp = client.linked_accounts()
        accounts = accounts_resp.json()
        dump_response("linked_accounts", accounts)
    except Exception as e:
        logger.error(f"linked_accounts failed: {e}")
        return

    if not accounts:
        logger.warning("No linked accounts found, cannot test account-specific APIs.")
        account_hashes = []
    else:
        account_hashes = [
            (acc.get("accountNumber", "unknown"), acc.get("hashValue"))
            for acc in accounts
        ]

    # 2. User Preferences
    logger.info("Testing user_preferences...")
    try:
        prefs_resp = client.user_preferences()
        dump_response("user_preferences", prefs_resp.json())
    except Exception as e:
        logger.error(f"user_preferences failed: {e}")

    # 3. Account Details All
    logger.info("Testing account_details_all...")
    try:
        details_all_resp = client.account_details_all(fields="positions")
        data = details_all_resp.json()
        dump_response("account_details_all", data)

        # Dump positions table
        total_worth = 0.0
        print("\n" + "=" * 80)
        print(
            f"{'Account':<12} | {'Ticker':<10} | {'Quantity':<10} | {'Price':<12} | {'Total':<15}"
        )
        print("-" * 80)

        for account in data:
            sec_acc = account.get("securitiesAccount", {})
            acc_num = sec_acc.get("accountNumber", "Unknown")
            positions = sec_acc.get("positions", [])

            acc_worth = sec_acc.get("currentBalances", {}).get("liquidationValue", 0.0)
            total_worth += acc_worth

            for p in positions:
                ticker = p.get("instrument", {}).get("symbol", "UNKNOWN")
                qty = p.get("longQuantity", 0.0) - p.get("shortQuantity", 0.0)
                if qty == 0.0:
                    qty = p.get("settledLongQuantity", 0.0) - p.get(
                        "settledShortQuantity", 0.0
                    )

                total = p.get("marketValue", 0.0)

                # Calculate current price, safeguard against div by zero
                if qty != 0:
                    price = abs(total / qty)
                else:
                    price = 0.0

                print(
                    f"{acc_num:<12} | {ticker:<10} | {qty:<10.4f} | ${price:<11.2f} | ${total:<14.2f}"
                )

        print("-" * 80)
        print(f"Total Portfolio Worth: ${total_worth:,.2f}")
        print("=" * 80 + "\n")
    except Exception as e:
        logger.error(f"account_details_all failed: {e}")

    # 4. Account Orders All
    logger.info("Testing account_orders_all...")
    try:
        orders_all_resp = client.account_orders_all(
            fromEnteredTime=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=60),
            toEnteredTime=datetime.datetime.now(datetime.timezone.utc),
        )
        dump_response("account_orders_all", orders_all_resp.json())
    except Exception as e:
        logger.error(f"account_orders_all failed: {e}")

    for account_number, account_hash in account_hashes:
        if not account_hash:
            continue

        suffix = f"_{account_number}"
        logger.info(f"Testing APIs for account {account_number}...")

        # 5. Account Details (Single)
        logger.info(f"Testing account_details for {account_number}...")
        try:
            details_resp = client.account_details(account_hash, fields="positions")
            dump_response(f"account_details{suffix}", details_resp.json())
        except Exception as e:
            logger.error(f"account_details failed for {account_number}: {e}")

        # 6. Account Orders
        logger.info(f"Testing account_orders for {account_number}...")
        try:
            orders_resp = client.account_orders(
                account_hash,
                fromEnteredTime=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=60),
                toEnteredTime=datetime.datetime.now(datetime.timezone.utc),
            )
            dump_response(f"account_orders{suffix}", orders_resp.json())
        except Exception as e:
            logger.error(f"account_orders failed for {account_number}: {e}")

        # 7. Transactions
        logger.info(f"Testing transactions for {account_number}...")
        transaction_id = None
        try:
            # 60 day lookback
            transactions_resp = client.transactions(
                account_hash,
                startDate=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=60),
                endDate=datetime.datetime.now(datetime.timezone.utc),
                types="TRADE",
            )
            transactions_data = transactions_resp.json()
            dump_response(f"transactions{suffix}", transactions_data)

            # 180 day lookback
            logger.info(f"Testing 180-day transaction history for {account_number}...")
            tx_180 = client.transactions(
                account_hash,
                startDate=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=180),
                endDate=datetime.datetime.now(datetime.timezone.utc),
                types="TRADE",
            )
            dump_response(f"transactions_180d{suffix}", tx_180.json())

            if isinstance(transactions_data, list) and len(transactions_data) > 0:
                transaction_id = transactions_data[0].get("activityId")
        except Exception as e:
            logger.error(f"transactions failed for {account_number}: {e}")

        # 8. Transaction Details
        if transaction_id:
            logger.info(f"Testing transaction_details for {account_number}...")
            try:
                tx_details_resp = client.transaction_details(
                    account_hash, transaction_id
                )
                dump_response(f"transaction_details{suffix}", tx_details_resp.json())
            except Exception as e:
                logger.error(f"transaction_details failed for {account_number}: {e}")

    # 9. Quotes
    logger.info("Testing quotes...")
    try:
        quotes_resp = client.quotes(["AAPL", "MSFT"])
        dump_response("quotes", quotes_resp.json())
    except Exception as e:
        logger.error(f"quotes failed: {e}")

    # 10. Quote (Single)
    logger.info("Testing quote...")
    try:
        quote_resp = client.quote("AAPL")
        dump_response("quote", quote_resp.json())
    except Exception as e:
        logger.error(f"quote failed: {e}")

    # 11. Option Chains
    logger.info("Testing option_chains...")
    try:
        chain_resp = client.option_chains("AAPL", strikeCount=5)
        dump_response("option_chains", chain_resp.json())
    except Exception as e:
        logger.error(f"option_chains failed: {e}")

    # 12. Option Expiration Chain
    logger.info("Testing option_expiration_chain...")
    try:
        exp_chain_resp = client.option_expiration_chain("AAPL")
        dump_response("option_expiration_chain", exp_chain_resp.json())
    except Exception as e:
        logger.error(f"option_expiration_chain failed: {e}")

    # 13. Price History
    logger.info("Testing price_history...")
    try:
        price_resp = client.price_history(
            "AAPL", periodType="day", period=1, frequencyType="minute", frequency=1
        )
        dump_response("price_history", price_resp.json())
    except Exception as e:
        logger.error(f"price_history failed: {e}")

    # 14. Instruments
    logger.info("Testing instruments...")
    cusip_id = None
    try:
        instruments_resp = client.instruments("AAPL", projection="fundamental")
        instruments_data = instruments_resp.json()
        dump_response("instruments", instruments_data)

        instruments_list = instruments_data.get("instruments", [])
        if instruments_list:
            cusip_id = instruments_list[0].get("cusip")
    except Exception as e:
        logger.error(f"instruments failed: {e}")

    # 15. Instrument CUSIP
    if cusip_id:
        logger.info("Testing instrument_cusip...")
        try:
            cusip_resp = client.instrument_cusip(cusip_id)
            dump_response("instrument_cusip", cusip_resp.json())
        except Exception as e:
            logger.error(f"instrument_cusip failed: {e}")

    # 16. Movers
    logger.info("Testing movers...")
    try:
        movers_resp = client.movers("$DJI", sort="VOLUME", frequency=0)
        dump_response("movers", movers_resp.json())

        # Test movers with different parameters
        movers_spx = client.movers("$SPX", sort="AVERAGE_PERCENT_VOLUME", frequency=10)
        dump_response("movers_spx_avg_vol", movers_spx.json())
    except Exception as e:
        logger.error(f"movers failed: {e}")

    # 16b. Price History for Indices
    logger.info("Testing price_history for index $STOXX50E...")
    try:
        ph_stoxx = client.price_history(
            "$STOXX50E", periodType="year", period=1, frequencyType="daily"
        )
        dump_response("price_history_stoxx50e", ph_stoxx.json())
    except Exception as e:
        logger.error(f"price_history for $STOXX50E failed: {e}")

    # 16c. Instrument Search by Regex
    logger.info("Testing instrument search by regex...")
    try:
        # Search for $D.* (e.g. $DJI, $DJT)
        regex_indices = client.instruments("\\$D.*", "symbol-regex")
        dump_response("instruments_regex_indices", regex_indices.json())

        # Search for GOOG.*
        regex_goog = client.instruments("GOOG.*", "symbol-regex")
        dump_response("instruments_regex_goog", regex_goog.json())
    except Exception as e:
        logger.error(f"instrument regex search failed: {e}")

    # 16d. Instrument CUSIP Lookups
    logger.info("Testing specific CUSIP lookups...")
    cusips = ["02079K305", "02079K107", "92826C839"]
    for c in cusips:
        try:
            c_resp = client.instrument_cusip(c)
            dump_response(f"instrument_cusip_{c}", c_resp.json())

            # Also test with fundamental projection
            f_resp = client.instruments(c, "fundamental")
            dump_response(f"instrument_fundamental_{c}", f_resp.json())
        except Exception as e:
            logger.error(f"CUSIP lookup failed for {c}: {e}")

    # 16e. Advanced Option Chains (Strategies)
    logger.info("Testing advanced option chain strategies...")
    strategies = [("CONDOR", 28, True), ("COVERED", 28, True), ("SINGLE", 30, False)]
    for strat, dte, include_quote in strategies:
        try:
            logger.info(f"Requesting option_chains for GOOG with strategy={strat}...")
            strat_resp = client.option_chains(
                "GOOG",
                strategy=strat,
                daysToExpiration=dte,
                includeUnderlyingQuote=include_quote,
            )
            dump_response(
                f"option_chains_{strat}_dte{dte}_quote{include_quote}",
                strat_resp.json(),
            )
        except Exception as e:
            logger.error(f"option_chains strategy {strat} failed: {e}")

    # 17. Market Hours
    logger.info("Testing market_hours...")
    try:
        hours_resp = client.market_hours(["equity", "option"])
        dump_response("market_hours", hours_resp.json())
    except Exception as e:
        logger.error(f"market_hours failed: {e}")

    # 18. Market Hours for Market
    logger.info("Testing market_hours_for_market...")
    try:
        hours_market_resp = client.market_hours_for_market("equity")
        dump_response("market_hours_for_market", hours_market_resp.json())
    except Exception as e:
        logger.error(f"market_hours_for_market failed: {e}")

    # 19. Get Daily Price History (Helper)
    logger.info("Testing get_daily_price_history...")
    try:
        start_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=7
        )
        daily_df = client.get_daily_price_history("AAPL", start_date=start_date)
        dump_response("get_daily_price_history", daily_df)
    except Exception as e:
        logger.error(f"get_daily_price_history failed: {e}")

    # 20. Get Fundamentals (Helper)
    logger.info("Testing get_fundamentals...")
    try:
        funds = client.get_fundamentals(["AAPL", "MSFT"])
        dump_response("get_fundamentals", funds)
    except Exception as e:
        logger.error(f"get_fundamentals failed: {e}")

    # 21. StreamClient
    logger.info("Testing StreamClient...")
    try:
        from schwab_api import get_numeric_fields
        from schwab_api.stream_parsers import StreamResponseHandler
        from schwab_api.trading import OptionChainAnalyzer

        # Dynamically discover an option to track
        goog_chain = client.option_chains("GOOG", strikeCount=2).json()
        analyzer = OptionChainAnalyzer(goog_chain)

        # Get closest call to the money with low DTE
        candidates = analyzer.filter_options(option_type="CALL", min_dte=0, max_dte=30)

        if not candidates.empty:
            # Sort by lowest DTE first, then by closest delta to 0.50 (ATM)
            candidates["delta_diff"] = (candidates["delta"].abs() - 0.5).abs()
            sorted_candidates = candidates.sort_values(
                by=["days_to_expiration", "delta_diff"]
            )
            target_option_symbol = sorted_candidates.index[0]
            logger.info(
                f"Dynamically selected option for streaming: {target_option_symbol}"
            )
        else:
            target_option_symbol = "GOOG  250411C00160000"
            logger.warning(
                "Could not dynamically find an option, falling back to hardcoded symbol."
            )

        stream_messages = []

        class TestStreamHandler(StreamResponseHandler):
            def on_level_one_equity(self, update: dict) -> None:
                stream_messages.append({"type": "EQUITY", "data": update})

            def on_level_one_option(self, update: dict) -> None:
                stream_messages.append({"type": "OPTION", "data": update})

            def on_level_one_future(self, update: dict) -> None:
                stream_messages.append({"type": "FUTURE", "data": update})

            def on_level_one_future_option(self, update: dict) -> None:
                stream_messages.append({"type": "FUTURE_OPTION", "data": update})

            def on_level_one_forex(self, update: dict) -> None:
                stream_messages.append({"type": "FOREX", "data": update})

            def on_screener_item(
                self, service: str, screener_key: str, item: dict
            ) -> None:
                stream_messages.append(
                    {"type": "SCREENER", "key": screener_key, "data": item}
                )

            def on_chart_equity(self, update: dict) -> None:
                stream_messages.append({"type": "CHART_EQUITY", "data": update})

            def on_chart_future(self, update: dict) -> None:
                stream_messages.append({"type": "CHART_FUTURE", "data": update})

            def on_book_update(self, service: str, update: dict) -> None:
                stream_messages.append(
                    {"type": "BOOK", "service": service, "data": update}
                )

            def on_account_activity(self, update: dict) -> None:
                stream_messages.append({"type": "ACCT_ACTIVITY", "data": update})

            def on_response(self, response: dict) -> None:
                stream_messages.append({"type": "RESPONSE", "data": response})

            def on_unknown_event(self, service: str, update: dict) -> None:
                stream_messages.append(
                    {"type": "UNKNOWN", "service": service, "data": update}
                )

        handler = TestStreamHandler()
        stream_client = StreamClient(client)

        # 1. Equities (Demonstrating get_numeric_fields)
        equity_fields = get_numeric_fields(
            "LEVELONE_EQUITIES",
            [
                "symbol",
                "bid_price",
                "ask_price",
                "last_price",
                "bid_size",
                "ask_size",
                "total_volume",
            ],
        )
        stream_client.send(
            stream_client.level_one_equities(
                "AAPL,MSFT,GOOG,AMD,INTC,TSLA", equity_fields
            )
        )

        # 2. Options (Demonstrating get_numeric_fields)
        option_fields = get_numeric_fields(
            "LEVELONE_OPTIONS",
            [
                "symbol",
                "bid_price",
                "ask_price",
                "last_price",
                "delta",
                "gamma",
                "theta",
                "vega",
            ],
        )
        stream_client.send(
            stream_client.level_one_options(target_option_symbol, option_fields)
        )

        # 3. Futures
        stream_client.send(
            stream_client.level_one_futures("/ES,/NQ,/CL", "0,1,2,3,4,5,6,7,8")
        )

        # 4. Forex
        stream_client.send(
            stream_client.level_one_forex("EUR/USD,USD/JPY", "0,1,2,3,4,5,6,7,8")
        )

        # 5. Charts
        stream_client.send(stream_client.chart_equity("AAPL,MSFT", "0,1,2,3,4,5,6,7,8"))
        stream_client.send(stream_client.chart_futures("/ES,/NQ", "0,1,2,3,4,5,6"))

        # 6. Order Books
        stream_client.send(stream_client.nasdaq_book("AAPL,MSFT", "0,1,2,3"))
        stream_client.send(stream_client.options_book(target_option_symbol, "0,1,2,3"))

        # 7. Screeners
        stream_client.send(
            stream_client.screener_equity(
                ["EQUITY_ALL_PERCENT_CHANGE_UP_0", "$SPX_PERCENT_CHANGE_UP_0"],
                "0,1,2,3,4",
            )
        )
        stream_client.send(
            stream_client.screener_option(
                ["OPTION_ALL_PERCENT_CHANGE_UP_0"],
                "0,1,2,3,4",
            )
        )

        # 8. Account Activity
        stream_client.send(
            stream_client.account_activity("Account Activity", "0,1,2,3")
        )

        # Start Stream
        stream_client.start(receiver=handler.handle, daemon=True)

        # allow stream to connect and gather some messages
        time.sleep(15)
        stream_client.stop()

        dump_response("stream_output", stream_messages)
    except Exception as e:
        logger.error(f"StreamClient failed: {e}")

    logger.info(
        "End-to-end read-only tests completed. Check the 'e2e_dumps' directory for outputs."
    )


if __name__ == "__main__":
    main()
