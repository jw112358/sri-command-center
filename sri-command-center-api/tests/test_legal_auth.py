import unittest

from fastapi import HTTPException

from app.config import settings
from app.routers.legal import require_operator


class LegalOperatorAuthTests(unittest.TestCase):
    def setUp(self):
        self.original = settings.legal_api_token

    def tearDown(self):
        settings.legal_api_token = self.original

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
        self.assertIsNone(require_operator("Bearer correct"))


if __name__ == "__main__":
    unittest.main()
