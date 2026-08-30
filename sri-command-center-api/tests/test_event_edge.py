import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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


def paper_payload():
    now = datetime.now(timezone.utc)
    return {
        "generated_at": now.isoformat(),
        "live_trade": False,
        "metrics": {
            "total": 143,
            "pending": 1,
            "wins": 80,
            "losses": 63,
            "win_rate": 80 / 143,
            "net": 4.25,
            "max_drawdown": -3.0,
        },
        "signals": [
            {
                "id": "btc-signal-144",
                "family": "btc_15m",
                "venue": "kalshi",
                "market_ticker": "KXBTC15M-SYNTHETIC",
                "event_ticker": "KXBTC15M",
                "side": "YES",
                "entry_price": 0.61,
                "max_acceptable_price": 0.64,
                "observed_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=4)).isoformat(),
                "status": "active",
                "confidence": "paper-only",
                "primary_signal": "Synthetic boundary fixture.",
                "risk_decision": "approved_for_paper_observation",
            }
        ],
        "pending_trades": [
            {
                "id": "paper-144",
                "sequence": 144,
                "market_ticker": "KXBTC15M-SYNTHETIC",
                "event_ticker": "KXBTC15M",
                "side": "YES",
                "entry": 0.61,
                "status": "pending_settlement",
                "outcome": "pending",
                "net": 0,
                "strategy": "synthetic",
                "simulated_entry_time": now.isoformat(),
                "expected_settlement_time": (now + timedelta(minutes=4)).isoformat(),
            }
        ],
        "settled_trades": [],
        "mlb_kalshi_game": {
            "pending_trades": [],
            "settled_trades": [],
        },
    }


