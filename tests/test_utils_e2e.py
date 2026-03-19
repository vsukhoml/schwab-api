import datetime
import json
import os
import unittest

from schwab_api.utils import parse_option_chain_to_df, parse_price_history_to_df


class TestUtilsE2E(unittest.TestCase):
    def setUp(self):
        self.dumps_dir = os.path.join(os.path.dirname(__file__), "..", "e2e_dumps")

    def test_parse_option_chain(self):
        chain_file = os.path.join(self.dumps_dir, "option_chains.json")
        if not os.path.exists(chain_file):
            self.skipTest(f"{chain_file} not found")

        with open(chain_file, "r") as f:
            chain_json = json.load(f)

        eval_date = datetime.date(2025, 3, 27)
        df = parse_option_chain_to_df(chain_json, evaluation_date=eval_date)

        self.assertFalse(df.empty)
        self.assertIn("ticker", df.columns)
        self.assertIn("strike_price", df.columns)
        self.assertIn("delta", df.columns)
        self.assertIn("gamma", df.columns)

    def test_parse_price_history(self):
        history_file = os.path.join(self.dumps_dir, "price_history.json")
        if not os.path.exists(history_file):
            self.skipTest(f"{history_file} not found")

        with open(history_file, "r") as f:
            history_json = json.load(f)

        df = parse_price_history_to_df(history_json)
        self.assertFalse(df.empty)
        self.assertIn("Close", df.columns)
        self.assertIn("Volume", df.columns)


if __name__ == "__main__":
    unittest.main()
