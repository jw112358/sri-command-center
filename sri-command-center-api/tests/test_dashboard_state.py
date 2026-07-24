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

    def test_task_completion_timestamps_and_reopens(self):
        task = self.store.create_task("Verify deployment")
        completed = self.store.patch_task(task.id, {"done": True})
        self.assertTrue(completed.done)
        self.assertIsNotNone(completed.completedAt)
        reopened = self.store.patch_task(task.id, {"done": False})
        self.assertFalse(reopened.done)
        self.assertIsNone(reopened.completedAt)

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
