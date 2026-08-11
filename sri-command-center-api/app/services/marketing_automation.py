"""Durable, approval-gated Marketing OS publication and evidence workers."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.models import MarketingMeasurementRequest, MarketingScheduleRequest
from app.services.dashboard_state import DashboardStateStore, get_dashboard_store


log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _validated_https_url(value: str, field: str) -> str:
    url = str(value).strip()
    if not url.startswith("https://"):
        raise ValueError(f"{field} must use HTTPS")
    return url


def _media_urls(approval: dict[str, Any]) -> list[str]:
    return [
        _validated_https_url(value, "media URL")
        for value in approval.get("mediaUrls") or []
    ]


def _publication_text(approval: dict[str, Any]) -> str:
    content = str(approval.get("content") or "").strip()
    if not content:
        raise ValueError("approved content is empty")
    destination = _validated_https_url(
        str(approval.get("destination") or ""), "destination"
    )
    return content if destination in content else f"{content}\n\n{destination}"


def _manifest_checksum(approval: dict[str, Any]) -> str:
    manifest = {
        "platform": approval.get("platform"),
        "format": approval.get("format"),
        "content": _publication_text(approval),
        "destination": approval.get("destination"),
        "mediaUrls": _media_urls(approval),
    }
    return _checksum(json.dumps(manifest, sort_keys=True, separators=(",", ":")))


def _route_fingerprint(route: dict[str, Any]) -> str:
    stable = {
        "accountId": route.get("accountId"),
        "platform": route.get("platform"),
        "target": route.get("target"),
    }
    return _checksum(json.dumps(stable, sort_keys=True, separators=(",", ":")))


def _verification_is_fresh(verification: dict[str, Any], route: dict[str, Any]) -> bool:
    verified_at = verification.get("verifiedAt")
    if not verified_at or verification.get("routeFingerprint") != _route_fingerprint(route):
        return False
    try:
        timestamp = datetime.fromisoformat(verified_at)
    except ValueError:
        return False
    return timestamp >= _now() - timedelta(hours=24)


def _parse_schedule(value: str | None) -> str | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("scheduledTime must include a timezone")
    if parsed.astimezone(timezone.utc) <= _now():
        raise ValueError("scheduledTime must be in the future")
    return parsed.astimezone(timezone.utc).isoformat()


class BlotatoClient:
    def __init__(self) -> None:
        if not settings.marketing_blotato_api_key:
            raise RuntimeError("Blotato API key is not configured")
        self.base_url = settings.marketing_blotato_base_url.rstrip("/")
        self.headers = {
            "blotato-api-key": settings.marketing_blotato_api_key,
            "Content-Type": "application/json",
        }

    def list_accounts(self) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.base_url}/users/me/accounts",
            headers=self.headers,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return payload
        return payload.get("items") or payload.get("accounts") or []

    def submit(self, payload: dict[str, Any]) -> str:
        response = httpx.post(
            f"{self.base_url}/posts",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        submission_id = response.json().get("postSubmissionId")
        if not submission_id:
            raise RuntimeError("Blotato did not return postSubmissionId")
        return str(submission_id)

    def status(self, submission_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/posts/{submission_id}",
            headers=self.headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()


class MarketingAutomationService:
    def __init__(
        self,
        store: DashboardStateStore,
        client: BlotatoClient | None = None,
    ) -> None:
        self.store = store
        self._client = client

    @property
    def client(self) -> BlotatoClient:
        if self._client is None:
            self._client = BlotatoClient()
        return self._client

    def routes(self) -> list[dict[str, Any]]:
        configured = settings.marketing_blotato_routes
        saved = self.store.list_marketing_routes()
        platforms = sorted(set(configured) | {"x", "linkedin"})
        result = []
        for platform in platforms:
            route = configured.get(platform, {})
            verification = saved.get(platform, {})
            is_configured = bool(route.get("accountId") and route.get("target"))
            verified = is_configured and _verification_is_fresh(verification, route)
            if verified:
                detail = verification.get("detail") or f"Verified {platform} route."
            elif is_configured:
                label = route.get("accountLabel") or platform.upper()
                detail = (
                    f"Route configuration loaded for {label}; "
                    "exact Blotato account verification is required."
                )
            else:
                detail = (
                    f"No valid {platform} route configuration is loaded. "
                    "Check MARKETING_BLOTATO_ROUTES_JSON."
                )
            result.append(
                {
                    "platform": platform,
                    "provider": "blotato",
                    "configured": is_configured,
                    "verified": verified,
                    "accountLabel": route.get("accountLabel"),
                    "verifiedAt": verification.get("verifiedAt"),
                    "detail": detail,
                }
            )
        return result

    def verify_route(self, platform: str) -> dict[str, Any]:
        route = settings.marketing_blotato_routes.get(platform)
        if not route or not route.get("accountId") or not route.get("target"):
            raise ValueError(f"{platform} Blotato route is not configured")
        accounts = self.client.list_accounts()
        account = next(
            (item for item in accounts if str(item.get("id")) == str(route["accountId"])),
            None,
        )
        if not account:
            raise ValueError(f"configured {platform} account was not returned by Blotato")
        record = {
            "verified": True,
            "verifiedAt": _iso(),
            "routeFingerprint": _route_fingerprint(route),
            "detail": f"Verified {platform} route for {route.get('accountLabel') or 'configured account'}.",
        }
        self.store.set_marketing_route(platform, record)
        return next(item for item in self.routes() if item["platform"] == platform)

    def schedule(
        self,
        *,
        packet_id: str,
        approval: dict[str, Any],
        request: MarketingScheduleRequest,
    ) -> dict[str, Any]:
        if approval.get("status") != "approved":
            raise ValueError("asset must be approved before it can enter the publishing queue")
        platform = str(approval["platform"])
        route = next((item for item in self.routes() if item["platform"] == platform), None)
        if not route or not route["configured"] or not route["verified"]:
            raise ValueError("the exact publishing account route must be verified first")
        scheduling_methods = sum(
            (bool(request.scheduledTime), request.useNextFreeSlot, request.publishNow)
        )
        if scheduling_methods != 1:
            raise ValueError("choose exactly one scheduling method")
        scheduled_time = _parse_schedule(request.scheduledTime)
        if approval.get("requestedAction") != "publish":
            raise ValueError("review-only assets cannot enter the publishing queue")
        publication_text = _publication_text(approval)
        if platform == "x" and len(publication_text) > 280:
            raise ValueError("the final X post exceeds 280 characters")
        media_urls = _media_urls(approval)
        checksum = _manifest_checksum(approval)
        for existing in self.store.list_marketing_publications().values():
            if (
                existing.get("approvalId") == approval["id"]
                and existing.get("contentChecksum") == checksum
                and existing.get("status") not in {"failed", "cancelled"}
            ):
                return existing
        now = _iso()
        record = {
            "id": f"publication:{uuid.uuid4().hex[:16]}",
            "approvalId": approval["id"],
            "packetId": packet_id,
            "platform": platform,
            "ownerAgent": "Publishing Agent",
            "status": "queued",
            "contentChecksum": checksum,
            "destination": approval["destination"],
            "mediaUrls": media_urls,
            "scheduledTime": scheduled_time,
            "useNextFreeSlot": request.useNextFreeSlot,
            "publishNow": request.publishNow,
            "providerSubmissionId": None,
            "publicUrl": None,
            "error": None,
            "attempts": 0,
            "createdAt": now,
            "updatedAt": now,
            "publishedAt": None,
        }
        return self.store.upsert_marketing_publication(record["id"], record)

    def revoke_approval(self, approval_id: str) -> None:
        publications = self.store.list_marketing_publications()
        active_provider_jobs = [
            item
            for item in publications.values()
            if item.get("approvalId") == approval_id
            and item.get("status") in {"submitting", "scheduled"}
        ]
        if active_provider_jobs:
            raise ValueError(
                "the asset is already with Blotato; cancel it there and verify the provider status before revoking approval"
            )
        for publication_id, item in publications.items():
            if item.get("approvalId") == approval_id and item.get("status") == "queued":
                self.store.upsert_marketing_publication(
                    publication_id,
                    {
                        **item,
                        "status": "cancelled",
                        "error": "Operator approval revoked before provider submission.",
                        "updatedAt": _iso(),
                    },
                )

    def run_once(self, approvals: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        if not settings.marketing_publishing_enabled:
            raise RuntimeError("Marketing publishing is disabled")
        changed: list[dict[str, Any]] = []
        publications = self.store.list_marketing_publications()
        for publication_id, record in publications.items():
            try:
                if record["status"] == "queued":
                    updated = self._submit(record, approvals)
                elif record["status"] in {"submitting", "scheduled"}:
                    updated = self._poll(record)
                else:
                    continue
                self.store.upsert_marketing_publication(publication_id, updated)
                changed.append(updated)
                if updated["status"] == "published" and record["status"] != "published":
                    self._create_measurement_windows(updated)
            except Exception as exc:
                failed = {
                    **record,
                    "status": "failed",
                    "error": str(exc)[:2_000],
                    "attempts": int(record.get("attempts", 0)) + 1,
                    "updatedAt": _iso(),
                }
                self.store.upsert_marketing_publication(publication_id, failed)
                changed.append(failed)
        self.refresh_due_measurements()
        return changed

    def _submit(
        self, record: dict[str, Any], approvals: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        approval = approvals.get(record["approvalId"])
        if not approval or approval.get("status") != "approved":
            raise ValueError("publication approval is missing or was revoked")
        if _manifest_checksum(approval) != record["contentChecksum"]:
            raise ValueError("approved publish manifest changed after the publication was queued")
        route = settings.marketing_blotato_routes.get(record["platform"], {})
        verification = self.store.list_marketing_routes().get(record["platform"], {})
        if not _verification_is_fresh(verification, route):
            raise ValueError("publishing route verification is no longer valid")
        platform = route.get("platform") or ("twitter" if record["platform"] == "x" else record["platform"])
        payload: dict[str, Any] = {
            "post": {
                "accountId": route["accountId"],
                "content": {
                    "text": _publication_text(approval),
                    "mediaUrls": _media_urls(approval),
                    "platform": platform,
                },
                "target": route["target"],
            }
        }
        if record.get("scheduledTime"):
            payload["scheduledTime"] = record["scheduledTime"]
        elif record.get("useNextFreeSlot"):
            payload["useNextFreeSlot"] = True
        submission_id = self.client.submit(payload)
        return {
            **record,
            "status": "submitting",
            "providerSubmissionId": submission_id,
            "attempts": int(record.get("attempts", 0)) + 1,
            "updatedAt": _iso(),
            "error": None,
        }

    def _poll(self, record: dict[str, Any]) -> dict[str, Any]:
        provider = self.client.status(record["providerSubmissionId"])
        provider_status = provider.get("status")
        status = {
            "in-progress": "submitting",
            "scheduled": "scheduled",
            "published": "published",
            "failed": "failed",
        }.get(provider_status)
        if not status:
            raise ValueError(f"unsupported Blotato post status: {provider_status}")
        public_url = provider.get("publicUrl") or record.get("publicUrl")
        if status == "published" and not public_url:
            raise ValueError("Blotato reported published without a public URL")
        if status == "published" and not str(public_url).startswith("https://"):
            raise ValueError("Blotato returned a non-HTTPS public URL")
        return {
            **record,
            "status": status,
            "scheduledTime": provider.get("scheduledTime") or record.get("scheduledTime"),
            "publicUrl": public_url,
            "publishedAt": _iso() if status == "published" else record.get("publishedAt"),
            "error": provider.get("errorMessage") if status == "failed" else None,
            "updatedAt": _iso(),
        }

    def _create_measurement_windows(self, publication: dict[str, Any]) -> None:
        published_at = datetime.fromisoformat(publication["publishedAt"])
        for window, hours in (("24h", 24), ("72h", 72)):
            measurement_id = f"{publication['id']}:{window}"
            if measurement_id in self.store.list_marketing_measurements():
                continue
            self.store.upsert_marketing_measurement(
                measurement_id,
                {
                    "id": measurement_id,
                    "publicationId": publication["id"],
                    "window": window,
                    "ownerAgent": "Analytics Agent",
                    "status": "pending",
                    "dueAt": _iso(published_at + timedelta(hours=hours)),
                    "capturedAt": None,
                    "source": None,
                    "evidenceUrl": None,
                    "impressions": None,
                    "reach": None,
                    "engagements": None,
                    "clicks": None,
                    "destinationSessions": None,
                    "notes": None,
                },
            )
        self._update_learning(publication["id"])

    def refresh_due_measurements(self) -> None:
        now = _now()
        for measurement_id, item in self.store.list_marketing_measurements().items():
            if item["status"] == "pending" and datetime.fromisoformat(item["dueAt"]) <= now:
                self.store.upsert_marketing_measurement(
                    measurement_id, {**item, "status": "due"}
                )

    def record_measurement(
        self, publication_id: str, request: MarketingMeasurementRequest
    ) -> dict[str, Any]:
        measurement_id = f"{publication_id}:{request.window}"
        existing = self.store.list_marketing_measurements().get(measurement_id)
        if not existing:
            raise LookupError("measurement window not found")
        if datetime.fromisoformat(existing["dueAt"]) > _now():
            raise ValueError("measurement evidence cannot be recorded before its due window")
        if request.window == "72h":
            first = self.store.list_marketing_measurements().get(
                f"{publication_id}:24h"
            )
            if not first or first.get("status") != "complete":
                raise ValueError("complete the 24h evidence window before the 72h window")
        record = {
            **existing,
            **request.model_dump(),
            "status": "complete",
            "capturedAt": _iso(),
        }
        self.store.upsert_marketing_measurement(measurement_id, record)
        self._update_learning(publication_id)
        return record

    def _update_learning(self, publication_id: str) -> None:
        measurements = [
            item
            for item in self.store.list_marketing_measurements().values()
            if item["publicationId"] == publication_id
        ]
        completed = [item for item in measurements if item["status"] == "complete"]
        if not completed:
            status = "awaiting-evidence"
            summary = "Publication confirmed; awaiting verified 24-hour performance evidence."
            recommendation = "Collect the first measurement before changing creative or channel strategy."
        else:
            latest = sorted(completed, key=lambda item: item["window"])[-1]
            status = "complete" if any(item["window"] == "72h" for item in completed) else "provisional"
            impressions = latest.get("impressions") or 0
            engagements = latest.get("engagements") or 0
            clicks = latest.get("clicks") or 0
            rate = (engagements / impressions * 100) if impressions else 0
            summary = (
                f"{latest['window']} evidence: {impressions} impressions, {engagements} engagements "
                f"({rate:.2f}% engagement), {clicks} clicks, and "
                f"{latest.get('destinationSessions') or 0} destination sessions."
            )
            recommendation = (
                "Retain the message as a baseline and compare the next single-variable variant."
                if impressions
                else "Verify platform evidence collection before drawing a performance conclusion."
            )
        self.store.upsert_marketing_learning(
            publication_id,
            {
                "publicationId": publication_id,
                "ownerAgent": "Learning Agent",
                "status": status,
                "summary": summary,
                "recommendation": recommendation,
                "updatedAt": _iso(),
            },
        )


async def marketing_worker_loop() -> None:
    while True:
        try:
            from app.services.marketing import approval_map

            store = get_dashboard_store()
            MarketingAutomationService(store).run_once(approval_map(store))
        except Exception:
            log.exception("Marketing OS worker cycle failed")
        await asyncio.sleep(max(15, settings.marketing_worker_interval_seconds))
