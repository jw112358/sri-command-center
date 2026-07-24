import unittest

from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app
from app.services import drive


class CommandSecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_api_token = settings.legal_api_token
        self.original_client_id = settings.legal_google_client_id
        self.original_session_secret = settings.legal_session_secret
        self.original_dispatch = settings.command_dispatch_enabled
        settings.legal_api_token = ""
        settings.legal_google_client_id = ""
        settings.legal_session_secret = ""
        settings.command_dispatch_enabled = False
        self.client = TestClient(create_app())

    def tearDown(self):
        settings.legal_api_token = self.original_api_token
        settings.legal_google_client_id = self.original_client_id
        settings.legal_session_secret = self.original_session_secret
        settings.command_dispatch_enabled = self.original_dispatch

    def test_private_dashboard_reads_require_operator_auth(self):
        for path in (
            "/api/agents",
            "/api/projects",
            "/api/notes",
            "/api/tasks",
            "/api/session-briefs",
            "/api/graph",
            "/api/events",
            "/api/legal/dashboard",
            "/api/legal/matters",
            "/api/legal/assignments",
        ):
            with self.subTest(path=path):
                self.assertEqual(503, self.client.get(path).status_code)

    def test_public_health_and_capability_status_remain_available(self):
        self.assertEqual(200, self.client.get("/api/health").status_code)
        response = self.client.get("/api/capabilities")
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json()["commandDispatchEnabled"])

    def test_disabled_dispatch_never_reports_noop_success(self):
        self.assertFalse(
            drive.write_signal(
                "builder",
                "launch",
                {"status": "RUNNING"},
            )
        )

    def test_launch_is_rejected_when_adapter_is_not_connected(self):
        settings.legal_api_token = "test-operator-token"
        response = self.client.post(
            "/api/os/builder/launch",
            headers={"Authorization": "Bearer test-operator-token"},
            json={},
        )
        self.assertEqual(503, response.status_code)
        self.assertIn("adapter", response.json()["detail"].lower())

    def test_live_event_stream_requires_operator_token(self):
        settings.legal_api_token = "test-operator-token"
        with self.client.websocket_connect("/ws") as websocket:
            websocket.send_json(
                {"type": "auth", "token": "test-operator-token"}
            )
            self.assertEqual(
                {"type": "authenticated"},
                websocket.receive_json(),
            )


if __name__ == "__main__":
    unittest.main()
