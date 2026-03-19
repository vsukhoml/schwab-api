import datetime
import unittest

from schwab_api.orders.common import (
    ComplexOrderStrategyType,
    Duration,
    EquityInstruction,
    OptionInstruction,
    OrderStrategyType,
    OrderType,
    Session,
)
from schwab_api.orders.equities import (
    equity_buy_limit,
    equity_buy_market,
    equity_sell_limit,
    equity_sell_market,
)
from schwab_api.orders.generic import OrderBuilder, truncate_float
from schwab_api.orders.options import (
    OptionSymbol,
    bear_call_vertical_close,
    bear_call_vertical_open,
    bear_put_vertical_close,
    bear_put_vertical_open,
    bull_call_vertical_close,
    bull_call_vertical_open,
    bull_put_vertical_close,
    bull_put_vertical_open,
    option_buy_to_close_limit,
    option_buy_to_close_market,
    option_buy_to_open_limit,
    option_buy_to_open_market,
    option_sell_to_close_limit,
    option_sell_to_close_market,
    option_sell_to_open_limit,
    option_sell_to_open_market,
)


class TestTruncateFloat(unittest.TestCase):
    def test_zero(self):
        self.assertEqual("0.00", truncate_float(0))

    def test_zero_float(self):
        self.assertEqual("0.00", truncate_float(0.0))

    def test_integer(self):
        self.assertEqual("12.00", truncate_float(12))

    def test_integer_as_float(self):
        self.assertEqual("12.00", truncate_float(12.0))

    def test_three_digits(self):
        self.assertEqual("12.12", truncate_float(12.123))

    def test_three_digits_truncate_not_round(self):
        self.assertEqual("12.12", truncate_float(12.129))

    def test_less_than_one(self):
        self.assertEqual("0.1212", truncate_float(0.12121))

    def test_negative_integer(self):
        self.assertEqual("-12.00", truncate_float(-12))

    def test_negative_integer_as_float(self):
        self.assertEqual("-12.00", truncate_float(-12.0))

    def test_negative_three_digits(self):
        self.assertEqual("-12.12", truncate_float(-12.123))

    def test_negative_three_digits_truncate_not_round(self):
        self.assertEqual("-12.12", truncate_float(-12.129))

    def test_negative_less_than_one(self):
        self.assertEqual("-0.1212", truncate_float(-0.12121))


class TestOptionSymbol(unittest.TestCase):
    def test_parse_success_put(self):
        op = OptionSymbol.parse_symbol("AAPL  261218P00350000")
        self.assertEqual(op.underlying_symbol, "AAPL")
        self.assertEqual(op.expiration_date, datetime.date(year=2026, month=12, day=18))
        self.assertEqual(op.contract_type, "P")
        self.assertEqual(op.strike_price, "350")
        self.assertEqual("AAPL  261218P00350000", op.build())

    def test_parse_success_call(self):
        op = OptionSymbol.parse_symbol("AAPL  240510C00100000")
        self.assertEqual(op.underlying_symbol, "AAPL")
        self.assertEqual(op.expiration_date, datetime.date(year=2024, month=5, day=10))
        self.assertEqual(op.contract_type, "C")
        self.assertEqual(op.strike_price, "100")
        self.assertEqual("AAPL  240510C00100000", op.build())

    def test_short_symbol(self):
        op = OptionSymbol.parse_symbol("V     240510C00145000")
        self.assertEqual(op.underlying_symbol, "V")
        self.assertEqual(op.expiration_date, datetime.date(year=2024, month=5, day=10))
        self.assertEqual(op.contract_type, "C")
        self.assertEqual(op.strike_price, "145")
        self.assertEqual("V     240510C00145000", op.build())

    def test_strike_over_1000(self):
        op = OptionSymbol.parse_symbol("BKNG  240510C02400000")
        self.assertEqual(op.underlying_symbol, "BKNG")
        self.assertEqual(op.expiration_date, datetime.date(year=2024, month=5, day=10))
        self.assertEqual(op.contract_type, "C")
        self.assertEqual(op.strike_price, "2400")
        self.assertEqual("BKNG  240510C02400000", op.build())

    def test_strike_ends_in_decimal_point(self):
        op = OptionSymbol("AAPL", datetime.date(2024, 5, 10), "C", "100.")
        self.assertEqual("AAPL  240510C00100000", op.build())

    def test_strike_ends_in_trailing_zeroes(self):
        op = OptionSymbol("AAPL", datetime.date(2024, 5, 10), "C", "100.00000000")
        self.assertEqual("AAPL  240510C00100000", op.build())

    def test_CALL_as_delimiter(self):
        op = OptionSymbol("AAPL", datetime.date(2024, 5, 10), "CALL", "100.10")
        self.assertEqual("AAPL  240510C00100100", op.build())

    def test_PUT_as_delimiter(self):
        op = OptionSymbol("AAPL", datetime.date(2024, 5, 10), "PUT", "100.10")
        self.assertEqual("AAPL  240510P00100100", op.build())

    def test_invalid_strike(self):
        with self.assertRaisesRegex(ValueError, ".*option must have contract type.*"):
            OptionSymbol.parse_symbol("BKNG  240510Q02400000")

    def test_date_as_string(self):
        op = OptionSymbol("AAPL", "261218", "P", "350")
        self.assertEqual("AAPL  261218P00350000", op.build())

    def test_strike_as_float(self):
        op = OptionSymbol("AAPL", datetime.date(2024, 5, 10), "C", 183.05)
        self.assertEqual("AAPL  240510C00183050", op.build())

    def test_strike_as_invalid_string(self):
        with self.assertRaisesRegex(ValueError, ".*strike price must be a.*"):
            OptionSymbol("AAPL", datetime.date(2024, 5, 10), "C", "bogus-strike")

    def test_strike_negative(self):
        with self.assertRaisesRegex(ValueError, ".*strike price must be a.*"):
            OptionSymbol("AAPL", datetime.date(2024, 5, 10), "C", "-150.0")

    def test_strike_zero(self):
        with self.assertRaisesRegex(ValueError, ".*strike price must be a.*"):
            OptionSymbol("AAPL", datetime.date(2024, 5, 10), "C", "0")


