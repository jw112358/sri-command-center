import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app


class FakeStore:
    def __init__(self):
        import threading

        self._lock = threading.RLock()
        self.state = {
            "hudApprovals": {},
            "taskProposals": {},
            "sessionBriefs": {},
        }

    def _load(self, *, fresh=False):
        return copy.deepcopy(self.state)

    def _save(self, state):
        self.state = copy.deepcopy(state)


class HudTests(unittest.TestCase):
    def setUp(self):
        self.original_hud_secret = settings.citadel_hud_signing_secret
        self.original_operator_token = settings.legal_api_token
        self.original_runner_token = settings.orchestrator_runner_token
        self.original_hud_publish_token = settings.citadel_hud_publish_token
        settings.citadel_hud_signing_secret = "h" * 48
        settings.legal_api_token = "operator-test-token"
        settings.orchestrator_runner_token = "worker-test-token"
        settings.citadel_hud_publish_token = "hud-publisher-test-token"
        self.store = FakeStore()
        self.store_patch = patch(
            "app.routers.hud.get_dashboard_store",
            return_value=self.store,
        )
        self.store_patch.start()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.store_patch.stop()
        settings.citadel_hud_signing_secret = self.original_hud_secret
        settings.legal_api_token = self.original_operator_token
        settings.orchestrator_runner_token = self.original_runner_token
        settings.citadel_hud_publish_token = self.original_hud_publish_token

    def pair_device(self):
        response = self.client.post(
            "/api/hud/pairing-codes",
            headers={"Authorization": "Bearer operator-test-token"},
        )
        self.assertEqual(200, response.status_code)
        code = response.json()["code"]
        response = self.client.post("/api/hud/pair", json={"code": code})
        self.assertEqual(200, response.status_code)
        return response.json()["accessToken"], code

    def test_pairing_code_is_single_use(self):
        _, code = self.pair_device()
        response = self.client.post("/api/hud/pair", json={"code": code})
        self.assertEqual(401, response.status_code)

    def test_medium_risk_coding_request_can_be_approved(self):
        token, _ = self.pair_device()
        created = self.client.post(
            "/api/hud/approvals",
            headers={"Authorization": "Bearer worker-test-token"},
            json={
                "source": "claude-code",
                "sessionId": "session-1",
                "title": "Run unit tests",
                "detail": "Run the repository test suite.",
                "action": "pytest",
                "risk": "medium",
            },
        )
        self.assertEqual(201, created.status_code)
        approval_id = created.json()["id"]
        decided = self.client.post(
            f"/api/hud/approvals/{approval_id}/decision",
            headers={"Authorization": f"Bearer {token}"},
            json={"decision": "approve"},
        )
        self.assertEqual(200, decided.status_code)
        self.assertEqual("approved", decided.json()["status"])
        self.assertTrue(decided.json()["decidedBy"].startswith("citadel-hud:"))

    def test_high_risk_request_requires_desktop_confirmation(self):
        token, _ = self.pair_device()
        created = self.client.post(
            "/api/hud/approvals",
            headers={"Authorization": "Bearer worker-test-token"},
            json={
                "source": "codex-api",
                "sessionId": "session-2",
                "title": "Production deployment",
                "detail": "Deploy the current branch to production.",
                "action": "deploy production",
                "risk": "high",
            },
        )
        approval_id = created.json()["id"]
        decided = self.client.post(
            f"/api/hud/approvals/{approval_id}/decision",
            headers={"Authorization": f"Bearer {token}"},
            json={"decision": "approve"},
        )
        self.assertEqual(409, decided.status_code)
        self.assertIn("desktop", decided.json()["detail"].lower())

    def test_summary_exposes_gtd_and_event_edge_read_only_status(self):
        token, _ = self.pair_device()
        brief = SimpleNamespace(model_dump=lambda: {
            "title": "GTD Current Session",
            "project": "GTD v2",
            "status": "complete",
            "summary": "Calibration cycle complete.",
            "nextStart": "Run prospective observation.",
            "updatedAt": "2026-09-10T12:00:00Z",
        })
        dashboard = SimpleNamespace(
            sourceStatus="live",
            sourceDetail="Drive supervisor refreshed 5 seconds ago.",
            paperOnly=True,
            generatedAt="2026-09-10T12:01:00Z",
            automation=SimpleNamespace(mode="paper", heartbeatStatus="healthy"),
            signals=[SimpleNamespace(status="active"), SimpleNamespace(status="blocked")],
            currentPaperTrades=[SimpleNamespace(id="paper-1")],
            metrics=SimpleNamespace(settled=143, winRate=0.56, normalizedNet=4.25),
        )
        with (
            patch("app.routers.hud.list_session_briefs", return_value=[brief]),
            patch("app.routers.hud.get_event_edge_dashboard", return_value=dashboard),
        ):
            response = self.client.get(
                "/api/hud/summary",
                headers={"Authorization": f"Bearer {token}"},
            )
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("GTD Current Session", data["gtd"]["title"])
        self.assertEqual("Run prospective observation.", data["gtd"]["nextStart"])
        self.assertEqual("live", data["eventEdge"]["sourceStatus"])
        self.assertEqual(1, data["eventEdge"]["activeSignals"])
        self.assertEqual(143, data["eventEdge"]["settled"])
        self.assertTrue(data["eventEdge"]["paperOnly"])

    def test_owner_brief_publish_surfaces_exact_top_five_in_gtd(self):
        token, _ = self.pair_device()
        picks = [
            {
                "rank": rank,
                "player": f"Player {rank}",
                "team": "KC",
                "opponent": "LV",
                "category": "qb_passing_yards",
                "line": 275.5,
                "direction": "OVER",
                "projection": 291.2,
                "modelProbability": 0.64,
            }
            for rank in range(1, 6)
        ]
        payload = {
            "schemaVersion": "gtd-nfl-hud-v1",
            "boardId": "board-20260913",
            "gameDate": "2026-09-13",
            "briefingDate": "2026-09-12",
            "publishedAt": "2026-09-12T14:35:00Z",
            "categories": [{
                "key": "qb_passing_yards",
                "label": "QB passing yards",
                "picks": picks,
            }],
            "calibrationStatus": "unvalidated_owner_shadow",
            "visibility": "owner_only",
        }
        response = self.client.post(
            "/api/hud/gtd/nfl-owner-brief",
            headers={"Authorization": "Bearer hud-publisher-test-token"},
            json=payload,
        )
        self.assertEqual(200, response.status_code)
        summary = self.client.get(
            "/api/hud/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(200, summary.status_code)
        snapshot = summary.json()["gtd"]["nflOwnerBrief"]
        self.assertEqual("board-20260913", snapshot["boardId"])
        self.assertEqual(5, len(snapshot["categories"][0]["picks"]))

    def test_owner_brief_publish_rejects_non_top_five_category(self):
        payload = {
            "schemaVersion": "gtd-nfl-hud-v1",
            "boardId": "board-20260913",
            "gameDate": "2026-09-13",
            "briefingDate": "2026-09-12",
            "publishedAt": "2026-09-12T14:35:00Z",
            "categories": [{
                "key": "qb_passing_yards",
                "label": "QB passing yards",
                "picks": [{
                    "rank": 1,
                    "player": "Player 1",
                    "team": "KC",
                    "opponent": "LV",
                    "category": "qb_passing_yards",
                }],
            }],
            "calibrationStatus": "unvalidated_owner_shadow",
        }
        response = self.client.post(
            "/api/hud/gtd/nfl-owner-brief",
            headers={"Authorization": "Bearer hud-publisher-test-token"},
            json=payload,
        )
        self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
