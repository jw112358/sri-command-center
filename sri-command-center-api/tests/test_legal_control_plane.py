import unittest
from unittest.mock import Mock, patch

from app.services.legal_control_plane import (
    LegalControlPlane,
    LegalControlPlaneError,
)


class LegalControlPlaneTests(unittest.TestCase):
    def setUp(self):
        self.control_plane = LegalControlPlane(
            base_url="https://legal.example.test",
            operator_token="server-secret",
        )

    @staticmethod
    def response(payload, status_code=200):
        response = Mock(status_code=status_code)
        response.json.return_value = payload
        return response

    @staticmethod
    def matter():
        return {
            "matter_id": "MAT-001",
            "version": 3,
            "status": "researching",
            "request_type": "strategy_memo",
            "practice_lane": "civil",
            "source_channel": "command_center",
            "client_name": "Example Client",
            "case_number": "2026-CP-00-0001",
            "current_summary": "Research underway.",
            "future_deadlines": ["2099-01-01"],
            "created_at": "2026-08-13T12:00:00Z",
            "updated_at": "2026-08-13T13:00:00Z",
        }

    @patch("app.services.legal_control_plane.httpx.get")
    def test_dashboard_maps_only_canonical_state(self, get):
        get.side_effect = [
            self.response(
                {
                    "active_matters": 1,
                    "capacity": 4,
                    "awaiting_review": 0,
                    "matters": [self.matter()],
                }
            ),
            self.response(
                {
                    "gmail_scanner_enabled": False,
                    "drive_root_configured": True,
                    "pipeline_paused": True,
                }
            ),
            self.response(
                {
                    "api_version": "0.8.0",
                    "control_plane": "sri-legal-agent-os-api",
                    "command_center_local_legal_state_permitted": False,
                    "matter_concurrency_cap": 4,
                }
            ),
        ]

        state = self.control_plane.dashboard()

        self.assertEqual(1, state.activeCount)
        self.assertEqual("MAT-001", state.matters[0].matterId)
        self.assertEqual("command_center", state.matters[0].sourceChannel)
        self.assertEqual("READY", state.connectors[0].status)
        self.assertEqual("STAGED", state.connectors[-1].status)
        self.assertTrue(state.paused)
        for call in get.call_args_list:
            self.assertEqual(
                "server-secret",
                call.kwargs["headers"]["X-Operator-Token"],
            )

    @patch("app.services.legal_control_plane.httpx.get")
    def test_assignments_translate_canonical_job_kinds(self, get):
        get.return_value = self.response(
            [
                {
                    "job_id": "job-1",
                    "matter_id": "MAT-001",
                    "kind": "research",
                    "status": "leased",
                    "created_at": "2026-08-13T12:00:00Z",
                    "updated_at": "2026-08-13T13:00:00Z",
                },
                {
                    "job_id": "job-2",
                    "matter_id": "MAT-001",
                    "kind": "draft",
                    "status": "queued",
                    "created_at": "2026-08-13T12:00:00Z",
                    "updated_at": "2026-08-13T13:00:00Z",
                },
            ]
        )

        assignments = self.control_plane.assignments()

        self.assertEqual(1, len(assignments))
        self.assertEqual("researching", assignments[0].stage)
        self.assertEqual("running", assignments[0].status)

    @patch("app.services.legal_control_plane.httpx.get")
    def test_unexpected_contract_fails_closed(self, get):
        get.side_effect = [
            self.response({"matters": []}),
            self.response({}),
            self.response(
                {
                    "control_plane": "unexpected-service",
                    "command_center_local_legal_state_permitted": False,
                }
            ),
        ]

        with self.assertRaises(LegalControlPlaneError):
            self.control_plane.dashboard()

    @patch("app.services.legal_control_plane.httpx.post")
    def test_pause_is_forwarded_to_the_canonical_control_plane(self, post):
        post.return_value = self.response({"paused": True})

        self.assertTrue(self.control_plane.set_pipeline_paused(True))

        self.assertEqual(
            "https://legal.example.test/api/automation/pause",
            post.call_args.args[0],
        )
        self.assertEqual(
            "server-secret",
            post.call_args.kwargs["headers"]["X-Operator-Token"],
        )


if __name__ == "__main__":
    unittest.main()
