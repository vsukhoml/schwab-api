import json
import os
import unittest
import datetime

from schwab_api.utils import parse_option_chain_to_df
from schwab_api.math import BlackScholesPricer, calculate_mfiv_from_df


class TestE2EOptionChainMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dump_file = os.path.join(
            os.path.dirname(__file__), "..", "e2e_dumps", "option_chains.json"
        )
        if not os.path.exists(dump_file):
            raise unittest.SkipTest(f"Dump file not found: {dump_file}")

        with open(dump_file, "r") as f:
            cls.chain_json = json.load(f)

    def test_parse_option_chain_to_df(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas is not installed")

        df = parse_option_chain_to_df(self.chain_json)
        self.assertFalse(df.empty)

        # Verify required columns
        expected_columns = [
            "ticker",
            "stock_price",
            "expiration_date",
            "days_to_expiration",
            "is_put",
            "strike_price",
            "bid",
            "ask",
            "last",
            "mark",
            "option_price",
            "delta",
            "gamma",
            "theta",
            "vega",
            "rho",
            "volatility",
            "totalVolume",
            "openInterest",
            "inTheMoney",
        ]
        for col in expected_columns:
            self.assertIn(col, df.columns)

        # Verify volatility is extracted correctly
        self.assertIn("volatility", df.columns)

        # Grab a row that has a non-zero volatility
        df_valid_vol = df[df["volatility"] > 0]
        self.assertFalse(df_valid_vol.empty, "No options found with volatility > 0")

    def test_black_scholes_computation_from_df(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas is not installed")

        df = parse_option_chain_to_df(self.chain_json)

        # Select an option with positive volatility, positive strike
        df_valid = df[(df["volatility"] > 0) & (df["strike_price"] > 0)].iloc[0]

        pricer = BlackScholesPricer(
            stock_price=df_valid["stock_price"],
            strike_price=df_valid["strike_price"],
            expiration_date=df_valid["expiration_date"],
            is_put=df_valid["is_put"],
            volatility=df_valid["volatility"]
            / 100.0,  # Note: IV might be passed as percentage in dump, so / 100
            evaluation_date=datetime.date.today(),
        )

        # Compute all greeks
        greeks = pricer.compute_all()
        self.assertIn("delta", greeks)
        self.assertIn("gamma", greeks)
        self.assertIn("theta", greeks)
        self.assertIn("vega", greeks)
        self.assertIn("rho", greeks)

        # Values should be floats
        for k, v in greeks.items():
            self.assertIsInstance(v, float)

    def test_calculate_mfiv_from_df(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas is not installed")

        df = parse_option_chain_to_df(self.chain_json)
        self.assertFalse(df.empty)

        # Filter dataframe for a single expiration date to calculate MFIV
        exp_dates = df["expiration_date"].unique()
        self.assertTrue(len(exp_dates) > 0)

        target_exp = exp_dates[0]
        single_exp_df = df[df["expiration_date"] == target_exp].copy()

        # Calculate time_to_maturity
        time_to_maturity = (target_exp - datetime.date.today()).days / 365.0
        if time_to_maturity <= 0:
            time_to_maturity = 1e-8

        mfiv = calculate_mfiv_from_df(
            df=single_exp_df,
            time_to_maturity=time_to_maturity,
            risk_free_rate=0.05,
            dividend_yield=0.0,
        )

        # We might get nan if data is too sparse, but it shouldn't crash

        # Ensure mfiv is a float or nan
        self.assertIsInstance(mfiv, float)


if __name__ == "__main__":
    unittest.main()
