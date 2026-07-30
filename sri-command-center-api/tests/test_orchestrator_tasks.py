import copy
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app
from app.models import SessionBrief
from app.services.dashboard_state import DashboardStateStore, _empty_state


class MemoryDashboardStateStore(DashboardStateStore):
    def __init__(self):
        super().__init__()
        self.state = _empty_state()

    def _read_drive_state(self):
        return copy.deepcopy(self.state)

    def _save(self, state):
        self.state = copy.deepcopy(state)
        self._cache = copy.deepcopy(state)


def fake_brief(body):
    return SessionBrief(
        id=f"brief:{body.status}",
        sessionId=f"session-{body.status}",
        date="2026-07-30",
        title=body.title,
        project=body.project,
        surface=body.surface,
        status=body.status,
        summary=body.summary,
        currentState=body.currentState,
        nextStart=body.nextStart,
        sourceUrl="https://drive.google.com/file/d/summary/view",
        updatedAt="2026-07-30T12:00:00Z",
        taskId=body.taskId,
    )


class OrchestratorTaskApiTests(unittest.TestCase):
    def setUp(self):
        self.old_operator = settings.legal_api_token
        self.old_runner = settings.orchestrator_runner_token
        settings.legal_api_token = "operator-token"
        settings.orchestrator_runner_token = "runner-token"
        self.store = MemoryDashboardStateStore()
        self.store_patch = patch(
            "app.routers.tasks.get_dashboard_store",
            return_value=self.store,
        )
        self.summary_patch = patch(
            "app.routers.tasks.create_session_summary",
            side_effect=fake_brief,
        )
        self.store_patch.start()
        self.summary_patch.start()
        self.client = TestClient(create_app())
        self.operator_headers = {"Authorization": "Bearer operator-token"}
        self.runner_headers = {"Authorization": "Bearer runner-token"}

    def tearDown(self):
        self.store_patch.stop()
        self.summary_patch.stop()
        settings.legal_api_token = self.old_operator
        settings.orchestrator_runner_token = self.old_runner

    def test_full_review_and_ship_lifecycle(self):
        created = self.client.post(
            "/api/tasks",
            headers=self.operator_headers,
            json={"text": "Ship the dashboard", "project": "Master Builder"},
        )
        self.assertEqual(201, created.status_code)
        task_id = created.json()["id"]
        self.assertEqual("queued", created.json()["status"])

        claimed = self.client.post(
            "/api/tasks/claim",
            headers=self.runner_headers,
            json={"workerId": "codex", "limit": 1},
        )
        self.assertEqual("running", claimed.json()[0]["status"])

        review = self.client.post(
            f"/api/tasks/{task_id}/review-ready",
            headers=self.runner_headers,
            json={
                "workerId": "codex",
                "surface": "Codex",
                "title": "Dashboard ready",
                "summary": "Implementation and checks are complete.",
                "currentState": "Awaiting Jeff's review.",
                "nextStart": "Review the packet and approve shipping if satisfied.",
                "reviewUrl": "https://github.com/example/pull/1",
                "evidenceUrls": ["https://github.com/example/checks"],
            },
        )
        self.assertEqual("review_ready", review.json()["status"])
        self.assertEqual("brief:review-ready", review.json()["summaryId"])

        rejected = self.client.post(
            f"/api/tasks/{task_id}/approve-ship",
            headers=self.runner_headers,
        )
        self.assertEqual(401, rejected.status_code)

        approved = self.client.post(
            f"/api/tasks/{task_id}/approve-ship",
            headers=self.operator_headers,
        )
        self.assertEqual("shipping", approved.json()["status"])

        shipping_work = self.client.post(
            "/api/tasks/claim",
            headers=self.runner_headers,
            json={"workerId": "codex", "limit": 1},
        )
        self.assertEqual("shipping", shipping_work.json()[0]["status"])

        completed = self.client.post(
            f"/api/tasks/{task_id}/complete",
            headers=self.runner_headers,
            json={
                "workerId": "codex",
                "finalSummary": "Production deployment passed verification.",
                "evidenceUrls": ["https://example.test/production"],
            },
        )
        self.assertEqual("completed", completed.json()["status"])
        self.assertTrue(completed.json()["done"])

    def test_worker_cannot_claim_without_runner_authentication(self):
        response = self.client.post(
            "/api/tasks/claim",
            headers=self.operator_headers,
            json={"workerId": "codex", "limit": 1},
        )
        self.assertEqual(401, response.status_code)


if __name__ == "__main__":
    unittest.main()
