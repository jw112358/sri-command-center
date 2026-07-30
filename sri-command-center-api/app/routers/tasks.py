"""Durable operator task queue and orchestrator lifecycle endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Response

from app.models import (
    CreateSessionSummaryRequest,
    CreateTaskRequest,
    PatchTaskRequest,
    Task,
    TaskBlockedRequest,
    TaskClaimRequest,
    TaskCompleteRequest,
    TaskReviewReadyRequest,
)
from app.routers.legal import require_operator
from app.services.dashboard_state import (
    DashboardStateUnavailable,
    get_dashboard_store,
)
from app.services.orchestrator_auth import require_orchestrator_worker
from app.services.session_briefs import create_session_summary

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get(
    "",
    response_model=list[Task],
    dependencies=[Depends(require_operator)],
)
def list_tasks():
    try:
        return get_dashboard_store().list_tasks()
    except DashboardStateUnavailable:
        return []


@router.post(
    "",
    response_model=Task,
    status_code=201,
    dependencies=[Depends(require_operator)],
)
def create_task(body: CreateTaskRequest):
    try:
        return get_dashboard_store().create_task(
            body.text,
            project=body.project,
            preferred_surface=body.preferredSurface,
        )
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.patch(
    "/{task_id}",
    response_model=Task,
    dependencies=[Depends(require_operator)],
)
def patch_task(task_id: str, body: PatchTaskRequest):
    patch = {key: value for key, value in body.model_dump().items() if value is not None}
    try:
        existing = get_dashboard_store().get_task(task_id)
        if existing and existing.status not in ("queued", "blocked"):
            raise HTTPException(
                409,
                "Only queued or blocked tasks can be edited",
            )
        task = get_dashboard_store().patch_task(task_id, patch)
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return task


@router.post(
    "/claim",
    response_model=list[Task],
    dependencies=[Depends(require_orchestrator_worker)],
)
def claim_tasks(body: TaskClaimRequest):
    try:
        return get_dashboard_store().claim_tasks(body.workerId, body.limit)
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post(
    "/{task_id}/review-ready",
    response_model=Task,
    dependencies=[Depends(require_orchestrator_worker)],
)
def mark_review_ready(task_id: str, body: TaskReviewReadyRequest):
    store = get_dashboard_store()
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    try:
        brief = create_session_summary(CreateSessionSummaryRequest(
            project=task.project,
            surface=body.surface,
            title=body.title,
            summary=body.summary,
            currentState=body.currentState,
            nextStart=body.nextStart,
            materialChange=True,
            taskId=task.id,
            status="review-ready",
            evidenceUrls=body.evidenceUrls,
        ))
        updated = store.mark_task_review_ready(
            task_id,
            worker_id=body.workerId,
            summary_id=brief.id,
            review_url=body.reviewUrl,
            evidence_urls=body.evidenceUrls,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RuntimeError, DashboardStateUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            503,
            "Review-ready work was not accepted because its session summary could not be filed",
        ) from exc
    return updated


@router.post(
    "/{task_id}/approve-ship",
    response_model=Task,
    dependencies=[Depends(require_operator)],
)
def approve_ship(task_id: str):
    try:
        task = get_dashboard_store().approve_task_for_shipping(task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return task


@router.post(
    "/{task_id}/complete",
    response_model=Task,
    dependencies=[Depends(require_orchestrator_worker)],
)
def complete_task(task_id: str, body: TaskCompleteRequest):
    store = get_dashboard_store()
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    try:
        brief = create_session_summary(CreateSessionSummaryRequest(
            project=task.project,
            surface=body.workerId,
            title=f"{task.project} — task shipped",
            summary=body.finalSummary or "The approved task was shipped and verified.",
            currentState="The approved action completed and its verification evidence is linked below.",
            nextStart="Review the verified result; open a new task only if a follow-up change is required.",
            materialChange=True,
            taskId=task.id,
            status="complete",
            evidenceUrls=body.evidenceUrls,
        ))
        updated = store.complete_task(
            task_id,
            worker_id=body.workerId,
            summary_id=brief.id,
            evidence_urls=body.evidenceUrls,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RuntimeError, DashboardStateUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            503,
            "The task remains open because its completion summary could not be filed",
        ) from exc
    return updated


@router.post(
    "/{task_id}/blocked",
    response_model=Task,
    dependencies=[Depends(require_orchestrator_worker)],
)
def block_task(task_id: str, body: TaskBlockedRequest):
    store = get_dashboard_store()
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    try:
        brief = create_session_summary(CreateSessionSummaryRequest(
            project=task.project,
            surface=body.workerId,
            title=f"{task.project} — task blocked",
            summary=body.reason,
            currentState="The task is blocked; no external action was taken.",
            nextStart="Resolve the recorded blocker, then requeue this task from the Command Center.",
            materialChange=True,
            taskId=task.id,
            status="blocked",
            evidenceUrls=body.evidenceUrls,
        ))
        updated = store.block_task(
            task_id,
            worker_id=body.workerId,
            reason=body.reason,
            summary_id=brief.id,
            evidence_urls=body.evidenceUrls,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RuntimeError, DashboardStateUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            503,
            "The task could not be blocked because its session summary was not filed",
        ) from exc
    return updated


@router.post(
    "/{task_id}/requeue",
    response_model=Task,
    dependencies=[Depends(require_operator)],
)
def requeue_task(task_id: str):
    try:
        task = get_dashboard_store().requeue_task(task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return task


@router.delete(
    "/{task_id}",
    status_code=204,
    dependencies=[Depends(require_operator)],
)
def delete_task(task_id: str):
    try:
        task = get_dashboard_store().get_task(task_id)
        if task and task.status not in ("queued", "blocked", "completed"):
            raise HTTPException(
                409,
                "Running, review-ready, or shipping tasks cannot be deleted",
            )
        if not get_dashboard_store().delete_task(task_id):
            raise HTTPException(404, f"Task '{task_id}' not found")
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(status_code=204)
