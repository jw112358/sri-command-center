import copy
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app
from app.services.dashboard_state import DashboardStateStore, _empty_state


class MemoryStore(DashboardStateStore):
    def __init__(self):
        super().__init__()
        self.state = _empty_state()

    def _read_drive_state(self):
        return copy.deepcopy(self.state)

    def _save(self, state):
        self.state = copy.deepcopy(state)
        self._cache = copy.deepcopy(state)


class MarketingApiTests(unittest.TestCase):
    def setUp(self):
        self.old_token = settings.legal_api_token
        self.old_routes = settings.marketing_blotato_routes_json
        self.old_api_key = settings.marketing_blotato_api_key
        self.old_publishing = settings.marketing_publishing_enabled
        self.old_runner_token = settings.orchestrator_runner_token
        settings.legal_api_token = "operator-token"
        settings.marketing_blotato_api_key = "synthetic-key"
        settings.marketing_blotato_routes_json = (
            '{"x":{"accountId":"synthetic-x-account","accountLabel":"SRI X",'
            '"platform":"twitter","target":{"targetType":"twitter"}}}'
        )
        settings.marketing_publishing_enabled = False
        settings.orchestrator_runner_token = "synthetic-marketing-runner-token"
        self.store = MemoryStore()
        self.patch = patch("app.routers.marketing.get_dashboard_store", return_value=self.store)
        self.patch.start()
        self.client = TestClient(create_app())
        self.headers = {"Authorization": "Bearer operator-token"}
        self.runner_headers = {
            "Authorization": "Bearer synthetic-marketing-runner-token"
        }

    def tearDown(self):
        self.patch.stop()
        settings.legal_api_token = self.old_token
        settings.marketing_blotato_routes_json = self.old_routes
        settings.marketing_blotato_api_key = self.old_api_key
        settings.marketing_publishing_enabled = self.old_publishing
        settings.orchestrator_runner_token = self.old_runner_token

    def test_dashboard_requires_operator_and_uses_real_destination(self):
        self.assertEqual(401, self.client.get("/api/marketing/dashboard").status_code)
        response = self.client.get("/api/marketing/dashboard", headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual(3, len(response.json()["approvals"]))
        self.assertIn("gtd-v2-frontend.onrender.com", response.json()["destination"])

    def test_approval_is_durable_and_does_not_publish(self):
        approval_id = "gtd-v2-daily-briefing-launch-001-linkedin"
        response = self.client.post(
            f"/api/marketing/approvals/{approval_id}",
            headers=self.headers,
            json={"approved": True},
        )
        self.assertEqual(200, response.status_code)
        item = next(item for item in response.json()["approvals"] if item["id"] == approval_id)
        self.assertEqual("approved", item["status"])
        self.assertEqual("publish", item["requestedAction"])

    def test_controlled_x_asset_runs_through_publish_evidence_and_learning(self):
        class FakeBlotato:
            def __init__(self):
                self.submissions = []

            def list_accounts(self):
                return [{"id": "synthetic-x-account", "name": "SRI X"}]

            def submit(self, payload):
                self.submissions.append(payload)
                return "synthetic-submission-001"

            def status(self, submission_id):
                return {
                    "postSubmissionId": submission_id,
                    "status": "published",
                    "publicUrl": "https://x.com/sri/status/synthetic",
                }

        blotato = FakeBlotato()
        client_patch = patch(
            "app.services.marketing_automation.BlotatoClient", return_value=blotato
        )
        client_patch.start()
        self.addCleanup(client_patch.stop)

        approval_id = "gtd-v2-daily-briefing-launch-001-x"
        approved = self.client.post(
            f"/api/marketing/approvals/{approval_id}",
            headers=self.headers,
            json={"approved": True},
        )
        self.assertEqual(200, approved.status_code)

        verified = self.client.post(
            "/api/marketing/routes/x/verify", headers=self.headers
        )
        self.assertEqual(200, verified.status_code)
        self.assertTrue(verified.json()["verified"])

        scheduled = self.client.post(
            f"/api/marketing/approvals/{approval_id}/schedule",
            headers=self.headers,
            json={"useNextFreeSlot": True},
        )
        self.assertEqual(200, scheduled.status_code)
        publication_id = scheduled.json()["id"]
        self.assertEqual("queued", scheduled.json()["status"])

        settings.marketing_publishing_enabled = True
        submitted = self.client.post("/api/marketing/worker/run", headers=self.headers)
        self.assertEqual(200, submitted.status_code)
        self.assertEqual("submitting", submitted.json()[0]["status"])
        self.assertEqual("twitter", blotato.submissions[0]["post"]["content"]["platform"])
        self.assertNotIn("scheduledTime", blotato.submissions[0])
        self.assertTrue(blotato.submissions[0]["useNextFreeSlot"])

        published = self.client.post("/api/marketing/worker/run", headers=self.headers)
        self.assertEqual(200, published.status_code)
        self.assertEqual("published", published.json()[0]["status"])
        self.assertEqual(
            "https://x.com/sri/status/synthetic", published.json()[0]["publicUrl"]
        )

        dashboard = self.client.get("/api/marketing/dashboard", headers=self.headers).json()
        self.assertEqual(2, len(dashboard["measurements"]))
        self.assertEqual("awaiting-evidence", dashboard["learning"][0]["status"])

        measurement_id = f"{publication_id}:24h"
        early = self.client.post(
            f"/api/marketing/publications/{publication_id}/measurements",
            headers=self.headers,
            json={
                "window": "24h",
                "source": "verified native X analytics",
                "evidenceUrl": "https://x.com/sri/status/synthetic/analytics",
                "impressions": 1000,
            },
        )
        self.assertEqual(409, early.status_code)
        self.assertIn("before its due window", early.text)

        measurement = self.store.list_marketing_measurements()[measurement_id]
        self.store.upsert_marketing_measurement(
            measurement_id,
            {
                **measurement,
                "dueAt": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                "status": "due",
            },
        )

        insecure_evidence = self.client.post(
            f"/api/marketing/publications/{publication_id}/measurements",
            headers=self.headers,
            json={
                "window": "24h",
                "source": "verified native X analytics",
                "evidenceUrl": "http://example.com/evidence",
                "impressions": 1000,
            },
        )
        self.assertEqual(422, insecure_evidence.status_code)

        measured = self.client.post(
            f"/api/marketing/publications/{publication_id}/measurements",
            headers=self.headers,
            json={
                "window": "24h",
                "source": "verified native X analytics",
                "evidenceUrl": "https://x.com/sri/status/synthetic/analytics",
                "impressions": 1000,
                "engagements": 50,
                "clicks": 20,
                "destinationSessions": 12,
            },
        )
        self.assertEqual(200, measured.status_code)
        dashboard = self.client.get("/api/marketing/dashboard", headers=self.headers).json()
        self.assertEqual("provisional", dashboard["learning"][0]["status"])
        self.assertIn("5.00% engagement", dashboard["learning"][0]["summary"])

    def test_publishing_worker_fails_closed_while_disabled(self):
        response = self.client.post("/api/marketing/worker/run", headers=self.headers)
        self.assertEqual(409, response.status_code)
        self.assertIn("publishing is disabled", response.text)

    def test_agent_work_queue_accepts_only_operator_or_orchestrator(self):
        rejected = self.client.get(
            "/api/marketing/agent/work",
            headers={"Authorization": "Bearer wrong-token"},
        )
        self.assertEqual(401, rejected.status_code)
        accepted = self.client.get(
            "/api/marketing/agent/work", headers=self.runner_headers
        )
        self.assertEqual(200, accepted.status_code)
        self.assertEqual([], accepted.json()["analyticsAgent"])

    def test_revoking_approval_cancels_only_a_local_queued_publication(self):
        approval_id = "gtd-v2-daily-briefing-launch-001-x"
        self.store.set_marketing_approval(
            approval_id, approved=True, approved_by="Jeffery Williams"
        )
        from app.services.marketing_automation import _route_fingerprint

        route = settings.marketing_blotato_routes["x"]
        self.store.set_marketing_route(
            "x",
            {
                "verified": True,
                "verifiedAt": datetime.now(timezone.utc).isoformat(),
                "routeFingerprint": _route_fingerprint(route),
                "detail": "Synthetic verified route.",
            },
        )
        queued = self.client.post(
            f"/api/marketing/approvals/{approval_id}/schedule",
            headers=self.headers,
            json={"useNextFreeSlot": True},
        )
        self.assertEqual(200, queued.status_code)
        revoked = self.client.post(
            f"/api/marketing/approvals/{approval_id}",
            headers=self.headers,
            json={"approved": False},
        )
        self.assertEqual(200, revoked.status_code)
        publication = next(iter(self.store.list_marketing_publications().values()))
        self.assertEqual("cancelled", publication["status"])

    def test_stale_route_verification_blocks_scheduling(self):
        approval_id = "gtd-v2-daily-briefing-launch-001-x"
        self.store.set_marketing_approval(
            approval_id, approved=True, approved_by="Jeffery Williams"
        )
        from app.services.marketing_automation import _route_fingerprint

        route = settings.marketing_blotato_routes["x"]
        self.store.set_marketing_route(
            "x",
            {
                "verified": True,
                "verifiedAt": (
                    datetime.now(timezone.utc) - timedelta(hours=25)
                ).isoformat(),
                "routeFingerprint": _route_fingerprint(route),
                "detail": "Stale synthetic route.",
            },
        )
        response = self.client.post(
            f"/api/marketing/approvals/{approval_id}/schedule",
            headers=self.headers,
            json={"useNextFreeSlot": True},
        )
        self.assertEqual(409, response.status_code)
        self.assertIn("must be verified", response.text)


if __name__ == "__main__":
    unittest.main()
