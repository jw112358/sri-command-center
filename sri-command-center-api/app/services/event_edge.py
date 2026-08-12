"""Read-only Event Edge paper intelligence for the operator dashboard.

The existing Event Edge supervisor writes one self-contained HTML dashboard to
Google Drive.  Its embedded JSON is the integration contract, which keeps the
Command Center from duplicating or mutating the paper-trading ledger.  Manual
entries are durable operator records only; this module never submits orders.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models import (
    EventEdgeDashboard,
    EventEdgeMetrics,
    EventEdgePaperTrade,
    EventEdgeSignal,
)
from app.services import drive
from app.services.dashboard_state import DashboardStateStore


class EventEdgeUnavailable(RuntimeError):
    """Raised when the governed paper dashboard cannot be read."""


_cache: dict[str, Any] | None = None
_cache_at = 0.0
_DASHBOARD_JSON = re.compile(
    r'<script\s+type="application/json"\s+id="event-edge-dashboard-data">(.*?)</script>',
    re.DOTALL,
)


def _parse_timestamp(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_event_edge_payload(*, fresh: bool = False) -> dict[str, Any]:
    global _cache, _cache_at
    if not fresh and _cache is not None and time.monotonic() - _cache_at < 15:
        return json.loads(json.dumps(_cache))
    if not settings.event_edge_dashboard_file_id:
        raise EventEdgeUnavailable("Event Edge dashboard file is not configured")
    service = drive.get_drive_service()
    if not service:
        raise EventEdgeUnavailable("Google Drive is unavailable")
    try:
        content = service.files().get_media(
            fileId=settings.event_edge_dashboard_file_id
        ).execute()
        if isinstance(content, bytes):
            content = content.decode("utf-8")
    except Exception as exc:
        raise EventEdgeUnavailable("Event Edge dashboard could not be read") from exc
    match = _DASHBOARD_JSON.search(str(content))
    if not match:
        raise EventEdgeUnavailable("Event Edge dashboard data contract is missing")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise EventEdgeUnavailable("Event Edge dashboard data is invalid") from exc
    if not isinstance(payload, dict):
        raise EventEdgeUnavailable("Event Edge dashboard data is not an object")
    _cache = payload
    _cache_at = time.monotonic()
    return json.loads(json.dumps(payload))


def _signal(item: dict[str, Any]) -> EventEdgeSignal:
    max_price = item.get("max_acceptable_price")
    return EventEdgeSignal(
        id=str(item.get("id") or "unknown-signal"),
        family=str(item.get("family") or "unknown"),
        venue=str(item.get("venue") or "kalshi"),
        marketTicker=str(item.get("market_ticker") or ""),
        eventTicker=str(item.get("event_ticker") or ""),
        side=str(item.get("side") or ""),
        entryPrice=float(item.get("entry_price") or 0),
        maxAcceptablePrice=(float(max_price) if max_price not in (None, "", 0) else None),
        observedAt=str(item.get("observed_at") or ""),
        expiresAt=str(item.get("expires_at") or ""),
        status=str(item.get("status") or "blocked"),
        confidence=str(item.get("confidence") or ""),
        primarySignal=str(item.get("primary_signal") or ""),
        supportingSignals=str(item.get("supporting_signals") or ""),
        contrarySignals=str(item.get("contrary_signals") or ""),
        riskDecision=str(item.get("risk_decision") or ""),
        strategy=str(item.get("strategy") or ""),
    )


def _trade(item: dict[str, Any], family: str) -> EventEdgePaperTrade:
    cash_pnl = item.get("cash_pnl")
    return EventEdgePaperTrade(
        id=str(item.get("id") or item.get("path_rel") or "unknown-trade"),
        family=family,
        sequence=int(item.get("sequence") or 0),
        marketTicker=str(item.get("market_ticker") or ""),
        eventTicker=str(item.get("event_ticker") or ""),
        eventTitle=str(item.get("event_title") or ""),
        team=str(item.get("team") or ""),
        side=str(item.get("side") or ""),
        entryPrice=float(item.get("entry") or 0),
        status=str(item.get("status") or ""),
        outcome=str(item.get("outcome") or "pending"),
        netResult=float(item.get("net") or 0),
        cashPnl=(float(cash_pnl) if cash_pnl is not None else None),
        strategy=str(item.get("strategy") or ""),
        enteredAt=str(item.get("simulated_entry_time") or ""),
        expiresAt=str(item.get("expected_settlement_time") or ""),
    )


def get_dashboard(store: DashboardStateStore) -> EventEdgeDashboard:
    payload = load_event_edge_payload()
    generated_at = str(payload.get("generated_at") or "")
    generated = _parse_timestamp(generated_at)
    if generated is None:
        source_status = "partial"
        source_detail = "Paper data loaded without a valid generated timestamp."
    else:
        age = max(0, int((datetime.now(timezone.utc) - generated).total_seconds()))
        if age <= settings.event_edge_dashboard_stale_seconds:
            source_status = "live"
            source_detail = f"Drive paper supervisor refreshed {age} seconds ago."
        else:
            source_status = "stale"
            source_detail = f"Last Drive paper-supervisor refresh was {age} seconds ago."

    btc_pending = [_trade(item, "btc_15m") for item in payload.get("pending_trades", [])]
    btc_settled = [_trade(item, "btc_15m") for item in payload.get("settled_trades", [])]
    mlb = payload.get("mlb_kalshi_game") or {}
    mlb_pending = [
        _trade(item, "mlb_kalshi_game") for item in mlb.get("pending_trades", [])
    ]
    mlb_settled = [
        _trade(item, "mlb_kalshi_game") for item in mlb.get("settled_trades", [])
    ]
    recent = sorted(
        btc_settled + mlb_settled,
        key=lambda item: (item.enteredAt, item.sequence),
        reverse=True,
    )[: settings.event_edge_recent_trade_limit]
    signals = [_signal(item) for item in payload.get("signals", [])]
    signals.sort(
        key=lambda item: (item.status == "active", item.observedAt), reverse=True
    )
    metrics = payload.get("metrics") or {}
    families = sorted(
        {
            "btc_15m",
            "mlb_kalshi_game",
            *(item.family for item in signals),
            *(item.family for item in store.list_event_edge_manual_trades()),
        }
    )
    return EventEdgeDashboard(
        generatedAt=generated_at,
        sourceStatus=source_status,
        sourceDetail=source_detail,
        paperOnly=True,
        liveExecutionEnabled=False,
        metrics=EventEdgeMetrics(
            settled=int(metrics.get("total") or 0),
            pending=int(metrics.get("pending") or 0),
            wins=int(metrics.get("wins") or 0),
            losses=int(metrics.get("losses") or 0),
            winRate=float(metrics.get("win_rate") or 0),
            normalizedNet=float(metrics.get("net") or 0),
            maxDrawdown=float(metrics.get("max_drawdown") or 0),
        ),
        signals=signals,
        currentPaperTrades=btc_pending + mlb_pending,
        recentPaperTrades=recent,
        manualTrades=store.list_event_edge_manual_trades(),
        marketFamilies=families,
    )
