import unittest
from unittest.mock import patch

from app.config import settings
from app.models import CreateSessionSummaryRequest
from app.services.session_briefs import create_session_summary, parse_session_summary


class FakeCreateRequest:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeFiles:
    def __init__(self):
        self.created = None

    def create(self, **kwargs):
        self.created = kwargs
        return FakeCreateRequest({
            "id": "new-summary",
            "name": kwargs["body"]["name"],
            "createdTime": "2026-07-30T12:00:00Z",
            "modifiedTime": "2026-07-30T12:00:00Z",
            "webViewLink": "https://drive.google.com/file/d/new-summary/view",
        })


class FakeDriveService:
    def __init__(self):
        self._files = FakeFiles()

    def files(self):
        return self._files


class SessionBriefParserTests(unittest.TestCase):
    def test_result_and_resume_instruction_become_concise_brief(self):
        raw = """---
session_id: platform-session-999
date: 2026-07-24
owner_os: SRI Agent Platform
status: complete
project: Master Builder
---
# Platform Session 999 - Continuity Test

## Result

Completed the durable session continuity index without duplicating the source record.

## Current State

The source summary remains canonical and the dashboard is read-only.

## Resume Instruction

Begin by validating the live dashboard, then continue the next unfinished build gate.
"""
        brief = parse_session_summary(
            {
                "id": "drive-file",
                "name": "platform-session-999.md",
                "modifiedTime": "2026-07-24T12:00:00Z",
            },
            raw,
        )
        self.assertEqual("platform-session-999", brief.sessionId)
        self.assertEqual("Master Builder", brief.project)
        self.assertIn("Completed the durable", brief.summary)
        self.assertIn("Begin by validating", brief.nextStart)
        self.assertTrue(brief.sourceUrl.endswith("/drive-file/view"))

    def test_follow_up_is_used_as_next_start(self):
        raw = """# Platform Session - Test

## Completed
Captured the current evidence.

## Follow-up
Confirm the result and update the canonical record.
"""
        brief = parse_session_summary(
            {
                "id": "follow-up",
                "name": "platform-session.md",
                "modifiedTime": "2026-07-24T12:00:00Z",
            },
            raw,
        )
        self.assertIn("Confirm the result", brief.nextStart)

    def test_material_summary_is_written_and_linked_to_task(self):
        original_enabled = settings.dashboard_drive_write_enabled
        original_folder = settings.dashboard_session_summaries_folder_id
        settings.dashboard_drive_write_enabled = True
        settings.dashboard_session_summaries_folder_id = "summary-folder"
        service = FakeDriveService()
        try:
            with patch("app.services.session_briefs.drive.get_drive_service", return_value=service):
                brief = create_session_summary(CreateSessionSummaryRequest(
                    project="Master Builder",
                    surface="Codex",
                    title="Command Center review ready",
                    summary="Implemented and tested the orchestrator queue.",
                    currentState="The change is ready for Jeff's review.",
                    nextStart="Open the review packet and decide whether to Approve & Ship.",
                    materialChange=True,
                    taskId="task:123",
                    status="review-ready",
                    evidenceUrls=["https://example.test/checks"],
                ))
        finally:
            settings.dashboard_drive_write_enabled = original_enabled
            settings.dashboard_session_summaries_folder_id = original_folder
        self.assertEqual("task:123", brief.taskId)
        self.assertEqual("review-ready", brief.status)
        self.assertEqual("summary-folder", service._files.created["body"]["parents"][0])

    def test_non_material_summary_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "materially change"):
            create_session_summary(CreateSessionSummaryRequest(
                project="Master Builder",
                surface="Codex",
                title="Read-only session",
                summary="No change.",
                currentState="Unchanged.",
                nextStart="Continue later.",
                materialChange=False,
            ))


if __name__ == "__main__":
    unittest.main()
