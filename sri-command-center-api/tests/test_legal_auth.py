import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.config import settings
from app.routers.legal import require_operator
from app.services.legal_auth import create_operator_session, verify_operator_session


class LegalOperatorAuthTests(unittest.TestCase):
    def setUp(self):
        self.original_api_token = settings.legal_api_token
        self.original_client_id = settings.legal_google_client_id
        self.original_session_secret = settings.legal_session_secret
        self.original_operator_email = settings.legal_operator_email
        settings.legal_google_client_id = ""
        settings.legal_session_secret = ""
        settings.legal_operator_email = "jeff@sri-intel.com"

    def tearDown(self):
        settings.legal_api_token = self.original_api_token
        settings.legal_google_client_id = self.original_client_id
        settings.legal_session_secret = self.original_session_secret
        settings.legal_operator_email = self.original_operator_email

    def test_mutation_is_unavailable_without_configured_auth(self):
        settings.legal_api_token = ""
        with self.assertRaises(HTTPException) as raised:
            require_operator(None)
        self.assertEqual(503, raised.exception.status_code)

    def test_mutation_rejects_wrong_token(self):
        settings.legal_api_token = "correct"
        with self.assertRaises(HTTPException) as raised:
            require_operator("Bearer wrong")
        self.assertEqual(401, raised.exception.status_code)

    def test_mutation_accepts_exact_bearer_token(self):
        settings.legal_api_token = "correct"
        principal = require_operator("Bearer correct")
        self.assertEqual("jeff@sri-intel.com", principal.email)

    def test_signed_operator_session_is_accepted(self):
        settings.legal_api_token = ""
        settings.legal_google_client_id = "web-client.apps.googleusercontent.com"
        settings.legal_session_secret = "test-secret-with-sufficient-entropy"
        token, expected = create_operator_session(
            {"sub": "google-subject", "email": "jeff@sri-intel.com"}
        )
        actual = require_operator(f"Bearer {token}")
        self.assertEqual(expected.email, actual.email)
        self.assertEqual(expected.subject, actual.subject)

    def test_tampered_operator_session_is_rejected(self):
        settings.legal_api_token = ""
        settings.legal_google_client_id = "web-client.apps.googleusercontent.com"
        settings.legal_session_secret = "test-secret-with-sufficient-entropy"
        token, _ = create_operator_session(
            {"sub": "google-subject", "email": "jeff@sri-intel.com"}
        )
        with self.assertRaises(HTTPException) as raised:
            require_operator(f"Bearer {token}tampered")
        self.assertEqual(401, raised.exception.status_code)

    def test_expired_operator_session_is_rejected(self):
        settings.legal_api_token = ""
        settings.legal_google_client_id = "web-client.apps.googleusercontent.com"
        settings.legal_session_secret = "test-secret-with-sufficient-entropy"
        with patch("app.services.legal_auth.time.time", return_value=1_000):
            token, _ = create_operator_session(
                {"sub": "google-subject", "email": "jeff@sri-intel.com"}
            )
        with patch("app.services.legal_auth.time.time", return_value=10_000):
            with self.assertRaises(ValueError):
                verify_operator_session(token)


if __name__ == "__main__":
    unittest.main()
