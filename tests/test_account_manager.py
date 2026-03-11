import time
import unittest
from unittest.mock import MagicMock, patch

from schwab_api.account_manager import AccountManager
from schwab_api.client import Client
from schwab_api.stream import StreamClient


class TestAccountManager(unittest.TestCase):
    def setUp(self):
        # Mocking the client
        self.mock_client = MagicMock(spec=Client)

        self.linked_accounts_payload = [
            {"accountNumber": "123456", "hashValue": "hash123"},
            {"accountNumber": "654321", "hashValue": "hash654"},
        ]

        self.account_details_payload = [
            {
                "securitiesAccount": {
                    "accountNumber": "123456",
                    "type": "MARGIN",
                    "currentBalances": {
                        "cashBalance": 1000.0,
                        "liquidationValue": 5000.0,
                    },
                    "positions": [
                        {
                            "instrument": {"symbol": "AAPL", "assetType": "EQUITY"},
                            "longQuantity": 10.0,
                            "shortQuantity": 0.0,
                            "averagePrice": 150.0,
                            "marketValue": 1600.0,
                        }
                    ],
                }
            },
            {
                "securitiesAccount": {
                    "accountNumber": "654321",
                    "type": "CASH",
                    "currentBalances": {
                        "cashBalance": 200.0,
                        "liquidationValue": 200.0,
                    },
                    "positions": [
                        {
                            "instrument": {"symbol": "AAPL", "assetType": "EQUITY"},
                            "longQuantity": 5.0,
                            "shortQuantity": 0.0,
                            "averagePrice": 140.0,
                            "marketValue": 800.0,
                        },
                        {
                            "instrument": {"symbol": "MSFT", "assetType": "EQUITY"},
                            "longQuantity": 0.0,
                            "shortQuantity": 5.0,
                            "averagePrice": 300.0,
                            "marketValue": -1500.0,
                        },
                    ],
                }
            },
        ]

        # Setup mocks returning the expected json()
        mock_linked = MagicMock()
        mock_linked.json.return_value = self.linked_accounts_payload
        self.mock_client.linked_accounts.return_value = mock_linked

        mock_details = MagicMock()
        mock_details.json.return_value = self.account_details_payload
        self.mock_client.account_details_all.return_value = mock_details

    def test_update_aggregates_accounts(self):
        manager = AccountManager(self.mock_client)
        manager.update()

        # Check accounts
        self.assertIn(123456, manager.accounts)
        self.assertEqual(manager.accounts[123456]["hashValue"], "hash123")
        self.assertEqual(manager.accounts[123456]["cashBalance"], 1000.0)

        self.assertIn(654321, manager.accounts)
        self.assertEqual(manager.accounts[654321]["hashValue"], "hash654")
        self.assertEqual(manager.accounts[654321]["cashBalance"], 200.0)

        # Check positions dictionary
        self.assertIn("AAPL", manager.positions)
        self.assertIn("MSFT", manager.positions)

        # AAPL across two accounts
        self.assertEqual(manager.positions["AAPL"][123456]["longQuantity"], 10.0)
        self.assertEqual(manager.positions["AAPL"][654321]["longQuantity"], 5.0)

    def test_get_position_totals(self):
        manager = AccountManager(self.mock_client)
        manager.update()

        aapl_totals = manager.get_position_totals("AAPL")
        self.assertEqual(aapl_totals["longQuantity"], 15.0)
        self.assertEqual(aapl_totals["shortQuantity"], 0.0)
        self.assertEqual(aapl_totals["netQuantity"], 15.0)
        self.assertEqual(aapl_totals["marketValue"], 2400.0)

        msft_totals = manager.get_position_totals("MSFT")
        self.assertEqual(msft_totals["longQuantity"], 0.0)
        self.assertEqual(msft_totals["shortQuantity"], 5.0)
        self.assertEqual(msft_totals["netQuantity"], -5.0)

    def test_automatic_subscription(self):
        mock_stream = MagicMock(spec=StreamClient)
        manager = AccountManager(self.mock_client, stream_client=mock_stream)
        manager.update()

        # It should have called _subscribe_positions and _subscribe_account_activity
        # so send() should be called twice.
        self.assertEqual(mock_stream.send.call_count, 2)

        mock_stream.level_one_equities.assert_called_once()
        mock_stream.account_activity.assert_called_once()

        call_args = mock_stream.level_one_equities.call_args
        keys = call_args.kwargs.get(
            "keys", call_args.args[0] if len(call_args.args) > 0 else []
        )
        self.assertIn("AAPL", keys)
        self.assertIn("MSFT", keys)

    def test_stream_updates_market_value(self):
        manager = AccountManager(self.mock_client)
        manager.update()

        # Before update, AAPL in account 123456 is 1600 (price 160)
        self.assertEqual(manager.positions["AAPL"][123456]["marketValue"], 1600.0)

        # Simulate a stream update
        stream_payload = {
            "symbol": "AAPL",
            "last_price": 200.0,
            "mark_price": 205.0,  # Mark takes precedence
        }

        manager.on_level_one_equity(stream_payload)

        # Qty is 10. Mark price is 205. Value should be 2050
        self.assertEqual(manager.positions["AAPL"][123456]["marketValue"], 2050.0)

        # Total aggregation should update as well
        totals = manager.get_position_totals("AAPL")
        # 10 * 205 + 5 * 205 = 3075
        self.assertEqual(totals["marketValue"], 3075.0)

    def test_on_account_activity_triggers_update(self):
        manager = AccountManager(self.mock_client)

        # Override update to verify it gets called
        with patch.object(manager, "update") as mock_update:
            # Simulate a non-fill
            manager.on_account_activity({"message_type": "OrderEntry"})
            # Give background thread a tiny window to spawn (it shouldn't)
            time.sleep(0.01)
            mock_update.assert_not_called()

            # Simulate an order fill
            manager.on_account_activity({"message_type": "OrderFill"})
            # Wait briefly for thread execution
            time.sleep(0.1)
            mock_update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
