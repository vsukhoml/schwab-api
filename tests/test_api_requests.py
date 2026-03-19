import unittest
from unittest.mock import MagicMock, patch

from schwab_api.client import Client
from schwab_api.exceptions import AuthError, InvalidRequestError, RateLimitError


class TestClientAPIRequests(unittest.TestCase):
    @patch("schwab_api.client.Tokens")
    @patch("schwab_api.client.c_requests.Session")
    def setUp(self, mock_session_class, mock_tokens_class):
        # Initialize client with dummy credentials and prevent actual token updates
        self.mock_tokens_instance = mock_tokens_class.return_value
        self.mock_tokens_instance.access_token = "DUMMY_TOKEN"
        self.mock_tokens_instance.update_tokens.return_value = False

        # Mock the requests session
        self.mock_session_instance = mock_session_class.return_value
        self.mock_session_instance.headers = {}

        self.client = Client("DUMMY_KEY", "DUMMY_SECRET")
        self.client.tokens = self.mock_tokens_instance
        self.client._session = self.mock_session_instance
        self.client._session.headers.update({"Authorization": "Bearer DUMMY_TOKEN"})

    def _create_mock_response(self, status_code, json_data=None, text=""):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.ok = status_code < 400
        mock_resp.text = text
        if json_data is not None:
            mock_resp.json.return_value = json_data
        return mock_resp

    def test_linked_accounts_success(self):
        # Mock the endpoint
        mock_data = [{"accountNumber": "12345678", "hashValue": "A1B2C3D4"}]
        self.mock_session_instance.request.return_value = self._create_mock_response(
            200, mock_data
        )

        resp = self.client.linked_accounts()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), mock_data)

        # Verify call arguments
        self.mock_session_instance.request.assert_called_with(
            "GET",
            "https://api.schwabapi.com/trader/v1/accounts/accountNumbers",
            timeout=10,
        )

    def test_account_details_all(self):
        mock_data = [{"securitiesAccount": {"accountNumber": "12345678"}}]
        self.mock_session_instance.request.return_value = self._create_mock_response(
            200, mock_data
        )

        resp = self.client.account_details_all(fields="positions")
        self.assertEqual(resp.json(), mock_data)

        # Check query string parsing
        self.mock_session_instance.request.assert_called_with(
            "GET",
            "https://api.schwabapi.com/trader/v1/accounts/",
            params={"fields": "positions"},
            timeout=10,
        )

    def test_place_order(self):
        dummy_order = {"orderType": "MARKET", "session": "NORMAL"}
        self.mock_session_instance.request.return_value = self._create_mock_response(
            201
        )

        resp = self.client.place_order("HASH123", dummy_order)
        self.assertEqual(resp.status_code, 201)

        # Verify JSON body
        self.mock_session_instance.request.assert_called_with(
            "POST",
            "https://api.schwabapi.com/trader/v1/accounts/HASH123/orders",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=dummy_order,
            timeout=10,
        )

    def test_check_response_decorator_429(self):
        self.mock_session_instance.request.return_value = self._create_mock_response(
            429, text="Rate limit exceeded"
        )

        with self.assertRaises(RateLimitError):
            self.client.quotes("AAPL")

    def test_check_response_decorator_401(self):
        self.mock_session_instance.request.return_value = self._create_mock_response(
            401, text="Unauthorized"
        )

        with self.assertRaises(AuthError):
            self.client.option_chains("GOOG")

    def test_check_response_decorator_400(self):
        self.mock_session_instance.request.return_value = self._create_mock_response(
            400, text="Invalid parameters"
        )

        with self.assertRaises(InvalidRequestError):
            self.client.price_history("GOOG")


if __name__ == "__main__":
    unittest.main()
