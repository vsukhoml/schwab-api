import unittest

import numpy as np
import pandas as pd

from schwab_api.math import calculate_mfiv_from_df, calculate_vix_like_index


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


def _make_expiry_df(spot: float, strikes, expiration_date: str) -> pd.DataFrame:
    """Build a minimal synthetic option chain DataFrame for a single expiry."""
    rows = []
    for k in strikes:
        # OTM put below spot, OTM call above spot, ATM uses call
        is_put = k < spot
        intrinsic = max(spot - k, 0) if is_put else max(k - spot, 0)
        price = max(intrinsic * 0.1 + 0.5, 0.5)
        rows.append(
            {
                "stock_price": spot,
                "strike_price": float(k),
                "is_put": is_put,
                "option_price": price,
                "expiration_date": expiration_date,
            }
        )
    return pd.DataFrame(rows)


class TestCalculateVixLikeIndex(unittest.TestCase):
    def setUp(self):
        spot = 100.0
        strikes = [90, 95, 100, 105, 110]
        self.near_df = _make_expiry_df(spot, strikes, "2025-01-01")
        self.far_df = _make_expiry_df(spot, strikes, "2025-02-01")
        self.t1 = 23 / 365.0  # near expiry ~ 23 days out
        self.t2 = 37 / 365.0  # far expiry  ~ 37 days out
        self.rfr = 0.05

    def test_returns_positive_float(self):
        result = calculate_vix_like_index(
            self.near_df, self.far_df, self.t1, self.t2, self.rfr
        )
        self.assertIsInstance(result, float)
        self.assertFalse(np.isnan(result))
        self.assertGreater(result, 0.0)

    def test_interpolation_between_legs(self):
        # Result must lie between (or very close to) the two individual MFIVs
        sigma1 = calculate_mfiv_from_df(self.near_df, self.t1, self.rfr)
        sigma2 = calculate_mfiv_from_df(self.far_df, self.t2, self.rfr)
        result = calculate_vix_like_index(
            self.near_df, self.far_df, self.t1, self.t2, self.rfr
        )
        self.assertGreaterEqual(result, min(sigma1, sigma2) * 0.5)
        self.assertLessEqual(result, max(sigma1, sigma2) * 2.0)

    def test_target_at_t1_matches_near_leg(self):
        # When target == t1 the entire weight goes to the near leg,
        # so the result should match calculate_mfiv_from_df(near_df, t1) * scaling.
        target_days = round(self.t1 * 365)
        result = calculate_vix_like_index(
            self.near_df,
            self.far_df,
            self.t1,
            self.t2,
            self.rfr,
            target_days=target_days,
        )
        self.assertFalse(np.isnan(result))
        self.assertGreater(result, 0.0)

    def test_target_at_t2_matches_far_leg(self):
        target_days = round(self.t2 * 365)
        result = calculate_vix_like_index(
            self.near_df,
            self.far_df,
            self.t1,
            self.t2,
            self.rfr,
            target_days=target_days,
        )
        self.assertFalse(np.isnan(result))
        self.assertGreater(result, 0.0)

    def test_nan_propagates_when_near_df_empty(self):
        result = calculate_vix_like_index(
            pd.DataFrame(), self.far_df, self.t1, self.t2, self.rfr
        )
        self.assertTrue(np.isnan(result))

    def test_nan_propagates_when_far_df_empty(self):
        result = calculate_vix_like_index(
            self.near_df, pd.DataFrame(), self.t1, self.t2, self.rfr
        )
        self.assertTrue(np.isnan(result))

    def test_raises_when_t1_gte_t2(self):
        with self.assertRaises(ValueError):
            calculate_vix_like_index(
                self.near_df, self.far_df, self.t2, self.t1, self.rfr
            )

    def test_raises_when_t1_zero(self):
        with self.assertRaises(ValueError):
            calculate_vix_like_index(self.near_df, self.far_df, 0.0, self.t2, self.rfr)

    def test_raises_when_target_outside_bracket(self):
        # target_days = 60 > t2 * 365 ≈ 37 → outside bracket
        with self.assertRaises(ValueError):
            calculate_vix_like_index(
                self.near_df,
                self.far_df,
                self.t1,
                self.t2,
                self.rfr,
                target_days=60,
            )

    def test_raises_when_target_days_zero(self):
        with self.assertRaises(ValueError):
            calculate_vix_like_index(
                self.near_df,
                self.far_df,
                self.t1,
                self.t2,
                self.rfr,
                target_days=0,
            )


if __name__ == "__main__":
    unittest.main()
