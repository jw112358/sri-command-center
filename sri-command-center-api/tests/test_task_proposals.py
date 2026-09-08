from __future__ import annotations

import threading
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import task_proposals
from app.routers.legal import require_operator
from app.services.orchestrator_auth import require_orchestrator_worker


class FakeStore:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {"tasks": {}, "taskProposals": {}}

    def _load(self, fresh: bool = False):
        return self.state

    def _save(self, state):
        self.state = state


class TaskProposalTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        task_proposals.get_dashboard_store = lambda: self.store
        app = FastAPI()
        app.include_router(task_proposals.router)
        app.dependency_overrides[require_orchestrator_worker] = lambda: "orchestrator-worker"
        app.dependency_overrides[require_operator] = lambda: "operator@example.com"
        self.app = app
        self.client = TestClient(app)

    def _propose(self):
        response = self.client.post(
            "/api/tasks/proposed",
            json={
                "text": "Run a harmless Builder OS verification",
                "project": "Master Builder",
                "preferredSurface": "claude",
                "agentId": "program-gm",
            },
        )
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    def test_proposal_is_not_executable_until_operator_promotes_it(self):
        proposal = self._propose()
        self.assertEqual("proposed", proposal["status"])
        self.assertEqual("program-gm", proposal["proposedBy"])
        self.assertEqual("orchestrator-worker", proposal["authenticatedPrincipal"])
        self.assertEqual({}, self.store.state["tasks"])
        self.assertIn(proposal["id"], self.store.state["taskProposals"])

        promoted = self.client.post(f"/api/tasks/proposed/{proposal['id']}/promote")
        self.assertEqual(200, promoted.status_code, promoted.text)
        task = promoted.json()
        self.assertEqual("queued", task["status"])
        self.assertIn(task["id"], self.store.state["tasks"])
        record = self.store.state["taskProposals"][proposal["id"]]
        self.assertEqual("promoted", record["status"])
        self.assertEqual(task["id"], record["promotedTaskId"])

    def test_promotion_is_operator_only(self):
        proposal = self._propose()

        def deny_operator():
            raise HTTPException(401, "operator required")

        self.app.dependency_overrides[require_operator] = deny_operator
        denied = self.client.post(f"/api/tasks/proposed/{proposal['id']}/promote")
        self.assertEqual(401, denied.status_code)
        self.assertEqual({}, self.store.state["tasks"])

    def test_operator_can_reject_without_creating_a_task(self):
        proposal = self._propose()
        rejected = self.client.post(f"/api/tasks/proposed/{proposal['id']}/reject")
        self.assertEqual(200, rejected.status_code, rejected.text)
        self.assertEqual("rejected", rejected.json()["status"])
        self.assertEqual({}, self.store.state["tasks"])

    def test_operator_listing_surfaces_proposals_separately(self):
        proposal = self._propose()
        response = self.client.get("/api/tasks/proposed")
        self.assertEqual(200, response.status_code, response.text)
        rows = response.json()
        self.assertEqual(1, len(rows))
        self.assertEqual(proposal["id"], rows[0]["id"])
        self.assertEqual("proposed", rows[0]["status"])


if __name__ == "__main__":
    unittest.main()
