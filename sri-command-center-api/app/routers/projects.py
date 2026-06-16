"""app/routers/projects.py — Mission Control project endpoints"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from typing import List

from app.models import Project, CreateProjectRequest, PatchProjectRequest
from app.services import drive
from app.services.ws_manager import broadcast_project_updated

router = APIRouter(prefix="/api/projects", tags=["projects"])

# In-memory mutation store (mutations written to Drive signals + kept here for instant response)
_overrides: dict = {}  # project_id → partial dict


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

    # Apply in-memory lane overrides from PATCH calls
    result = []
    for p in projects:
        if p.id in _overrides:
            p = p.model_copy(update=_overrides[p.id])
        result.append(p)

    return result


@router.post("", response_model=Project, status_code=201)
async def create_project(body: CreateProjectRequest):
    from app.models import Lane
    import uuid
    proj = Project(
        id=f"p:{uuid.uuid4().hex[:8]}",
        name=body.name,
        os=body.os,
        owner=body.owner,
        priority=body.priority,
        lane=Lane.PLANNING,
        updatedAt=datetime.now(timezone.utc).isoformat(),
    )
    drive.write_signal(body.os, "project-created", proj.model_dump())
    await broadcast_project_updated(proj.model_dump())
    return proj


@router.patch("/{project_id}", response_model=Project)
async def patch_project(project_id: str, body: PatchProjectRequest):
    projects = {p.id: p for p in drive.get_projects()}

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

    # Store override for fast response; also write signal
    _overrides[project_id] = {**_overrides.get(project_id, {}), **patch}
    updated = proj.model_copy(update=patch)

    drive.write_signal(updated.os, "project-updated", updated.model_dump())
    await broadcast_project_updated(updated.model_dump())
    return updated
