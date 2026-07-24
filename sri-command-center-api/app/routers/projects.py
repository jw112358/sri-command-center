"""app/routers/projects.py — Mission Control project endpoints"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import List

from app.models import Project, CreateProjectRequest, PatchProjectRequest
from app.routers.legal import require_operator
from app.services import drive
from app.services.dashboard_state import (
    DashboardStateUnavailable,
    get_dashboard_store,
)
from app.services.ws_manager import broadcast_project_updated

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=List[Project])
def list_projects():
    projects = drive.get_projects()

    # Enrich with GitHub CI data
    try:
        from app.services.github import enrich_projects, get_github_projects
        projects = enrich_projects(projects)
        # Append GitHub-native projects (open PRs) not already in Drive
        existing_ids = {p.id for p in projects}
        gh_projs = get_github_projects()
        projects += [p for p in gh_projs if p.id not in existing_ids]
    except Exception:
        pass

    try:
        dashboard_projects = {
            project.id: project for project in get_dashboard_store().list_projects()
        }
    except DashboardStateUnavailable:
        dashboard_projects = {}
    merged = {project.id: project for project in projects}
    merged.update(dashboard_projects)
    return list(merged.values())


@router.post(
    "",
    response_model=Project,
    status_code=201,
    dependencies=[Depends(require_operator)],
)
async def create_project(body: CreateProjectRequest):
    try:
        proj = get_dashboard_store().create_project(
            name=body.name,
            os_id=body.os,
            owner=body.owner,
            priority=body.priority,
        )
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    await broadcast_project_updated(proj.model_dump())
    return proj


@router.patch(
    "/{project_id}",
    response_model=Project,
    dependencies=[Depends(require_operator)],
)
async def patch_project(project_id: str, body: PatchProjectRequest):
    projects = {p.id: p for p in list_projects()}

    # Also search GitHub projects
    try:
        from app.services.github import get_github_projects
        for gp in get_github_projects():
            projects.setdefault(gp.id, gp)
    except Exception:
        pass

    proj = projects.get(project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")

    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    patch["updatedAt"] = datetime.now(timezone.utc).isoformat()

    updated = proj.model_copy(update=patch)
    try:
        updated = get_dashboard_store().upsert_project(updated)
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    await broadcast_project_updated(updated.model_dump())
    return updated


@router.delete(
    "/{project_id}",
    status_code=204,
    dependencies=[Depends(require_operator)],
)
async def delete_project(project_id: str):
    if not project_id.startswith("p:"):
        raise HTTPException(
            409,
            "Canonical registry projects cannot be deleted from Mission Control",
        )
    try:
        if not get_dashboard_store().delete_project(project_id):
            raise HTTPException(404, f"Project '{project_id}' not found")
    except DashboardStateUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(status_code=204)
