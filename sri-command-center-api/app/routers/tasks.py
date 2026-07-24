"""Durable Notebook task endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Response

from app.models import CreateTaskRequest, PatchTaskRequest, Task
from app.routers.legal import require_operator
from app.services.dashboard_state import (
    DashboardStateUnavailable,
    get_dashboard_store,
)

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
        return get_dashboard_store().create_task(body.text)
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
        task = get_dashboard_store().patch_task(task_id, patch)
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
        if not get_dashboard_store().delete_task(task_id):
            raise HTTPException(404, f"Task '{task_id}' not found")
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(status_code=204)
