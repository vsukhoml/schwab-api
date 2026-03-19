import datetime
import unittest


from schwab_api.trading import OptionChainAnalyzer, PositionAnalyzer
from schwab_api.utils import parse_price_history_to_df, to_schwab


class TestTradingAnalyzers(unittest.TestCase):
    def setUp(self):
        # Mock Option Chain JSON Response
        self.mock_chain_json = {
            "symbol": "GOOG",
            "status": "SUCCESS",
            "underlyingPrice": 164.08,
            "callExpDateMap": {},
            "putExpDateMap": {
                "2025-04-25:29": {
                    "95.0": [
                        {
                            "putCall": "PUT",
                            "symbol": "GOOG 250425P00095000",
                            "bid": 1.10,
                            "ask": 1.20,
                            "strikePrice": 95.0,
                            "delta": -0.25,
                            "openInterest": 500,
                            "totalVolume": 100,
                        }
                    ],
                    "90.0": [
                        {
                            "putCall": "PUT",
                            "symbol": "GOOG 250425P00090000",
                            "bid": 0.40,
                            "ask": 0.50,
                            "strikePrice": 90.0,
                            "delta": -0.15,
                            "openInterest": 1000,
                            "totalVolume": 200,
                        }
                    ],
                }
            },
        }

        # Mock Position JSON Response
        self.mock_positions_json = [
            {
                "longQuantity": 0,
                "shortQuantity": 1,  # Short 1 contract
                "averagePrice": 1.50,
                "marketValue": -100.0,  # Current value $1.00
                "instrument": {
                    "assetType": "OPTION",
                    "symbol": "GOOG  250425P00095000",
                    "underlyingSymbol": "GOOG",
                },
            },
            {
                "longQuantity": 100,
                "shortQuantity": 0,
                "averagePrice": 150.0,
                "marketValue": 16408.0,
                "instrument": {"assetType": "EQUITY", "symbol": "GOOG"},
            },
        ]

    def test_option_chain_analyzer(self):
        eval_date = datetime.date(2025, 3, 27)  # Hardcoded eval date to force DTE to 29
        from schwab_api.utils import parse_option_chain_to_df

        df_chain = parse_option_chain_to_df(
            self.mock_chain_json, evaluation_date=eval_date
        )
        analyzer = OptionChainAnalyzer(df_chain)

        self.assertFalse(analyzer.df.empty)
        self.assertEqual(len(analyzer.df), 2)

        # Test basic filtering (Wheel candidates)
        candidates = analyzer.get_put_candidates(
            min_dte=20, max_dte=30, min_delta=0.20, max_delta=0.30
        )

        # Should only find the 95 strike (-0.25 delta absolute value = 0.25)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates.iloc[0]["strike_price"], 95.0)
        self.assertEqual(
            candidates.iloc[0]["option_price"], 1.15
        )  # Mid price of 1.10 and 1.20

    def test_position_analyzer_options(self):
        analyzer = PositionAnalyzer(self.mock_positions_json)

        # 1 option position, 1 equity position
        self.assertEqual(len(analyzer.options), 1)
        self.assertEqual(len(analyzer.equities), 1)

        opt = analyzer.options[0]
        self.assertEqual(opt["symbol"], "GOOG  250425P00095000")
        self.assertEqual(opt["quantity"], -1)
        self.assertEqual(opt["is_put"], True)
        self.assertEqual(opt["strike_price"], 95.0)
        self.assertEqual(opt["average_price"], 1.50)
        self.assertEqual(opt["current_price"], 1.00)  # |-100| / 100

        # Short position: sold at 1.50, buying back at 1.00 = 0.50 profit
        self.assertAlmostEqual(opt["profit_percentage"], 33.33, places=2)

    def test_to_schwab_ticker(self):
        self.assertEqual(to_schwab("^VIX"), "$VIX")
        self.assertEqual(to_schwab("BRK.B"), "BRK/B")
        self.assertEqual(to_schwab("BF.A"), "BF/A")

    def test_parse_price_history(self):
        mock_history = {
            "candles": [
                {
                    "open": 164.5,
                    "high": 165.2,
                    "low": 163.8,
                    "close": 164.1,
                    "volume": 1200000,
                    "datetime": 1741737600000,  # Matches epoch
                }
            ],
            "symbol": "GOOG",
            "empty": False,
        }

        df = parse_price_history_to_df(mock_history)
        self.assertFalse(df.empty)
        self.assertIn("Close", df.columns)
        self.assertEqual(df.iloc[0]["Close"], 164.1)
        self.assertEqual(df.iloc[0]["Volume"], 1200000)

    def test_get_losing_short_puts(self):
        mock_positions = [
            # Winning short put (DTE = 10 days, profit 33%)
            {
                "longQuantity": 0,
                "shortQuantity": 1,
                "averagePrice": 1.50,
                "marketValue": -100.0,  # current price = 1.00
                "instrument": {
                    "assetType": "OPTION",
                    "symbol": "GOOG  250425P00095000",
                    "underlyingSymbol": "GOOG",
                },
            },
            # Losing short put (DTE = 10 days, loss -100%)
            {
                "longQuantity": 0,
                "shortQuantity": 1,
                "averagePrice": 1.50,
                "marketValue": -300.0,  # current price = 3.00, profit = -1.50
                "instrument": {
                    "assetType": "OPTION",
                    "symbol": "AAPL  250425P00150000",
                    "underlyingSymbol": "AAPL",
                },
            },
            # Losing short put but far away (DTE = 45 days, loss -60%) -> should be ignored due to max_dte=14
            {
                "longQuantity": 0,
                "shortQuantity": 1,
                "averagePrice": 1.00,
                "marketValue": -160.0,
                "instrument": {
                    "assetType": "OPTION",
                    "symbol": "MSFT  251219P00400000",  # Far expiration
                    "underlyingSymbol": "MSFT",
                },
            },
            # Short call (losing but not a put)
            {
                "longQuantity": 0,
                "shortQuantity": 1,
                "averagePrice": 1.00,
                "marketValue": -200.0,
                "instrument": {
                    "assetType": "OPTION",
                    "symbol": "TSLA  250425C00200000",
                    "underlyingSymbol": "TSLA",
                },
            },
        ]

        # We need an evaluation date that makes 250425 ~10 days away (e.g. 2025-04-15)
        eval_date = datetime.date(2025, 4, 15)

        analyzer = PositionAnalyzer(mock_positions, evaluation_date=eval_date)

        # Test max_loss_percentage = -50.0%
        losers = analyzer.get_losing_short_puts(max_loss_percentage=-50.0, max_dte=14)

        # Should only find the AAPL put
        self.assertEqual(len(losers), 1)
        self.assertEqual(losers[0]["symbol"], "AAPL  250425P00150000")
        self.assertEqual(losers[0]["profit_percentage"], -100.0)


if __name__ == "__main__":
    unittest.main()
