import unittest

from app.services.session_briefs import parse_session_summary


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


if __name__ == "__main__":
    unittest.main()
