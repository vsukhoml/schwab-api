import unittest
from typing import Any, Dict

from schwab_api.stream_parsers import StreamResponseHandler


class DummyHandler(StreamResponseHandler):
    def __init__(self):
        super().__init__()
        self.equity_events = []
        self.option_events = []

    def on_level_one_equity(self, update: Dict[str, Any]) -> None:
        self.equity_events.append(update)

    def on_level_one_option(self, update: Dict[str, Any]) -> None:
        self.option_events.append(update)


class TestStreamResponseHandler(unittest.TestCase):
    def test_handler_chaining(self):
        root_handler = StreamResponseHandler()

        handler_a = DummyHandler()
        handler_b = DummyHandler()

        # Add handlers to chain
        root_handler.add_handler(handler_a)
        root_handler.add_handler(handler_b)

        # Simulate a parsed event dispatch
        update_equity = {"symbol": "AAPL", "last_price": 150.0}
        root_handler._dispatch("LEVELONE_EQUITIES", update_equity)

        # Both should receive it
        self.assertEqual(len(handler_a.equity_events), 1)
        self.assertEqual(handler_a.equity_events[0]["symbol"], "AAPL")

        self.assertEqual(len(handler_b.equity_events), 1)
        self.assertEqual(handler_b.equity_events[0]["symbol"], "AAPL")

        # Simulate option event
        update_option = {"symbol": "GOOG", "bid_price": 5.0}
        root_handler._dispatch("LEVELONE_OPTIONS", update_option)

        self.assertEqual(len(handler_a.option_events), 1)
        self.assertEqual(len(handler_b.option_events), 1)

        # Remove handler_b
        root_handler.remove_handler(handler_b)

        update_equity_2 = {"symbol": "MSFT", "last_price": 300.0}
        root_handler._dispatch("LEVELONE_EQUITIES", update_equity_2)

        # Handler A should have 2 events now
        self.assertEqual(len(handler_a.equity_events), 2)
        self.assertEqual(handler_a.equity_events[1]["symbol"], "MSFT")

        # Handler B should still only have 1
        self.assertEqual(len(handler_b.equity_events), 1)


if __name__ == "__main__":
    unittest.main()