class EventEdgeApiTests(unittest.TestCase):
    def setUp(self):
        self.old_token = settings.legal_api_token
        settings.legal_api_token = "operator-token"
        self.store = MemoryStore()
        self.store_patch = patch(
            "app.routers.event_edge.get_dashboard_store", return_value=self.store
        )
        self.payload_patch = patch(
            "app.services.event_edge.load_event_edge_payload",
            return_value=paper_payload(),
        )
        self.store_patch.start()
        self.payload_patch.start()
        self.client = TestClient(create_app())
        self.headers = {"Authorization": "Bearer operator-token"}

    def tearDown(self):
        self.payload_patch.stop()
        self.store_patch.stop()
        settings.legal_api_token = self.old_token

    def test_dashboard_is_operator_only_and_preserves_paper_boundary(self):
        self.assertEqual(401, self.client.get("/api/event-edge/dashboard").status_code)
        response = self.client.get("/api/event-edge/dashboard", headers=self.headers)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertTrue(data["paperOnly"])
        self.assertFalse(data["liveExecutionEnabled"])
        self.assertEqual(143, data["metrics"]["settled"])
        self.assertEqual("active", data["signals"][0]["status"])
        self.assertEqual("unknown", data["signals"][0]["sourceLane"])
        self.assertEqual("candidate", data["signals"][0]["lifecycleStatus"])
        self.assertEqual(1, len(data["currentPaperTrades"]))
        self.assertFalse(data["automation"]["ordersEnabled"])
        self.assertTrue(data["automation"]["paused"])
        self.assertTrue(data["automation"]["killSwitchEngaged"])
        self.assertEqual("offline", data["automation"]["heartbeatStatus"])
        self.assertEqual([], data["executionRecords"])

    def test_live_contract_fails_closed_when_heartbeat_is_missing(self):
        payload = paper_payload()
        payload["live_trade"] = True
        payload["automation"] = {
            "mode": "live",
            "orders_enabled": True,
            "control_plane_connected": True,
            "paused": False,
            "kill_switch_engaged": False,
        }
        with patch("app.services.event_edge.load_event_edge_payload", return_value=payload):
            response = self.client.get("/api/event-edge/dashboard", headers=self.headers)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertFalse(data["liveExecutionEnabled"])
        self.assertFalse(data["automation"]["ordersEnabled"])
        self.assertEqual("offline", data["automation"]["mode"])

    def test_enriched_execution_contract_preserves_source_fees_and_pnl(self):
        now = datetime.now(timezone.utc)
        payload = paper_payload()
        payload["signals"][0].update({
            "source_lane": "polymarket_copy",
            "source_trader": "wallet-abc",
            "lifecycle_status": "rejected",
            "rejection_reason": "Price moved beyond tolerance",
        })
        payload["execution_records"] = [{
            "id": "execution-1",
            "signal_id": "btc-signal-144",
            "execution_mode": "paper",
            "source_lane": "internal_btc",
            "market_ticker": "KXBTC15M-SYNTHETIC",
            "side": "YES",
            "status": "settled",
            "requested_contracts": 1,
            "filled_contracts": 1,
            "average_fill_price": 0.61,
            "fees": 0.02,
            "realized_pnl": 0.37,
            "updated_at": now.isoformat(),
        }]
        with patch("app.services.event_edge.load_event_edge_payload", return_value=payload):
            response = self.client.get("/api/event-edge/dashboard", headers=self.headers)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("polymarket_copy", data["signals"][0]["sourceLane"])
        self.assertEqual("rejected", data["signals"][0]["lifecycleStatus"])
        self.assertEqual("internal_btc", data["executionRecords"][0]["sourceLane"])
        self.assertEqual(0.02, data["executionRecords"][0]["fees"])
        self.assertEqual(0.37, data["executionRecords"][0]["realizedPnl"])

    def test_live_contract_requires_all_safety_conditions(self):
        now = datetime.now(timezone.utc)
        payload = paper_payload()
        payload["live_trade"] = True
        payload["automation"] = {
            "mode": "live",
            "orders_enabled": True,
            "control_plane_connected": True,
            "paused": False,
            "kill_switch_engaged": False,
            "last_heartbeat_at": now.isoformat(),
            "detail": "Synthetic healthy control-plane fixture.",
        }
        with patch("app.services.event_edge.load_event_edge_payload", return_value=payload):
            response = self.client.get("/api/event-edge/dashboard", headers=self.headers)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertTrue(data["liveExecutionEnabled"])
        self.assertFalse(data["paperOnly"])
        self.assertTrue(data["automation"]["ordersEnabled"])
        self.assertEqual("live", data["automation"]["mode"])
        self.assertEqual("healthy", data["automation"]["heartbeatStatus"])

    def test_paper_mode_cannot_enable_orders_even_with_live_flags(self):
        now = datetime.now(timezone.utc)
        payload = paper_payload()
        payload["live_trade"] = True
        payload["automation"] = {
            "mode": "paper",
            "orders_enabled": True,
            "control_plane_connected": True,
            "paused": False,
            "kill_switch_engaged": False,
            "last_heartbeat_at": now.isoformat(),
        }
        with patch("app.services.event_edge.load_event_edge_payload", return_value=payload):
            response = self.client.get("/api/event-edge/dashboard", headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json()["liveExecutionEnabled"])

    def test_manual_trade_is_a_durable_record_not_an_order(self):
        response = self.client.post(
            "/api/event-edge/manual-trades",
            headers=self.headers,
            json={
                "signalId": "btc-signal-144",
                "family": "btc_15m",
                "venue": "kalshi",
                "marketTicker": "KXBTC15M-SYNTHETIC",
                "side": "YES",
                "entryPrice": 0.62,
                "quantity": 2,
                "notes": "Synthetic manual-entry acceptance record.",
            },
        )
        self.assertEqual(200, response.status_code)
        record = response.json()
        self.assertEqual("manual_external_record", record["executionMode"])
        self.assertEqual("recorded", record["status"])
        self.assertEqual(1, len(self.store.list_event_edge_manual_trades()))

    def test_manual_trade_requires_a_size(self):
        response = self.client.post(
            "/api/event-edge/manual-trades",
            headers=self.headers,
            json={
                "family": "btc_15m",
                "venue": "kalshi",
                "marketTicker": "KXBTC15M-SYNTHETIC",
                "side": "YES",
                "entryPrice": 0.62,
            },
        )
        self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
