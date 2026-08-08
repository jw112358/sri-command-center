import copy
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app
from app.services.dashboard_state import DashboardStateStore, _empty_state


class MemoryStore(DashboardStateStore):
    def __init__(self):
        super().__init__()
        self.state = _empty_state()

    def _read_drive_state(self):
        return copy.deepcopy(self.state)

    def _save(self, state):
        self.state = copy.deepcopy(state)
        self._cache = copy.deepcopy(state)


class MarketingApiTests(unittest.TestCase):
    def setUp(self):
        self.old_token = settings.legal_api_token
        settings.legal_api_token = "operator-token"
        self.store = MemoryStore()
        self.patch = patch("app.routers.marketing.get_dashboard_store", return_value=self.store)
        self.patch.start()
        self.client = TestClient(create_app())
        self.headers = {"Authorization": "Bearer operator-token"}

    def tearDown(self):
        self.patch.stop()
        settings.legal_api_token = self.old_token

    def test_dashboard_requires_operator_and_uses_real_destination(self):
        self.assertEqual(401, self.client.get("/api/marketing/dashboard").status_code)
        response = self.client.get("/api/marketing/dashboard", headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual(3, len(response.json()["approvals"]))
        self.assertIn("gtd-v2-frontend.onrender.com", response.json()["destination"])

    def test_approval_is_durable_and_does_not_publish(self):
        approval_id = "gtd-v2-daily-briefing-launch-001-linkedin"
        response = self.client.post(
            f"/api/marketing/approvals/{approval_id}",
            headers=self.headers,
            json={"approved": True},
        )
        self.assertEqual(200, response.status_code)
        item = next(item for item in response.json()["approvals"] if item["id"] == approval_id)
        self.assertEqual("approved", item["status"])
        self.assertEqual("publish", item["requestedAction"])


if __name__ == "__main__":
    unittest.main()
