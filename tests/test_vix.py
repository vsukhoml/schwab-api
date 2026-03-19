import unittest

import numpy as np
import pandas as pd

from schwab_api.math import calculate_mfiv_from_df


class TestVix(unittest.TestCase):
    def test_calculate_mfiv_from_df(self):
        # Create a mock dataframe that resembles the output of parse_option_chain_to_df
        # We need a set of puts and calls around a strike price to calculate MFIV.

        spot = 100.0
        data = []

        strikes = [90, 95, 100, 105, 110]

        # Puts (Out of money puts: strikes < spot. ATM put: 100)
        for k in strikes:
            if k <= 100:
                data.append(
                    {
                        "stock_price": spot,
                        "strike_price": float(k),
                        "is_put": True,
                        "option_price": max(
                            0.5, (100 - k) * 0.1 + 0.5
                        ),  # simple dummy prices
                        "expiration_date": "2025-01-01",
                    }
                )

        # Calls (Out of money calls: strikes > spot. ATM call: 100)
        for k in strikes:
            if k >= 100:
                data.append(
                    {
                        "stock_price": spot,
                        "strike_price": float(k),
                        "is_put": False,
                        "option_price": max(0.5, (k - 100) * 0.1 + 0.5),
                        "expiration_date": "2025-01-01",
                    }
                )

        df = pd.DataFrame(data)

        time_to_maturity = 30.0 / 365.0
        risk_free_rate = 0.05

        mfiv = calculate_mfiv_from_df(df, time_to_maturity, risk_free_rate)

        self.assertFalse(np.isnan(mfiv))
        self.assertTrue(mfiv > 0.0)

    def test_calculate_mfiv_empty_df(self):
        df = pd.DataFrame()
        mfiv = calculate_mfiv_from_df(df, 30.0 / 365.0, 0.05)
        self.assertTrue(np.isnan(mfiv))

    def test_calculate_mfiv_multiple_expiries(self):
        data = [
            {
                "stock_price": 100.0,
                "strike_price": 100.0,
                "is_put": False,
                "option_price": 1.0,
                "expiration_date": "2025-01-01",
            },
            {
                "stock_price": 100.0,
                "strike_price": 100.0,
                "is_put": False,
                "option_price": 1.0,
                "expiration_date": "2025-02-01",
            },
        ]
        df = pd.DataFrame(data)

        with self.assertRaises(ValueError):
            calculate_mfiv_from_df(df, 30.0 / 365.0, 0.05)


if __name__ == "__main__":
    unittest.main()
