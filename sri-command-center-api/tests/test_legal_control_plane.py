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
            "exact_next_action": "Complete targeted clarification.",
            "intake_completeness_score": 72,
            "blocking_gaps": ["Requested relief"],
            "future_deadlines": ["2099-01-01"],
            "created_at": "2026-08-13T12:00:00Z",
            "updated_at": "2026-08-13T13:00:00Z",
        }

    @staticmethod
    def review_packet():
        return {
            "packet_id": "packet-001",
            "matter_id": "MAT-001",
            "matter_version": 3,
            "status": "awaiting_review",
            "summary": "Synthetic packet ready for operator review.",
            "artifacts": [
                {
                    "title": "Synthetic draft",
                    "kind": "draft_work_product",
                    "drive_file_id": "drive-file-001",
                    "sha256": "a" * 64,
                }
            ],
            "authorities": ["Rule 56(c), SCRCP"],
            "citation_findings": ["Synthetic citation finding"],
            "risk_flags": ["Synthetic test only"],
            "proposed_external_action": "Draft a delivery message for separate approval.",
            "created_at": "2026-08-17T16:00:00Z",
            "reviewed_at": None,
            "reviewed_by": None,
            "decision_note": None,
        }

    @staticmethod
    def document():
        return {
            "document_id": "doc-001",
            "matter_id": "MAT-001",
            "version": 3,
            "name": "synthetic-motion.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size_bytes": 4096,
            "sha256": "b" * 64,
            "drive_file_id": "drive-source-001",
            "category": "motion_or_brief",
            "record_status": "filed",
            "confidentiality": "privileged",
            "ingestion_status": "ready_for_review",
            "extraction_method": "docx_xml",
            "extracted_character_count": 1200,
            "page_count": None,
            "warnings": [],
            "review_note": "",
            "accepted_at": None,
            "created_at": "2026-08-17T16:00:00Z",
            "updated_at": "2026-08-17T16:01:00Z",
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
                    "ai_worker_enabled": False,
                    "ai_confidential_processing_authorized": True,
                    "ai_model": "gpt-5.6-sol",
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
        self.assertEqual(["Requested relief"], state.matters[0].blockingGaps)
        self.assertEqual(72, state.matters[0].intakeCompletenessScore)
        self.assertEqual("STAGED", state.connectors[-1].status)
        self.assertEqual("AI DRAFT + QA", state.connectors[-1].name)
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
    def test_review_packets_expose_private_drive_references_and_findings(self, get):
        get.return_value = self.response([self.review_packet()])

        packets = self.control_plane.review_packets()

        self.assertEqual(1, len(packets))
        self.assertEqual("packet-001", packets[0].packetId)
        self.assertEqual("drive-file-001", packets[0].artifacts[0].driveFileId)
        self.assertEqual(["Rule 56(c), SCRCP"], packets[0].authorities)
        self.assertEqual(
            "https://legal.example.test/api/review-packets",
            get.call_args.args[0],
        )

    @patch("app.services.legal_control_plane.httpx.get")
    def test_document_list_and_preview_preserve_drive_provenance(self, get):
        get.side_effect = [
            self.response([self.document()]),
            self.response(
                {
                    "document": self.document(),
                    "text_excerpt": "Synthetic extracted record.",
                    "provenance_notice": "Unverified until accepted.",
                }
            ),
        ]
        documents = self.control_plane.matter_documents("MAT-001")
        preview = self.control_plane.document_preview("MAT-001", "doc-001")
        self.assertEqual("drive-source-001", documents[0].driveFileId)
        self.assertEqual("Synthetic extracted record.", preview.textExcerpt)

    @patch("app.services.legal_control_plane.httpx.post")
    def test_document_upload_forwards_private_file_and_metadata(self, post):
        post.return_value = self.response(self.document(), status_code=201)
        document = self.control_plane.upload_matter_document(
            "MAT-001",
            filename="synthetic-motion.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=b"synthetic-docx",
            category="motion_or_brief",
            record_status="filed",
            confidentiality="privileged",
        )
        self.assertEqual("doc-001", document.documentId)
        self.assertEqual(b"synthetic-docx", post.call_args.kwargs["files"]["file"][1])
        self.assertEqual("motion_or_brief", post.call_args.kwargs["data"]["category"])

    @patch("app.services.legal_control_plane.httpx.post")
    def test_review_decision_is_forwarded_without_authorizing_delivery(self, post):
        packet = self.review_packet()
        packet.update(
            {
                "status": "approved",
                "reviewed_at": "2026-08-17T16:05:00Z",
                "reviewed_by": "jeffery-williams",
                "decision_note": "Synthetic approval; delivery remains separate.",
            }
        )
        post.return_value = self.response(packet)

        updated = self.control_plane.decide_review_packet(
            "packet-001",
            "approve",
            "Synthetic approval; delivery remains separate.",
        )

        self.assertEqual("approved", updated.status)
        self.assertEqual(
            "https://legal.example.test/api/review-packets/packet-001/decision",
            post.call_args.args[0],
        )
        self.assertEqual(
            {
                "decision": "approve",
                "note": "Synthetic approval; delivery remains separate.",
            },
            post.call_args.kwargs["json"],
        )

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

    @patch("app.services.legal_control_plane.httpx.post")
    def test_structured_intake_is_forwarded_without_local_matter_state(self, post):
        post.return_value = self.response(self.matter(), status_code=201)
        payload = {
            "schema_version": "1.1",
            "channel": "manual",
            "source_id": "synthetic-intake-001",
            "request_type": "strategy_memo",
        }

        receipt = self.control_plane.manual_intake(payload)

        self.assertEqual("MAT-001", receipt.matter.matterId)
        self.assertEqual("synthetic-intake-001", receipt.eventId)
        self.assertEqual(
            "https://legal.example.test/api/intakes/manual",
            post.call_args.args[0],
        )
        self.assertEqual(payload, post.call_args.kwargs["json"])
        self.assertEqual(
            "server-secret",
            post.call_args.kwargs["headers"]["X-Operator-Token"],
        )

    def test_structured_intake_rejects_noncanonical_schema(self):
        with self.assertRaises(LegalControlPlaneError) as raised:
            self.control_plane.manual_intake(
                {"schema_version": "1.0", "channel": "manual"}
            )
        self.assertEqual(422, raised.exception.status_code)

    @patch("app.services.legal_control_plane.httpx.post")
    def test_operator_clarifications_are_forwarded_to_canonical_matter(self, post):
        matter = self.matter()
        matter.update({"status": "received", "blocking_gaps": []})
        post.return_value = self.response(matter)

        updated = self.control_plane.resolve_clarifications(
            "MAT-001",
            3,
            {"Requested relief": "Synthetic declaratory relief."},
            "Synthetic acceptance only.",
        )

        self.assertEqual("received", updated.status)
        self.assertEqual([], updated.blockingGaps)
        self.assertEqual(
            "https://legal.example.test/api/matters/MAT-001/clarifications",
            post.call_args.args[0],
        )
        self.assertEqual(
            {
                "expected_version": 3,
                "answers": {"Requested relief": "Synthetic declaratory relief."},
                "operator_note": "Synthetic acceptance only.",
            },
            post.call_args.kwargs["json"],
        )


if __name__ == "__main__":
    unittest.main()
