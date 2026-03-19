import datetime
import unittest

from schwab_api.math import BlackScholesPricer


class TestBlackScholesPricer(unittest.TestCase):
    def test_call_option_at_the_money(self):
        # Textbook example parameters
        pricer = BlackScholesPricer(
            stock_price=100.0,
            strike_price=100.0,
            expiration_date=datetime.date.today() + datetime.timedelta(days=365),
            is_put=False,
            volatility=0.20,
            risk_free_rate=0.05,
            dividend_yield=0.0,
            evaluation_date=datetime.date.today(),
        )

        # d1 = 0.35, d2 = 0.15
        # N(0.35) = 0.63683

        delta = pricer.delta()
        self.assertAlmostEqual(delta, 0.63683, places=3)

        gamma = pricer.gamma()
        self.assertAlmostEqual(gamma, 0.01888, places=3)

        vega = pricer.vega()
        self.assertAlmostEqual(vega, 0.3752, places=3)

        theta = pricer.theta()
        self.assertTrue(theta < 0)  # Time decay should be negative

        rho = pricer.rho()
        self.assertTrue(rho > 0)

    def test_put_option_at_the_money(self):
        pricer = BlackScholesPricer(
            stock_price=100.0,
            strike_price=100.0,
            expiration_date=datetime.date.today() + datetime.timedelta(days=365),
            is_put=True,
            volatility=0.20,
            risk_free_rate=0.05,
            dividend_yield=0.0,
            evaluation_date=datetime.date.today(),
        )

        delta = pricer.delta()
        # Put delta = Call delta - 1 = 0.636831 - 1
        self.assertAlmostEqual(delta, -0.36317, places=5)

        gamma = pricer.gamma()
        # Gamma should be the same for put and call
        self.assertAlmostEqual(gamma, 0.01876, places=5)

        vega = pricer.vega()
        # Vega should be the same
        self.assertAlmostEqual(vega, 0.37524, places=5)

    def test_compute_all(self):
        pricer = BlackScholesPricer(
            stock_price=150.0,
            strike_price=160.0,
            expiration_date=datetime.date.today() + datetime.timedelta(days=30),
            is_put=False,
            volatility=0.30,
            risk_free_rate=0.05,
        )
        greeks = pricer.compute_all()
        self.assertIn("delta", greeks)
        self.assertIn("gamma", greeks)
        self.assertIn("theta", greeks)
        self.assertIn("vega", greeks)
        self.assertIn("rho", greeks)
        self.assertTrue(isinstance(greeks["delta"], float))

    def test_zero_iv_handling(self):
        # Should not raise division by zero
        pricer = BlackScholesPricer(
            stock_price=100.0,
            strike_price=100.0,
            expiration_date=datetime.date.today() + datetime.timedelta(days=30),
            is_put=False,
            volatility=0.0,
        )
        delta = pricer.delta()
        self.assertTrue(isinstance(delta, float))

    def test_zero_dte_handling(self):
        # Should not raise division by zero
        pricer = BlackScholesPricer(
            stock_price=100.0,
            strike_price=100.0,
            expiration_date=datetime.date.today(),
            is_put=False,
            volatility=0.20,
        )
        delta = pricer.delta()
        self.assertTrue(isinstance(delta, float))


if __name__ == "__main__":
    unittest.main()
