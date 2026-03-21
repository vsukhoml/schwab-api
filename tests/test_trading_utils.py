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


def _make_ic_chain_df(stock_price: float = 100.0, dte: int = 30):
    """
    Build a minimal synthetic option chain DataFrame for Iron Condor tests.

    Strikes: puts at 85/90/95, calls at 105/110/115
    Deltas:  puts -0.10/-0.20/-0.30, calls +0.30/+0.20/+0.10
    """
    import pandas as pd

    expiry = (datetime.date(2025, 3, 27) + datetime.timedelta(days=dte)).isoformat()
    rows = [
        # Puts (is_put=True, delta negative)
        dict(
            symbol="X 250426P00085000",
            expiration_date=expiry,
            days_to_expiration=dte,
            stock_price=stock_price,
            strike_price=85.0,
            is_put=True,
            delta=-0.10,
            bid=0.30,
            ask=0.50,
            option_price=0.40,
            openInterest=500,
        ),
        dict(
            symbol="X 250426P00090000",
            expiration_date=expiry,
            days_to_expiration=dte,
            stock_price=stock_price,
            strike_price=90.0,
            is_put=True,
            delta=-0.20,
            bid=0.70,
            ask=0.90,
            option_price=0.80,
            openInterest=500,
        ),
        dict(
            symbol="X 250426P00095000",
            expiration_date=expiry,
            days_to_expiration=dte,
            stock_price=stock_price,
            strike_price=95.0,
            is_put=True,
            delta=-0.30,
            bid=1.40,
            ask=1.60,
            option_price=1.50,
            openInterest=500,
        ),
        # Calls (is_put=False, delta positive)
        dict(
            symbol="X 250426C00105000",
            expiration_date=expiry,
            days_to_expiration=dte,
            stock_price=stock_price,
            strike_price=105.0,
            is_put=False,
            delta=0.30,
            bid=1.40,
            ask=1.60,
            option_price=1.50,
            openInterest=500,
        ),
        dict(
            symbol="X 250426C00110000",
            expiration_date=expiry,
            days_to_expiration=dte,
            stock_price=stock_price,
            strike_price=110.0,
            is_put=False,
            delta=0.20,
            bid=0.70,
            ask=0.90,
            option_price=0.80,
            openInterest=500,
        ),
        dict(
            symbol="X 250426C00115000",
            expiration_date=expiry,
            days_to_expiration=dte,
            stock_price=stock_price,
            strike_price=115.0,
            is_put=False,
            delta=0.10,
            bid=0.30,
            ask=0.50,
            option_price=0.40,
            openInterest=500,
        ),
    ]
    df = pd.DataFrame(rows).set_index("symbol")
    df.index.name = "symbol"
    return df