class TestEquityTemplates(unittest.TestCase):
    def test_equity_buy_market(self):
        expected = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": 10,
                    "instrument": {"symbol": "AAPL", "assetType": "EQUITY"},
                }
            ],
        }
        self.assertEqual(expected, equity_buy_market("AAPL", 10).build())

    def test_equity_buy_limit(self):
        expected = {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "200.50",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": 5,
                    "instrument": {"symbol": "MSFT", "assetType": "EQUITY"},
                }
            ],
        }
        self.assertEqual(expected, equity_buy_limit("MSFT", 5, 200.5).build())

    def test_equity_sell_market(self):
        expected = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": 20,
                    "instrument": {"symbol": "TSLA", "assetType": "EQUITY"},
                }
            ],
        }
        self.assertEqual(expected, equity_sell_market("TSLA", 20).build())

    def test_equity_sell_limit(self):
        expected = {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "250.75",
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": 15,
                    "instrument": {"symbol": "AMZN", "assetType": "EQUITY"},
                }
            ],
        }
        self.assertEqual(expected, equity_sell_limit("AMZN", 15, 250.75).build())


class TestOptionTemplates(unittest.TestCase):
    def test_option_buy_to_open_market(self):
        expected = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": 10,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                }
            ],
        }
        self.assertEqual(
            expected, option_buy_to_open_market("GOOG_012122P2200", 10).build()
        )

    def test_option_buy_to_open_limit(self):
        expected = {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "32.50",
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": 10,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                }
            ],
        }
        self.assertEqual(
            expected, option_buy_to_open_limit("GOOG_012122P2200", 10, 32.5).build()
        )

    def test_option_sell_to_open_market(self):
        expected = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": 10,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                }
            ],
        }
        self.assertEqual(
            expected, option_sell_to_open_market("GOOG_012122P2200", 10).build()
        )

    def test_option_sell_to_open_limit(self):
        expected = {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "32.50",
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": 10,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                }
            ],
        }
        self.assertEqual(
            expected, option_sell_to_open_limit("GOOG_012122P2200", 10, 32.5).build()
        )

    def test_option_buy_to_close_market(self):
        expected = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": 10,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                }
            ],
        }
        self.assertEqual(
            expected, option_buy_to_close_market("GOOG_012122P2200", 10).build()
        )

    def test_option_buy_to_close_limit(self):
        expected = {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "32.50",
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": 10,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                }
            ],
        }
        self.assertEqual(
            expected, option_buy_to_close_limit("GOOG_012122P2200", 10, 32.5).build()
        )

    def test_option_sell_to_close_market(self):
        expected = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": 10,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                }
            ],
        }
        self.assertEqual(
            expected, option_sell_to_close_market("GOOG_012122P2200", 10).build()
        )

    def test_option_sell_to_close_limit(self):
        expected = {
            "orderType": "LIMIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "32.50",
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": 10,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                }
            ],
        }
        self.assertEqual(
            expected, option_sell_to_close_limit("GOOG_012122P2200", 10, 32.5).build()
        )


