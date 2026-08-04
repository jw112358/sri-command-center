import unittest
from unittest.mock import patch

from app.config import settings
from app.services import drive


class DriveAuthPriorityTests(unittest.TestCase):
    def setUp(self):
        self.original = {
            "user": settings.legal_google_user_token_json,
            "service": settings.google_service_account_json,
            "adc": settings.legal_google_allow_adc,
        }
        drive._drive_service = None
        drive._drive_service_attempted = False

    def tearDown(self):
        settings.legal_google_user_token_json = self.original["user"]
        settings.google_service_account_json = self.original["service"]
        settings.legal_google_allow_adc = self.original["adc"]
        drive._drive_service = None
        drive._drive_service_attempted = False

    def test_configured_user_grant_wins_over_ambient_adc(self):
        settings.legal_google_user_token_json = '{"refresh_token":"configured"}'
        settings.google_service_account_json = ""
        settings.legal_google_allow_adc = True
        configured_credentials = object()
        expected_service = object()

        with (
            patch(
                "app.services.legal_google.load_legal_google_credentials",
                return_value=configured_credentials,
            ),
            patch("googleapiclient.discovery.build", return_value=expected_service) as build,
            patch("google.auth.default", side_effect=AssertionError("ADC must not win")),
        ):
            self.assertIs(expected_service, drive.get_drive_service())

        self.assertIs(configured_credentials, build.call_args.kwargs["credentials"])


if __name__ == "__main__":
    unittest.main()
