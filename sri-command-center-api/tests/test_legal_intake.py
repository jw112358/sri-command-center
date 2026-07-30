import tempfile
import unittest
from pathlib import Path

from app.models import LegalIntakeRequest
from app.services.legal_intake import LegalIntakeStore


class LegalIntakeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LegalIntakeStore(
            str(Path(self.tmp.name) / "legal.db"),
            max_active=4,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_idempotency_returns_same_matter(self):
        request = LegalIntakeRequest(
            channel="gmail",
            sourceId="gmail-message-1",
            threadId="thread-1",
            subject="Research request",
            body="Please prepare a legal research memo.",
        )
        first = self.store.ingest(request)
        second = self.store.ingest(request)
        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(first.matter.matterId, second.matter.matterId)

    def test_revision_matches_exact_thread_and_increments_version(self):
        original = self.store.ingest(
            LegalIntakeRequest(
                channel="gmail",
                sourceId="gmail-message-1",
                threadId="thread-1",
                subject="New civil matter",
                body="Please open this new matter.",
                requestType="new_matter",
            )
        )
        revision = self.store.ingest(
            LegalIntakeRequest(
                channel="gmail",
                sourceId="gmail-message-2",
                threadId="thread-1",
                subject="Revision requested",
                body="Please revise the prior draft.",
                requestType="revision",
            )
        )
        self.assertTrue(revision.revisionMatched)
        self.assertEqual(original.matter.matterId, revision.matter.matterId)
        self.assertEqual(2, revision.matter.version)
        self.assertEqual("revision_requested", revision.matter.status)

    def test_lease_ceiling_and_one_lease_per_matter(self):
        matters = []
        for index in range(5):
            receipt = self.store.ingest(
                LegalIntakeRequest(
                    sourceId=f"manual-{index}",
                    subject=f"Matter {index}",
                    body="Open a new South Carolina civil matter.",
                    requestType="new_matter",
                )
            )
            matters.append(receipt.matter)

        leases = [
            self.store.acquire_lease(matter.matterId, f"worker-{index}")
            for index, matter in enumerate(matters)
        ]
        self.assertTrue(all(leases[:4]))
        self.assertIsNone(leases[4])
        self.assertIsNone(
            self.store.acquire_lease(matters[0].matterId, "duplicate-worker")
        )

    def test_pause_blocks_new_lease(self):
        receipt = self.store.ingest(
            LegalIntakeRequest(
                sourceId="manual-pause",
                subject="New matter",
                body="Open a new matter.",
                requestType="new_matter",
            )
        )
        self.store.set_paused(True)
        self.assertIsNone(
            self.store.acquire_lease(receipt.matter.matterId, "worker-1")
        )

    def test_drive_persistence_failure_blocks_accepted_matter(self):
        receipt = self.store.ingest(
            LegalIntakeRequest(
                sourceId="manual-drive-failure",
                subject="New matter",
                body="Open a new South Carolina civil matter.",
                requestType="new_matter",
            )
        )
        self.assertTrue(
            self.store.block_intake_persistence_failure(
                matter_id=receipt.matter.matterId,
                event_id=receipt.eventId,
            )
        )
        matter = self.store.list_matters()[0]
        self.assertEqual("blocked", matter.status)
        self.assertIsNone(
            self.store.acquire_lease(matter.matterId, "worker-1")
        )

    def test_assignment_start_creates_live_assignment_and_sanitized_note(self):
        receipt = self.store.ingest(
            LegalIntakeRequest(
                sourceId="manual-assignment-start",
                subject="Privileged client description",
                body="Confidential facts that must not appear in activity feeds.",
                requestType="new_matter",
            )
        )
        lease_id = self.store.acquire_lease(receipt.matter.matterId, "worker-1")
        self.assertIsNotNone(lease_id)

        assignments = self.store.list_assignments()
        self.assertEqual(1, len(assignments))
        self.assertEqual("running", assignments[0].status)
        self.assertEqual("researching", assignments[0].stage)
        self.assertTrue(assignments[0].assignmentId.startswith("ASG-"))

        notes = self.store.list_activity_notes()
        self.assertEqual(1, len(notes))
        self.assertEqual("legal-os", notes[0].tag)
        self.assertIn("Legal assignment started", notes[0].title)
        self.assertNotIn("Privileged client description", notes[0].body)
        self.assertNotIn("Confidential facts", notes[0].body)

    def test_assignment_completion_updates_feed_and_creates_completion_note(self):
        receipt = self.store.ingest(
            LegalIntakeRequest(
                sourceId="manual-assignment-complete",
                subject="Strategy memo",
                body="Prepare a strategy memo.",
                requestType="strategy_memo",
            )
        )
        lease_id = self.store.acquire_lease(receipt.matter.matterId, "worker-1")
        self.assertTrue(self.store.release_lease(lease_id, "pending_approval"))

        assignment = self.store.list_assignments()[0]
        self.assertEqual("completed", assignment.status)
        self.assertEqual("pending_approval", assignment.outcomeStatus)
        self.assertIsNotNone(assignment.completedAt)

        notes = self.store.list_activity_notes()
        self.assertEqual(2, len(notes))
        self.assertIn("Legal assignment completed", notes[0].title)
        self.assertIn("Pending Approval", notes[0].body)


if __name__ == "__main__":
    unittest.main()
