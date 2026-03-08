import datetime
import json
import unittest

from schwab_api.utils import TIMEZONE_EST, decode_schwab_dates


class TestDateParsing(unittest.TestCase):
    def test_decode_schwab_dates(self):
        raw_json = """
        {
            "dividendDate": "2026-02-09 03:00:00-05:00",
            "expirationDate": "2026-03-09T20:00:00.000+00:00",
            "declarationDate": "2026-01-29 00:00:00.0",
            "quoteTime": 1772787600000,
            "tradeTime": 1772787598000,
            "datetime": 1772845139628,
            "regularString": "2026-02-09",
            "marketCap": 3821353930600,
            "nested": {
                "innerDate": "2026-02-12 03:00:00-05:00"
            }
        }
        """

        parsed = json.loads(raw_json, object_hook=decode_schwab_dates)

        # Check string date parsing (with explicit timezone)
        self.assertTrue(isinstance(parsed["dividendDate"], datetime.datetime))
        self.assertEqual(parsed["dividendDate"].year, 2026)
        self.assertEqual(parsed["dividendDate"].month, 2)

        # Check string date parsing (ISO format with T and Z/offset)
        self.assertTrue(isinstance(parsed["expirationDate"], datetime.datetime))
        self.assertEqual(parsed["expirationDate"].year, 2026)
        self.assertEqual(parsed["expirationDate"].month, 3)
        self.assertEqual(parsed["expirationDate"].day, 9)

        # Check string date parsing (naive datetime string -> should be localized to EST)
        self.assertTrue(isinstance(parsed["declarationDate"], datetime.datetime))
        self.assertIsNotNone(parsed["declarationDate"].tzinfo)

        # Check integer timestamp parsing (13-digit ms)
        self.assertTrue(isinstance(parsed["quoteTime"], datetime.datetime))
        self.assertEqual(parsed["quoteTime"].year, 2026)
        self.assertIsNotNone(parsed["quoteTime"].tzinfo)

        self.assertTrue(isinstance(parsed["datetime"], datetime.datetime))
        self.assertEqual(parsed["datetime"].year, 2026)

        # Check that it ignores regular strings and non-date integers
        self.assertEqual(parsed["regularString"], "2026-02-09")
        self.assertEqual(parsed["marketCap"], 3821353930600)

        # Check nested dict parsing
        self.assertTrue(isinstance(parsed["nested"]["innerDate"], datetime.datetime))


if __name__ == "__main__":
    unittest.main()