class TestIronCondors(unittest.TestCase):
    def setUp(self):
        self.df = _make_ic_chain_df()
        self.analyzer = OptionChainAnalyzer(self.df)

    def test_returns_dataframe_with_expected_columns(self):
        ic = self.analyzer.get_iron_condors(min_dte=20, max_dte=45)
        self.assertFalse(ic.empty)
        for col in [
            "expiration_date",
            "days_to_expiration",
            "stock_price",
            "short_put_symbol",
            "short_put_strike",
            "short_put_delta",
            "short_put_mark",
            "long_put_symbol",
            "long_put_strike",
            "long_put_mark",
            "put_width",
            "short_call_symbol",
            "short_call_strike",
            "short_call_delta",
            "short_call_mark",
            "long_call_symbol",
            "long_call_strike",
            "long_call_mark",
            "call_width",
            "net_credit",
            "max_loss",
            "credit_to_width_ratio",
            "break_even_lower",
            "break_even_upper",
        ]:
            self.assertIn(col, ic.columns, msg=f"Missing column: {col}")

    def test_leg_ordering(self):
        ic = self.analyzer.get_iron_condors(min_dte=20, max_dte=45)
        # long_put_strike < short_put_strike < short_call_strike < long_call_strike
        self.assertTrue((ic["long_put_strike"] < ic["short_put_strike"]).all())
        self.assertTrue((ic["short_put_strike"] < ic["short_call_strike"]).all())
        self.assertTrue((ic["short_call_strike"] < ic["long_call_strike"]).all())

    def test_net_credit_is_positive(self):
        ic = self.analyzer.get_iron_condors(min_dte=20, max_dte=45)
        # With these synthetic prices all condors should collect positive credit
        self.assertTrue((ic["net_credit"] > 0).all())

    def _get_5wide_condor(self):
        """Returns the unique 5-wide symmetric condor: 95/90 put spread + 105/110 call spread."""
        return self.analyzer.get_iron_condors(
            min_dte=20,
            max_dte=45,
            min_short_delta=0.29,
            max_short_delta=0.31,  # only delta ±0.30 shorts
            min_wing_width=5.0,
            max_wing_width=5.0,  # exactly 5-wide wings
        )

    def test_net_credit_calculation(self):
        # short_put_mark=1.50, long_put_mark=0.80, short_call_mark=1.50, long_call_mark=0.80
        ic = self._get_5wide_condor()
        self.assertFalse(ic.empty)
        self.assertEqual(len(ic), 1)
        expected_credit = 1.50 + 1.50 - 0.80 - 0.80  # = 1.40
        self.assertAlmostEqual(ic.iloc[0]["net_credit"], expected_credit, places=5)

    def test_max_loss_calculation(self):
        ic = self._get_5wide_condor()
        row = ic.iloc[0]
        expected_max_loss = max(row["put_width"], row["call_width"]) - row["net_credit"]
        self.assertAlmostEqual(row["max_loss"], expected_max_loss, places=5)

    def test_break_evens(self):
        ic = self._get_5wide_condor()
        row = ic.iloc[0]
        self.assertAlmostEqual(
            row["break_even_lower"],
            row["short_put_strike"] - row["net_credit"],
            places=5,
        )
        self.assertAlmostEqual(
            row["break_even_upper"],
            row["short_call_strike"] + row["net_credit"],
            places=5,
        )

    def test_dte_filter_excludes_all(self):
        ic = self.analyzer.get_iron_condors(min_dte=60, max_dte=90)
        self.assertTrue(ic.empty)

    def test_min_credit_filter(self):
        ic_all = self.analyzer.get_iron_condors(min_dte=20, max_dte=45)
        max_credit = ic_all["net_credit"].max()
        # Require more than the max → empty
        ic_filtered = self.analyzer.get_iron_condors(
            min_dte=20, max_dte=45, min_credit=max_credit + 1.0
        )
        self.assertTrue(ic_filtered.empty)

    def test_min_credit_to_width_ratio_filter(self):
        ic = self.analyzer.get_iron_condors(
            min_dte=20, max_dte=45, min_credit_to_width_ratio=0.99
        )
        # All remaining rows must satisfy the ratio
        if not ic.empty:
            self.assertTrue((ic["credit_to_width_ratio"] >= 0.99).all())

    def test_symmetric_wings_filter(self):
        ic = self.analyzer.get_iron_condors(
            min_dte=20, max_dte=45, symmetric_wings=True
        )
        if not ic.empty:
            self.assertTrue(((ic["put_width"] - ic["call_width"]).abs() < 0.01).all())

    def test_max_wing_width_filter(self):
        # With max_wing_width=4, no 5-wide spreads should appear
        ic = self.analyzer.get_iron_condors(min_dte=20, max_dte=45, max_wing_width=4.0)
        if not ic.empty:
            self.assertTrue((ic["put_width"] <= 4.0).all())
            self.assertTrue((ic["call_width"] <= 4.0).all())

    def test_empty_chain_returns_empty(self):
        import pandas as pd

        analyzer = OptionChainAnalyzer(pd.DataFrame())
        ic = analyzer.get_iron_condors()
        self.assertTrue(ic.empty)

    def test_puts_only_chain_returns_empty(self):
        puts_only = self.df[self.df["is_put"]]
        analyzer = OptionChainAnalyzer(puts_only)
        ic = analyzer.get_iron_condors(min_dte=20, max_dte=45)
        self.assertTrue(ic.empty)

    def test_sorted_by_credit_to_width_ratio_descending(self):
        ic = self.analyzer.get_iron_condors(min_dte=20, max_dte=45)
        if len(ic) > 1:
            ratios = ic["credit_to_width_ratio"].tolist()
            # Within each expiry group the ratio is non-increasing
            self.assertEqual(ratios, sorted(ratios, reverse=True))


if __name__ == "__main__":
    unittest.main()
