import logging
import threading
from typing import Any, Dict, Optional

from .client import Client
from .stream import StreamClient
from .stream_parsers import StreamResponseHandler

logger = logging.getLogger(__name__)


class AccountManager(StreamResponseHandler):
    """
    A utility class to easily manage and aggregate balances, positions, and accounts.

    It abstracts away the need to manually join `linked_accounts` (hashes) with `account_details`.
    It can optionally connect to a `StreamClient` to maintain real-time position values by
    automatically subscribing to Level 1 data for all active position symbols, and automatically
    subscribing to Account Activity to refresh REST position quantities when trades execute.

    Attributes:
        client (Client): The active Schwab REST API client.
        stream_client (Optional[StreamClient]): The optional stream client for real-time updates.
        accounts (Dict[int, Dict[str, Any]]): Dictionary of account data keyed by account number.
            Contains 'hashValue', 'type', 'cashBalance', and 'liquidationValue'.
        positions (Dict[str, Dict[int, Dict[str, Any]]]): Dictionary of position data.
            Keyed by symbol, then by account number. Contains quantity, price, and market value details.
        quotes (Dict[str, Dict[str, Any]]): Dictionary of cached quotes used for real-time market value
            updates. Automatically populated if a stream_client is provided.
    """

    def __init__(self, client: Client, stream_client: Optional[StreamClient] = None):
        """
        Initializes the AccountManager.

        Args:
            client (Client): An initialized REST API client.
            stream_client (Optional[StreamClient]): An optional initialized StreamClient. If provided,
                the AccountManager will automatically subscribe to position symbols and keep market
                values up to date via streaming.
        """
        super().__init__()
        self.client = client
        self.stream_client = stream_client
        self.accounts: Dict[int, Dict[str, Any]] = {}
        self.positions: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self.quotes: Dict[str, Dict[str, Any]] = {}
        self._update_lock = threading.Lock()

    def update(self) -> None:
        """
        Fetches linked accounts and all positions from the REST API, aggregating them into easy-to-use structures.

        This method performs the following:
        1. Calls the `linked_accounts()` endpoint to map raw account numbers to their respective encrypted hashes.
        2. Calls the `account_details_all(fields="positions")` endpoint to retrieve current balances and positions.
        3. Aggregates the balances into the `self.accounts` dictionary.
        4. Aggregates the positions into the `self.positions` dictionary, grouping them by symbol and then by account.
        5. If a `stream_client` is attached, it automatically invokes `_subscribe_positions()` to begin
           tracking real-time market values for those symbols, and `_subscribe_account_activity()` to track trade fills.
        """
        # Ensure thread safety in case it's called from a background thread
        with self._update_lock:
            # Fetch linked accounts
            linked = self.client.linked_accounts().json()
            for account in linked:
                acc_num = int(account["accountNumber"])
                if acc_num not in self.accounts:
                    self.accounts[acc_num] = {
                        "hashValue": account["hashValue"],
                        "type": "UNKNOWN",
                        "cashBalance": 0.0,
                        "liquidationValue": 0.0,
                    }

            # Fetch positions for all linked accounts
            account_details = self.client.account_details_all(fields="positions").json()

            # Clear old positions so closed positions don't linger
            self.positions.clear()

            for account in account_details:
                security_account = account.get("securitiesAccount", {})
                acc_num_str = security_account.get("accountNumber")
                if not acc_num_str:
                    continue

                acc_num = int(acc_num_str)
                if acc_num in self.accounts:
                    self.accounts[acc_num]["type"] = security_account.get(
                        "type", "UNKNOWN"
                    )
                    balances = security_account.get("currentBalances", {})
                    self.accounts[acc_num]["cashBalance"] = balances.get(
                        "cashBalance", balances.get("cashAvailableForTrading", 0.0)
                    )
                    self.accounts[acc_num]["liquidationValue"] = balances.get(
                        "liquidationValue", 0.0
                    )

                account_positions = security_account.get("positions", [])
                for position in account_positions:
                    instrument = position.get("instrument", {})
                    symbol = instrument.get("symbol")
                    if not symbol:
                        continue

                    if symbol not in self.positions:
                        self.positions[symbol] = {}

                    self.positions[symbol][acc_num] = {
                        "longQuantity": position.get("longQuantity", 0.0),
                        "shortQuantity": position.get("shortQuantity", 0.0),
                        "averagePrice": position.get("averagePrice", 0.0),
                        "settledLongQuantity": position.get("settledLongQuantity", 0.0),
                        "settledShortQuantity": position.get(
                            "settledShortQuantity", 0.0
                        ),
                        "marketValue": position.get("marketValue", 0.0),
                        "assetType": instrument.get("assetType", "UNKNOWN"),
                    }

                    # If we had streamed a quote before the REST update, restore the real-time market value
                    if symbol in self.quotes:
                        price = self.quotes[symbol].get(
                            "mark_price", self.quotes[symbol].get("last_price", 0.0)
                        )
                        net_qty = (
                            self.positions[symbol][acc_num]["longQuantity"]
                            - self.positions[symbol][acc_num]["shortQuantity"]
                        )
                        if price > 0:
                            self.positions[symbol][acc_num]["marketValue"] = (
                                net_qty * price
                            )

        if self.stream_client:
            if self.positions:
                self._subscribe_positions()
            self._subscribe_account_activity()

    def _subscribe_positions(self) -> None:
        """
        Automatically subscribes to Level 1 data for all current position symbols.

        Issues a `LEVELONE_EQUITIES` "ADD" command to the attached `StreamClient`.
        This requests `symbol`, `bid_price`, `ask_price`, `last_price`, and `mark_price`
        so that `on_level_one_equity` can continuously update position market values.
        """
        if not self.stream_client:
            return

        symbols = list(self.positions.keys())
        # Add basic fields needed for updating positions
        self.stream_client.send(
            self.stream_client.level_one_equities(
                keys=symbols,
                fields=["symbol", "bid_price", "ask_price", "last_price", "mark_price"],
                command="ADD",
            )
        )

    def _subscribe_account_activity(self) -> None:
        """
        Subscribes to the Account Activity stream to track orders and balance changes.
        """
        if not self.stream_client:
            return

        streamer_info = self.stream_client._streamer_info or {}
        correl_id = streamer_info.get("schwabClientCorrelId", "Account Activity")

        self.stream_client.send(
            self.stream_client.account_activity(
                keys=correl_id,
                fields="subscription_key,account,message_type,message_data",
                command="SUBS",
            )
        )

    def on_level_one_equity(self, update: Dict[str, Any]) -> None:
        """
        Callback automatically triggered when Level 1 Equity data is received via the stream.

        This method will cache the incoming quote data in `self.quotes` and, if the symbol is
        present in `self.positions`, it will recalculate the real-time `marketValue` for all
        accounts holding that position based on the streamed `mark_price` (or `last_price` if mark is unavailable).

        Args:
            update (Dict[str, Any]): The parsed Level 1 Equity payload.
        """
        symbol = update.get("symbol")
        if not symbol:
            return

        if symbol not in self.quotes:
            self.quotes[symbol] = {}

        for key in ["last_price", "bid_price", "ask_price", "mark_price"]:
            if key in update:
                self.quotes[symbol][key] = float(update[key])

        # Recalculate market value for positions
        if symbol in self.positions:
            # Prefer mark_price, then last_price
            price = self.quotes[symbol].get(
                "mark_price", self.quotes[symbol].get("last_price", 0.0)
            )
            if price > 0:
                for acc_num in self.positions[symbol]:
                    pos = self.positions[symbol][acc_num]
                    net_qty = pos["longQuantity"] - pos["shortQuantity"]
                    pos["marketValue"] = net_qty * price

    def on_account_activity(self, update: Dict[str, Any]) -> None:
        """
        Callback triggered when Account Activity events occur.

        Specifically monitors for `OrderFill` messages to automatically trigger a background
        re-sync of account quantities and balances via `self.update()`.

        Args:
            update (Dict[str, Any]): The parsed Account Activity payload.
        """
        message_type = update.get("message_type")

        # We listen for order fills which means our quantities have changed.
        # Alternatively, we could monitor "Position" or "Balance" updates.
        if message_type == "OrderFill":
            logger.info(
                "Order fill detected via Stream! Initiating background REST refresh of positions and balances."
            )
            # Run update in a separate thread so we don't block the WebSocket receiver loop.
            threading.Thread(target=self.update, daemon=True).start()

    def get_position_totals(self, symbol: str) -> Dict[str, float]:
        """
        Returns the aggregate position total for a specific symbol across all linked accounts.

        Args:
            symbol (str): The ticker symbol to aggregate (e.g., 'AAPL').

        Returns:
            Dict[str, float]: A dictionary containing total `longQuantity`, `shortQuantity`,
                `settledLongQuantity`, `settledShortQuantity`, `marketValue`, and `netQuantity`.
        """
        accounts_holding = self.positions.get(symbol, {})
        long_qty = 0.0
        short_qty = 0.0
        settled_long = 0.0
        settled_short = 0.0
        market_value = 0.0

        for account_holding in accounts_holding.values():
            long_qty += account_holding.get("longQuantity", 0.0)
            short_qty += account_holding.get("shortQuantity", 0.0)
            settled_long += account_holding.get("settledLongQuantity", 0.0)
            settled_short += account_holding.get("settledShortQuantity", 0.0)
            market_value += account_holding.get("marketValue", 0.0)

        return {
            "longQuantity": long_qty,
            "shortQuantity": short_qty,
            "settledLongQuantity": settled_long,
            "settledShortQuantity": settled_short,
            "marketValue": market_value,
            "netQuantity": long_qty - short_qty,
        }
