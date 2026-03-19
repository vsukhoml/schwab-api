import unittest

import pandas as pd

from schwab_api.math import calculate_gamma_exposure
from schwab_api.utils import parse_option_chain_to_df


class TestGammaExposure(unittest.TestCase):
    def setUp(self):
        # Mock option chain JSON payload
        self.mock_chain_json = {
            "symbol": "AAPL",
            "underlyingPrice": 150.0,
            "callExpDateMap": {
                "2023-10-20:5": {
                    "145.0": [
                        {
                            "symbol": "AAPL_102023C145",
                            "gamma": 0.05,
                            "openInterest": 1000,
                        }
                    ],
                    "150.0": [
                        {
                            "symbol": "AAPL_102023C150",
                            "gamma": 0.10,
                            "openInterest": 5000,
                        }
                    ],
                    "155.0": [
                        {
                            "symbol": "AAPL_102023C155",
                            "gamma": 0.05,
                            "openInterest": 2000,
                        }
                    ],
                }
            },
            "putExpDateMap": {
                "2023-10-20:5": {
                    "145.0": [
                        {
                            "symbol": "AAPL_102023P145",
                            "gamma": 0.05,
                            "openInterest": 3000,
                        }
                    ],
                    "150.0": [
                        {
                            "symbol": "AAPL_102023P150",
                            "gamma": 0.10,
                            "openInterest": 4000,
                        }
                    ],
                    "155.0": [
                        {
                            "symbol": "AAPL_102023P155",
                            "gamma": 0.05,
                            "openInterest": 1000,
                        }
                    ],
                }
            },
        }

    def test_get_gamma_exposure_non_net(self):
        df_chain = parse_option_chain_to_df(self.mock_chain_json)
        df = calculate_gamma_exposure(df_chain, plot_strikes=10, net_exposure=False)

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 6)
        self.assertIn("gamma_exposure", df.columns)
        self.assertIn("strike_price", df.columns)

        # GEX calculation test for C150
        # GEX = 150 * 0.10 * 5000 * 100 * 150 * 0.01 = 11,250,000
        call_150_row = df[df["symbol"] == "AAPL_102023C150"].iloc[0]
        self.assertAlmostEqual(call_150_row["gamma_exposure"], 11250000.0)

    def test_get_gamma_exposure_net(self):
        df_chain = parse_option_chain_to_df(self.mock_chain_json)
        df = calculate_gamma_exposure(df_chain, plot_strikes=10, net_exposure=True)

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 3)  # 3 unique strikes

        # Net GEX for 150 strike:
        # Call GEX: 150 * 0.10 * 5000 * 100 * 150 * 0.01 = 11,250,000
        # Put GEX: 150 * (-0.10) * 4000 * 100 * 150 * 0.01 = -9,000,000
        # Net GEX = 2,250,000
        net_150_row = df[df["strike_price"] == 150.0].iloc[0]
        self.assertAlmostEqual(net_150_row["gamma_exposure"], 2250000.0)


if __name__ == "__main__":
    unittest.main()
