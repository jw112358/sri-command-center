import unittest
from unittest.mock import patch

from app.config import settings
from app.services.legal_auth import (
    google_operator_auth_enabled,
    verify_google_credential,
)
from app.services.legal_google import legal_runner_config_errors


class LegalGoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.original = {
            "client_id": settings.legal_google_client_id,
            "session_secret": settings.legal_session_secret,
            "operator_email": settings.legal_operator_email,
            "workspace_domain": settings.legal_google_workspace_domain,
            "state_persistent": settings.legal_state_persistent,
            "drive_folder": settings.legal_drive_matters_folder_id,
            "user_token": settings.legal_google_user_token_json,
            "allow_adc": settings.legal_google_allow_adc,
        }
        settings.legal_google_client_id = "web-client.apps.googleusercontent.com"
        settings.legal_session_secret = "a" * 32
        settings.legal_operator_email = "jeff@sri-intel.com"
        settings.legal_google_workspace_domain = "sri-intel.com"

    def tearDown(self):
        settings.legal_google_client_id = self.original["client_id"]
        settings.legal_session_secret = self.original["session_secret"]
        settings.legal_operator_email = self.original["operator_email"]
        settings.legal_google_workspace_domain = self.original["workspace_domain"]
        settings.legal_state_persistent = self.original["state_persistent"]
        settings.legal_drive_matters_folder_id = self.original["drive_folder"]
        settings.legal_google_user_token_json = self.original["user_token"]
        settings.legal_google_allow_adc = self.original["allow_adc"]

    def test_google_auth_requires_strong_session_secret(self):
        settings.legal_session_secret = "too-short"
        self.assertFalse(google_operator_auth_enabled())

    @patch("app.services.legal_auth.id_token.verify_oauth2_token")
    def test_exact_verified_workspace_operator_is_accepted(self, verify):
        verify.return_value = {
            "sub": "google-subject",
            "email": "jeff@sri-intel.com",
            "email_verified": True,
            "hd": "sri-intel.com",
        }
        claims = verify_google_credential("credential")
        self.assertEqual("google-subject", claims["sub"])

    @patch("app.services.legal_auth.id_token.verify_oauth2_token")
    def test_other_workspace_user_is_rejected(self, verify):
        verify.return_value = {
            "sub": "other-subject",
            "email": "other@sri-intel.com",
            "email_verified": True,
            "hd": "sri-intel.com",
        }
        with self.assertRaises(ValueError):
            verify_google_credential("credential")

    def test_gmail_runner_blocks_incomplete_production_configuration(self):
        settings.legal_state_persistent = False
        settings.legal_drive_matters_folder_id = ""
        settings.legal_google_user_token_json = ""
        settings.legal_google_allow_adc = False
        self.assertEqual(3, len(legal_runner_config_errors()))

    def test_gmail_runner_accepts_complete_shadow_configuration(self):
        settings.legal_state_persistent = True
        settings.legal_drive_matters_folder_id = "drive-folder"
        settings.legal_google_user_token_json = '{"refresh_token":"secret"}'
        settings.legal_google_allow_adc = False
        self.assertEqual([], legal_runner_config_errors())


if __name__ == "__main__":
    unittest.main()
