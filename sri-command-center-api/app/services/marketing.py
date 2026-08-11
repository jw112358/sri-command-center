"""Bounded GTD-v2 controlled-launch state for the Marketing OS console."""
from __future__ import annotations

from app.models import MarketingApproval, MarketingConnector, MarketingDashboard
from app.config import settings
from app.services.dashboard_state import DashboardStateStore
from app.services.marketing_automation import MarketingAutomationService


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
    automation = MarketingAutomationService(store)
    routes = automation.routes()
    configured_route = any(item["configured"] for item in routes)
    verified_route = any(item["verified"] for item in routes)
    publishing_live = bool(
        settings.marketing_worker_enabled
        and settings.marketing_publishing_enabled
        and verified_route
    )
    publications = list(store.list_marketing_publications().values())
    publications.sort(key=lambda item: item["updatedAt"], reverse=True)
    measurements = list(store.list_marketing_measurements().values())
    measurements.sort(key=lambda item: item["dueAt"])
    learning = list(store.list_marketing_learning().values())
    learning.sort(key=lambda item: item["updatedAt"], reverse=True)
    connectors = [
        item
        for item in CONNECTORS
        if item.name != "Blotato publishing"
    ]
    connectors.insert(
        3,
        MarketingConnector(
            name="Blotato publishing",
            status="READY" if publishing_live else "STAGED",
            detail=(
                "Verified account route and autonomous publishing worker are active."
                if publishing_live
                else "API adapter is installed; configure and verify one exact account route before enabling the worker."
            ),
        ),
    )
    readiness = 92 if publishing_live else 88 if verified_route else 86
    if any(item.get("status") == "published" for item in publications):
        readiness = max(readiness, 93)
    if approved < len(approvals):
        current_gate = "Operator approval of each controlled-launch asset"
    elif not configured_route:
        current_gate = "Configure one exact Blotato account route in the production secret store"
    elif not verified_route:
        current_gate = "Fresh verification of the configured Blotato account route"
    elif not publishing_live:
        current_gate = "Enable the controlled organic publishing worker after final route review"
    else:
        current_gate = "Controlled organic pipeline active; collect verified 24-hour and 72-hour evidence"
    return MarketingDashboard(
        packetId="gtd-v2-daily-briefing-launch-001",
        product="GTD-v2 Daily Briefing",
        launchStage="controlled organic preview",
        objective="Introduce the briefing, validate qualified interest, and establish a measurable path to paid access.",
        destination=DESTINATION,
        productionReadiness=readiness,
        minimumOperationalCapability=92 if publishing_live else 88,
        measurementSource="Verified native platform metrics plus GTD destination sessions",
        currentGate=current_gate,
        connectors=connectors,
        approvals=approvals,
        routes=routes,
        publications=publications,
        measurements=measurements,
        learning=learning,
    )


def approval_ids() -> set[str]:
    return {item["id"] for item in APPROVALS}


def approval_map(store: DashboardStateStore) -> dict[str, dict]:
    return {
        item.id: item.model_dump()
        for item in get_dashboard(store).approvals
    }
