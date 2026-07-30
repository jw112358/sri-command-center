"""Cross-project material-session continuity feed."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import CreateSessionSummaryRequest, SessionBrief
from app.routers.legal import require_operator
from app.services.orchestrator_auth import require_operator_or_worker
from app.services.session_briefs import create_session_summary, list_session_briefs

router = APIRouter(prefix="/api/session-briefs", tags=["session-briefs"])


@router.get(
    "",
    response_model=list[SessionBrief],
    dependencies=[Depends(require_operator)],
)
def briefs(limit: int = Query(default=50, ge=1, le=100)):
    return list_session_briefs(limit)


@router.post(
    "",
    response_model=SessionBrief,
    status_code=201,
    dependencies=[Depends(require_operator_or_worker)],
)
def file_material_summary(body: CreateSessionSummaryRequest):
    try:
        return create_session_summary(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            503,
            "The material session summary could not be filed in Google Drive",
        ) from exc