class TestVerticalTemplates(unittest.TestCase):
    def test_bull_call_vertical_open(self):
        expected = {
            "orderType": "NET_DEBIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "30.60",
            "complexOrderStrategyType": "VERTICAL",
            "quantity": 3,
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122C2200", "assetType": "OPTION"},
                },
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122C2400", "assetType": "OPTION"},
                },
            ],
        }
        self.assertEqual(
            expected,
            bull_call_vertical_open(
                "GOOG_012122C2200", "GOOG_012122C2400", 3, 30.6
            ).build(),
        )

    def test_bull_call_vertical_close(self):
        expected = {
            "orderType": "NET_CREDIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "30.60",
            "complexOrderStrategyType": "VERTICAL",
            "quantity": 3,
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122C2200", "assetType": "OPTION"},
                },
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122C2400", "assetType": "OPTION"},
                },
            ],
        }
        self.assertEqual(
            expected,
            bull_call_vertical_close(
                "GOOG_012122C2200", "GOOG_012122C2400", 3, 30.6
            ).build(),
        )

    def test_bear_call_vertical_open(self):
        expected = {
            "orderType": "NET_CREDIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "30.60",
            "complexOrderStrategyType": "VERTICAL",
            "quantity": 3,
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122C2200", "assetType": "OPTION"},
                },
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122C2400", "assetType": "OPTION"},
                },
            ],
        }
        self.assertEqual(
            expected,
            bear_call_vertical_open(
                "GOOG_012122C2200", "GOOG_012122C2400", 3, 30.6
            ).build(),
        )

    def test_bear_call_vertical_close(self):
        expected = {
            "orderType": "NET_DEBIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "30.60",
            "complexOrderStrategyType": "VERTICAL",
            "quantity": 3,
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122C2200", "assetType": "OPTION"},
                },
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122C2400", "assetType": "OPTION"},
                },
            ],
        }
        self.assertEqual(
            expected,
            bear_call_vertical_close(
                "GOOG_012122C2200", "GOOG_012122C2400", 3, 30.6
            ).build(),
        )

    def test_bull_put_vertical_open(self):
        expected = {
            "orderType": "NET_CREDIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "30.60",
            "complexOrderStrategyType": "VERTICAL",
            "quantity": 3,
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                },
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122P2400", "assetType": "OPTION"},
                },
            ],
        }
        self.assertEqual(
            expected,
            bull_put_vertical_open(
                "GOOG_012122P2200", "GOOG_012122P2400", 3, 30.6
            ).build(),
        )

    def test_bull_put_vertical_close(self):
        expected = {
            "orderType": "NET_DEBIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "30.60",
            "complexOrderStrategyType": "VERTICAL",
            "quantity": 3,
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                },
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122P2400", "assetType": "OPTION"},
                },
            ],
        }
        self.assertEqual(
            expected,
            bull_put_vertical_close(
                "GOOG_012122P2200", "GOOG_012122P2400", 3, 30.6
            ).build(),
        )

    def test_bear_put_vertical_open(self):
        expected = {
            "orderType": "NET_DEBIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "30.60",
            "complexOrderStrategyType": "VERTICAL",
            "quantity": 3,
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                },
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122P2400", "assetType": "OPTION"},
                },
            ],
        }
        self.assertEqual(
            expected,
            bear_put_vertical_open(
                "GOOG_012122P2200", "GOOG_012122P2400", 3, 30.6
            ).build(),
        )

    def test_bear_put_vertical_close(self):
        expected = {
            "orderType": "NET_CREDIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": "30.60",
            "complexOrderStrategyType": "VERTICAL",
            "quantity": 3,
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122P2200", "assetType": "OPTION"},
                },
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": 3,
                    "instrument": {"symbol": "GOOG_012122P2400", "assetType": "OPTION"},
                },
            ],
        }
        self.assertEqual(
            expected,
            bear_put_vertical_close(
                "GOOG_012122P2200", "GOOG_012122P2400", 3, 30.6
            ).build(),
        )


