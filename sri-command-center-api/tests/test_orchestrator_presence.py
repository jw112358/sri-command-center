import json
import unittest
from unittest.mock import patch

from app.config import settings
from app.services import orchestrator_presence


class FakeRequest:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeFiles:
    def __init__(self):
        self.content = None

    def list(self, **_kwargs):
        return FakeRequest({"files": [{"id": "presence-file"}] if self.content else []})

    def get_media(self, **_kwargs):
        return FakeRequest(self.content)

    def update(self, **kwargs):
        media = kwargs["media_body"]
        self.content = media.getbytes(0, media.size())
        return FakeRequest({"id": "presence-file"})

    def create(self, **kwargs):
        media = kwargs["media_body"]
        self.content = media.getbytes(0, media.size())
        return FakeRequest({"id": "presence-file"})


class FakeDrive:
    def __init__(self):
        self._files = FakeFiles()

    def files(self):
        return self._files


class OrchestratorPresenceTests(unittest.TestCase):
    def setUp(self):
        self.original_parent = settings.drive_root_folder_id
        self.original_write = settings.dashboard_drive_write_enabled
        settings.drive_root_folder_id = "dashboard-root"
        settings.dashboard_drive_write_enabled = True
        orchestrator_presence._file_id = None
        orchestrator_presence._last_seen.clear()
        orchestrator_presence._cache_at = 0.0

    def tearDown(self):
        settings.drive_root_folder_id = self.original_parent
        settings.dashboard_drive_write_enabled = self.original_write
        orchestrator_presence._file_id = None
        orchestrator_presence._last_seen.clear()
        orchestrator_presence._cache_at = 0.0

    def test_heartbeat_is_visible_to_a_fresh_process_cache(self):
        service = FakeDrive()
        with patch("app.services.orchestrator_presence.drive.get_drive_service", return_value=service):
            orchestrator_presence.record_heartbeat("codex-master-builder")
            persisted = json.loads(service._files.content.decode("utf-8"))
            self.assertIn("codex-master-builder", persisted["workers"])

            # Simulate a second Render process with an empty in-memory cache.
            orchestrator_presence._last_seen.clear()
            orchestrator_presence._cache_at = 0.0
            status = orchestrator_presence.presence_status()

        self.assertTrue(status["connected"])
        self.assertEqual(["codex-master-builder"], status["workers"])


if __name__ == "__main__":
    unittest.main()
