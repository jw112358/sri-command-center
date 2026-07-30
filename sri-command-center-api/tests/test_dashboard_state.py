import copy
import unittest

from app.models import Lane, Priority
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


class DashboardStateStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryDashboardStateStore()

    def test_note_lifecycle_is_durable(self):
        created = self.store.create_note(
            title="Build note",
            tag="builder",
            body="# Progress",
        )
        self.assertEqual(created.id, self.store.get_note(created.id).id)
        updated = self.store.upsert_note(created, {"title": "Updated"})
        self.assertEqual("Updated", updated.title)
        self.assertTrue(self.store.delete_note(created.id))
        self.assertIsNone(self.store.get_note(created.id))

    def test_task_requires_review_and_operator_approval_before_completion(self):
        task = self.store.create_task("Verify deployment")
        claimed = self.store.claim_tasks("codex", 1)[0]
        self.assertEqual("running", claimed.status)
        review_ready = self.store.mark_task_review_ready(
            task.id,
            worker_id="codex",
            summary_id="brief:review",
            review_url="https://example.test/review",
            evidence_urls=["https://example.test/checks"],
        )
        self.assertEqual("review_ready", review_ready.status)
        shipping = self.store.approve_task_for_shipping(task.id)
        self.assertEqual("shipping", shipping.status)
        completed = self.store.complete_task(
            task.id,
            worker_id="codex",
            summary_id="brief:complete",
            evidence_urls=["https://example.test/production"],
        )
        self.assertEqual("completed", completed.status)
        self.assertTrue(completed.done)
        self.assertIsNotNone(completed.completedAt)

    def test_task_claims_respect_four_slot_cap(self):
        for index in range(6):
            self.store.create_task(f"Task {index}")
        first = self.store.claim_tasks("codex", 4)
        second = self.store.claim_tasks("claude", 4)
        self.assertEqual(4, len(first))
        self.assertEqual([], second)

    def test_blocked_task_can_be_requeued(self):
        task = self.store.create_task("Blocked build")
        self.store.claim_tasks("opencode", 1)
        blocked = self.store.block_task(
            task.id,
            worker_id="opencode",
            reason="Dependency unavailable",
            summary_id="brief:blocked",
            evidence_urls=[],
        )
        self.assertEqual("blocked", blocked.status)
        requeued = self.store.requeue_task(task.id)
        self.assertEqual("queued", requeued.status)
        self.assertIsNone(requeued.assignedAgent)

    def test_project_create_and_lane_update(self):
        project = self.store.create_project(
            name="Mission Control",
            os_id="builder",
            owner="Jeffery Williams",
            priority=Priority.HIGH,
        )
        moved = self.store.upsert_project(
            project.model_copy(update={"lane": Lane.IN_PROGRESS})
        )
        self.assertEqual("IN PROGRESS", moved.lane)
        self.assertEqual(1, len(self.store.list_projects()))
        self.assertTrue(self.store.delete_project(project.id))


if __name__ == "__main__":
    unittest.main()
