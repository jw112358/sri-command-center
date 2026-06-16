"""
services/sri_projects.py
Reads the SRI project registry from data/sri-projects.json.

Update sri-projects.json after each working session to refresh
the command center visualization. The file is the source of truth
for project state between real-time API updates.

When the Google Drive ADC scope issue is resolved (Task #8), this
service can optionally fetch the file from Drive instead, allowing
the command center to read updates without redeploying.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional
from app.models import Project, Lane, Priority

log = logging.getLogger(__name__)

# Path relative to the api root
_DATA_FILE = Path(__file__).parent.parent.parent / "data" / "sri-projects.json"

# Simple in-process cache (cleared on restart)
_cache: Optional[List[Project]] = None


def _lane(raw: str) -> Lane:
    mapping = {
        "PLANNING":    Lane.PLANNING,
        "IN_PROGRESS": Lane.IN_PROGRESS,
        "IN PROGRESS": Lane.IN_PROGRESS,
        "BLOCKED":     Lane.BLOCKED,
        "COMPLETE":    Lane.COMPLETE,
    }
    return mapping.get(raw.upper(), Lane.IN_PROGRESS)


def _priority(raw: str) -> Priority:
    mapping = {"HIGH": Priority.HIGH, "MED": Priority.MED, "LOW": Priority.LOW}
    return mapping.get(raw.upper(), Priority.MED)


def get_sri_projects() -> List[Project]:
    """Return SRI projects from the local JSON registry."""
    global _cache
    if _cache is not None:
        return _cache

    if not _DATA_FILE.exists():
        log.warning(f"Sri projects data file not found: {_DATA_FILE}")
        return []

    try:
        with open(_DATA_FILE, "r") as f:
            data = json.load(f)

        projects: List[Project] = []
        for item in data.get("projects", []):
            p = Project(
                id=item["id"],
                name=item["name"],
                os=item.get("os", "builder"),
                owner=item.get("owner", "SRI"),
                priority=_priority(item.get("priority", "MED")),
                lane=_lane(item.get("lane", "IN_PROGRESS")),
                completionPct=item.get("completionPct"),
                githubRepo=item.get("githubRepo"),
                notes=item.get("notes"),
                updatedAt=item.get("updatedAt"),
            )
            projects.append(p)

        log.info(f"Loaded {len(projects)} SRI projects from registry")
        _cache = projects
        return projects

    except Exception as e:
        log.error(f"Failed to load SRI projects: {e}")
        return []


def invalidate_cache() -> None:
    """Force a fresh read on next call (e.g., after file update)."""
    global _cache
    _cache = None
