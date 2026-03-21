import unittest
from typing import Any, Dict

from schwab_api.stream_parsers import StreamResponseHandler, parse_numeric_fields


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


class TestParseNumericFieldsTypeCasting(unittest.TestCase):
    """Verify that parse_numeric_fields casts values to the correct Python types."""

    def _equity_raw(self, **overrides) -> Dict[str, Any]:
        """Minimal LEVELONE_EQUITIES payload with string-encoded numerics."""
        data = {
            "key": "AAPL",
            "1": "172.50",  # bid_price → float
            "2": "172.51",  # ask_price → float
            "3": "172.48",  # last_price → float
            "4": "3",  # bid_size → int
            "5": "5",  # ask_size → int
            "8": "12345678",  # total_volume → int
            "14": "true",  # marginable → bool
            "33": "172.49",  # mark_price → float
            "34": "1741789287237",  # quote_time → int (epoch ms)
            "48": "0",  # hard_to_borrow → int (NOT bool: 0=false, -1=NULL)
            "49": "1",  # shortable → int (NOT bool: 1=true, -1=NULL)
        }
        data.update(overrides)
        return data

    def test_equity_prices_cast_to_float(self):
        parsed = parse_numeric_fields(self._equity_raw(), "LEVELONE_EQUITIES")
        self.assertIsInstance(parsed["bid_price"], float)
        self.assertAlmostEqual(parsed["bid_price"], 172.50)
        self.assertIsInstance(parsed["ask_price"], float)
        self.assertIsInstance(parsed["last_price"], float)
        self.assertIsInstance(parsed["mark_price"], float)

    def test_equity_sizes_cast_to_int(self):
        parsed = parse_numeric_fields(self._equity_raw(), "LEVELONE_EQUITIES")
        self.assertIsInstance(parsed["bid_size"], int)
        self.assertEqual(parsed["bid_size"], 3)
        self.assertIsInstance(parsed["ask_size"], int)
        self.assertIsInstance(parsed["total_volume"], int)
        self.assertEqual(parsed["total_volume"], 12345678)

    def test_equity_bool_fields(self):
        parsed = parse_numeric_fields(self._equity_raw(), "LEVELONE_EQUITIES")
        self.assertIsInstance(parsed["marginable"], bool)
        self.assertTrue(parsed["marginable"])

    def test_equity_timestamp_cast_to_int(self):
        parsed = parse_numeric_fields(self._equity_raw(), "LEVELONE_EQUITIES")
        self.assertIsInstance(parsed["quote_time"], int)
        self.assertEqual(parsed["quote_time"], 1741789287237)

    def test_equity_hard_to_borrow_is_int_not_bool(self):
        # hard_to_borrow uses -1=NULL sentinel so must be int, not bool
        parsed = parse_numeric_fields(self._equity_raw(), "LEVELONE_EQUITIES")
        self.assertIsInstance(parsed["hard_to_borrow"], int)
        self.assertNotIsInstance(parsed["hard_to_borrow"], bool)
        self.assertIsInstance(parsed["shortable"], int)
        self.assertNotIsInstance(parsed["shortable"], bool)

    def test_none_values_pass_through_unchanged(self):
        # Schwab sends null for unknown fields; must not raise TypeError
        raw = self._equity_raw()
        raw["47"] = None  # hard_to_borrow_rate = None (NULL)
        parsed = parse_numeric_fields(raw, "LEVELONE_EQUITIES")
        self.assertIsNone(parsed["hard_to_borrow_rate"])

    def test_already_correct_type_is_idempotent(self):
        # If json.loads already delivered a float, float(float) is a no-op
        raw = self._equity_raw()
        raw["1"] = 172.50  # already a float
        parsed = parse_numeric_fields(raw, "LEVELONE_EQUITIES")
        self.assertIsInstance(parsed["bid_price"], float)
        self.assertAlmostEqual(parsed["bid_price"], 172.50)

    def test_option_greeks_cast_to_float(self):
        raw = {
            "key": "AAPL  240809C00150000",
            "28": "-0.35",  # delta
            "29": "0.0123",  # gamma
            "30": "-0.05",  # theta
            "20": "150.0",  # strike_price
            "27": "30",  # days_to_expiration
        }
        parsed = parse_numeric_fields(raw, "LEVELONE_OPTIONS")
        self.assertIsInstance(parsed["delta"], float)
        self.assertAlmostEqual(parsed["delta"], -0.35)
        self.assertIsInstance(parsed["gamma"], float)
        self.assertIsInstance(parsed["theta"], float)
        self.assertIsInstance(parsed["strike_price"], float)
        self.assertIsInstance(parsed["days_to_expiration"], int)
        self.assertEqual(parsed["days_to_expiration"], 30)

    def test_futures_bool_fields(self):
        raw = {
            "key": "/ES",
            "1": "5300.25",  # bid_price
            "30": "true",  # future_is_tradable
            "32": "true",  # future_is_active
        }
        parsed = parse_numeric_fields(raw, "LEVELONE_FUTURES")
        self.assertIsInstance(parsed["bid_price"], float)
        self.assertIsInstance(parsed["future_is_tradable"], bool)
        self.assertTrue(parsed["future_is_tradable"])
        self.assertIsInstance(parsed["future_is_active"], bool)

    def test_unknown_service_no_type_cast(self):
        # ACCT_ACTIVITY has no type map — values should pass through unchanged
        raw = {"key": "acct", "1": "123456", "2": "ORDER_FILL", "3": "{}"}
        parsed = parse_numeric_fields(raw, "ACCT_ACTIVITY")
        # Values stay as strings since no type map is registered
        self.assertEqual(parsed.get("account"), "123456")

    def test_malformed_value_preserved_on_cast_failure(self):
        # If Schwab sends an unexpected encoding, keep the raw value, don't raise
        raw = self._equity_raw(**{"1": "N/A"})  # bid_price as non-numeric string
        parsed = parse_numeric_fields(raw, "LEVELONE_EQUITIES")
        self.assertEqual(parsed["bid_price"], "N/A")

    def test_symbol_field_is_unchanged_string(self):
        # symbol (field "0") has no type map entry; must remain a string
        raw = {"key": "AAPL", "0": "AAPL", "1": "172.50"}
        parsed = parse_numeric_fields(raw, "LEVELONE_EQUITIES")
        self.assertIsInstance(parsed["symbol"], str)
        self.assertEqual(parsed["symbol"], "AAPL")


if __name__ == "__main__":
    unittest.main()