class TestOrderBuilder(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.builder = OrderBuilder()

    def test_session_success(self):
        self.builder.set_session(Session.NORMAL)
        self.assertEqual({"session": "NORMAL"}, self.builder.build())
        self.builder.clear_session()
        self.assertEqual({}, self.builder.build())

    def test_duration_success(self):
        self.builder.set_duration(Duration.DAY)
        self.assertEqual({"duration": "DAY"}, self.builder.build())
        self.builder.clear_duration()
        self.assertEqual({}, self.builder.build())

    def test_order_type_success(self):
        self.builder.set_order_type(OrderType.MARKET)
        self.assertEqual({"orderType": "MARKET"}, self.builder.build())
        self.builder.clear_order_type()
        self.assertEqual({}, self.builder.build())

    def test_complex_order_strategy_type_success(self):
        self.builder.set_complex_order_strategy_type(
            ComplexOrderStrategyType.IRON_CONDOR
        )
        self.assertEqual(
            {"complexOrderStrategyType": "IRON_CONDOR"}, self.builder.build()
        )
        self.builder.clear_complex_order_strategy_type()
        self.assertEqual({}, self.builder.build())

    def test_quantity_success(self):
        self.builder.set_quantity(12)
        self.assertEqual({"quantity": 12}, self.builder.build())
        self.builder.clear_quantity()
        self.assertEqual({}, self.builder.build())

    def test_price_success(self):
        self.builder.set_price(23.49)
        self.assertEqual({"price": "23.49"}, self.builder.build())
        self.builder.clear_price()
        self.assertEqual({}, self.builder.build())

    def test_price_negative(self):
        self.builder.set_price(-1.23)
        self.assertEqual({"price": "-1.23"}, self.builder.build())

    def test_price_do_not_round_up(self):
        self.builder.set_price(19.999)
        self.assertEqual({"price": "19.99"}, self.builder.build())

    def test_order_strategy_type_success(self):
        self.builder.set_order_strategy_type(OrderStrategyType.OCO)
        self.assertEqual({"orderStrategyType": "OCO"}, self.builder.build())
        self.builder.clear_order_strategy_type()
        self.assertEqual({}, self.builder.build())

    def test_add_equity_leg_success(self):
        self.builder.add_equity_leg(EquityInstruction.BUY, "GOOG", 10)
        self.builder.add_equity_leg(EquityInstruction.SELL_SHORT, "MSFT", 1)
        expected = {
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "instrument": {"symbol": "GOOG", "assetType": "EQUITY"},
                    "quantity": 10,
                },
                {
                    "instruction": "SELL_SHORT",
                    "instrument": {"symbol": "MSFT", "assetType": "EQUITY"},
                    "quantity": 1,
                },
            ]
        }
        self.assertEqual(expected, self.builder.build())
        self.builder.clear_order_legs()
        self.assertEqual({}, self.builder.build())

    def test_add_option_leg_success(self):
        self.builder.add_option_leg(OptionInstruction.BUY_TO_OPEN, "GOOG31433C1342", 10)
        self.builder.add_option_leg(OptionInstruction.BUY_TO_CLOSE, "MSFT439132P35", 1)
        expected = {
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_OPEN",
                    "instrument": {"symbol": "GOOG31433C1342", "assetType": "OPTION"},
                    "quantity": 10,
                },
                {
                    "instruction": "BUY_TO_CLOSE",
                    "instrument": {"symbol": "MSFT439132P35", "assetType": "OPTION"},
                    "quantity": 1,
                },
            ]
        }
        self.assertEqual(expected, self.builder.build())
        self.builder.clear_order_legs()
        self.assertEqual({}, self.builder.build())

    def test_add_child_order_strategy_success(self):
        self.builder.add_child_order_strategy(
            OrderBuilder().set_session(Session.NORMAL)
        )
        self.assertEqual(
            {"childOrderStrategies": [{"session": "NORMAL"}]}, self.builder.build()
        )
        self.builder.clear_child_order_strategies()
        self.assertEqual({}, self.builder.build())

    def test_actual_account_order_payload_match(self):
        from schwab_api.orders.common import Destination

        builder = (
            OrderBuilder()
            .set_session(Session.NORMAL)
            .set_duration(Duration.GOOD_TILL_CANCEL)
            .set_order_type(OrderType.LIMIT)
            .set_complex_order_strategy_type(ComplexOrderStrategyType.NONE)
            .set_quantity(100.0372)
            .set_destination_link_name(Destination.AUTO)
            .set_price(10.95)
            .add_equity_leg(EquityInstruction.SELL, "GNOM", 100.0372)
            .set_order_strategy_type(OrderStrategyType.SINGLE)
        )

        expected = {
            "session": "NORMAL",
            "duration": "GOOD_TILL_CANCEL",
            "orderType": "LIMIT",
            "complexOrderStrategyType": "NONE",
            "quantity": 100.0372,
            "destinationLinkName": "AUTO",
            "price": "10.95",
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": 100.0372,
                    "instrument": {
                        "symbol": "GNOM",
                        "assetType": "EQUITY",
                    },
                }
            ],
            "orderStrategyType": "SINGLE",
        }
        self.assertEqual(expected, builder.build())


if __name__ == "__main__":
    unittest.main()
