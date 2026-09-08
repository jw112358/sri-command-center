from __future__ import annotations

import threading
import unittest
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.models import Task, TaskStatus
from app.routers import task_proposals, tasks
from app.routers.legal import require_operator
from app.services.orchestrator_auth import require_orchestrator_worker


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeStore:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {"tasks": {}, "taskProposals": {}}

    def _load(self, fresh: bool = False):
        return self.state

    def _save(self, state):
        self.state = state

    def claim_tasks(self, worker_id: str, limit: int):
        claimed = []
        for raw in list(self.state["tasks"].values()):
            task = Task(**raw)
            if task.status != TaskStatus.QUEUED:
                continue
            updated = task.model_copy(update={
                "status": TaskStatus.RUNNING,
                "assignedAgent": worker_id,
                "startedAt": task.startedAt or _now(),
                "updatedAt": _now(),
            })
            self.state["tasks"][task.id] = updated.model_dump(mode="json")
            claimed.append(updated)
            if len(claimed) >= limit:
                break
        return claimed


class TaskProposalTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        task_proposals.get_dashboard_store = lambda: self.store
        tasks.get_dashboard_store = lambda: self.store
        tasks.record_heartbeat = lambda worker_id: _now()

        app = FastAPI()
        app.include_router(tasks.router)
        app.include_router(task_proposals.router)
        app.dependency_overrides[require_orchestrator_worker] = lambda: "orchestrator-worker"
        app.dependency_overrides[require_operator] = lambda: "operator@example.com"
        self.app = app
        self.client = TestClient(app)

    def _propose(self, suffix: str = ""):
        response = self.client.post(
            "/api/tasks/proposed",
            json={
                "text": f"Run a harmless Builder OS verification{suffix}",
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

        claim_before = self.client.post(
            "/api/tasks/claim",
            json={"workerId": "claude", "limit": 4},
        )
        self.assertEqual(200, claim_before.status_code, claim_before.text)
        self.assertEqual([], claim_before.json())

        promoted = self.client.post(f"/api/tasks/proposed/{proposal['id']}/promote")
        self.assertEqual(200, promoted.status_code, promoted.text)
        task = promoted.json()
        self.assertEqual("queued", task["status"])
        self.assertIn(task["id"], self.store.state["tasks"])
        record = self.store.state["taskProposals"][proposal["id"]]
        self.assertEqual("promoted", record["status"])
        self.assertEqual(task["id"], record["promotedTaskId"])

        claim_after = self.client.post(
            "/api/tasks/claim",
            json={"workerId": "claude", "limit": 4},
        )
        self.assertEqual(200, claim_after.status_code, claim_after.text)
        self.assertEqual(1, len(claim_after.json()))
        self.assertEqual(task["id"], claim_after.json()[0]["id"])
        self.assertEqual("running", claim_after.json()[0]["status"])

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

    def test_unpromoted_proposals_do_not_consume_worker_slots(self):
        for index in range(6):
            self._propose(f" {index}")
        first = next(iter(self.store.state["taskProposals"]))
        promoted = self.client.post(f"/api/tasks/proposed/{first}/promote")
        self.assertEqual(200, promoted.status_code, promoted.text)

        claimed = self.client.post(
            "/api/tasks/claim",
            json={"workerId": "codex", "limit": 4},
        )
        self.assertEqual(200, claimed.status_code, claimed.text)
        self.assertEqual(1, len(claimed.json()))
        self.assertEqual("running", claimed.json()[0]["status"])


if __name__ == "__main__":
    unittest.main()
