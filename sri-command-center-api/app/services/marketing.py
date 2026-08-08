"""Bounded GTD-v2 controlled-launch state for the Marketing OS console."""
from __future__ import annotations

from app.models import MarketingApproval, MarketingConnector, MarketingDashboard
from app.services.dashboard_state import DashboardStateStore


DESTINATION = "https://gtd-v2-frontend.onrender.com/#/pricing"

APPROVALS = [
    {
        "id": "gtd-v2-daily-briefing-launch-001-email",
        "platform": "email",
        "format": "launch-list email",
        "content": (
            "A faster way to review the MLB slate. GTD-v2 organizes six player-prop research "
            "categories into a concise daily briefing, with current lines, matchup context, and "
            "transparent coverage disclosures. Explore the MLB Daily Briefing preview. "
            "For informational and entertainment purposes only. 21+. No guaranteed outcomes."
        ),
    },
    {
        "id": "gtd-v2-daily-briefing-launch-001-linkedin",
        "platform": "linkedin",
        "format": "organic text post",
        "content": (
            "Daily MLB prop research is often fragmented across too many screens. GTD-v2 brings "
            "six research categories into one repeatable briefing with current lines, matchup "
            "context, and transparent data-quality disclosures. It is an analysis aid—not a "
            "promise of outcomes or a list of prescribed selections. Explore the Daily Briefing preview."
        ),
    },
    {
        "id": "gtd-v2-daily-briefing-launch-001-x",
        "platform": "x",
        "format": "organic short post",
        "content": (
            "Six MLB prop-research categories. One concise daily briefing. Current lines, matchup "
            "context, and transparent coverage—without guaranteed outcomes or prescribed picks. "
            "Explore GTD-v2. 21+ | Informational/entertainment use only."
        ),
    },
]

CONNECTORS = [
    MarketingConnector(name="GTD launch destination", status="READY", detail="Public pricing and Daily Briefing preview are live."),
    MarketingConnector(name="Approval capture", status="READY", detail="Approvals persist in the Command Center Drive state."),
    MarketingConnector(name="Controlled-launch analytics", status="READY", detail="Verified native platform figures and destination sessions are the MVP source."),
    MarketingConnector(name="Blotato publishing", status="STAGED", detail="Previously connected; each live account route requires fresh verification before scheduling."),
    MarketingConnector(name="Paid advertising", status="BLOCKED", detail="No spend is authorized or configured for the controlled launch."),
]


def get_dashboard(store: DashboardStateStore) -> MarketingDashboard:
    saved = store.list_marketing_approvals()
    approvals = []
    for item in APPROVALS:
        state = saved.get(item["id"], {})
        approvals.append(MarketingApproval(
            **item,
            destination=DESTINATION,
            status=state.get("status", "awaiting-approval"),
            approvedAt=state.get("approvedAt"),
            approvedBy=state.get("approvedBy"),
        ))
    approved = sum(item.status == "approved" for item in approvals)
    return MarketingDashboard(
        packetId="gtd-v2-daily-briefing-launch-001",
        product="GTD-v2 Daily Briefing",
        launchStage="controlled organic preview",
        objective="Introduce the briefing, validate qualified interest, and establish a measurable path to paid access.",
        destination=DESTINATION,
        productionReadiness=78,
        minimumOperationalCapability=90,
        measurementSource="Verified native platform metrics plus GTD destination sessions",
        currentGate=(
            "Fresh publishing-route verification and operator approval of each asset"
            if approved < len(approvals)
            else "Fresh publishing-route verification; all launch assets are operator approved"
        ),
        connectors=CONNECTORS,
        approvals=approvals,
    )


def approval_ids() -> set[str]:
    return {item["id"] for item in APPROVALS}
