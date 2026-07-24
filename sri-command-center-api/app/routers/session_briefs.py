"""Read-only cross-project session continuity feed."""
from fastapi import APIRouter, Depends, Query

from app.models import SessionBrief
from app.routers.legal import require_operator
from app.services.session_briefs import list_session_briefs

router = APIRouter(prefix="/api/session-briefs", tags=["session-briefs"])


@router.get(
    "",
    response_model=list[SessionBrief],
    dependencies=[Depends(require_operator)],
)
def briefs(limit: int = Query(default=50, ge=1, le=100)):
    return list_session_briefs(limit)
