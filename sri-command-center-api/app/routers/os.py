"""app/routers/os.py — OS Registry endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.config import settings
from app.models import OSPlugin, LaunchOSRequest
from app.routers.legal import require_operator
from app.services import drive

router = APIRouter(prefix="/api/os", tags=["os"])


@router.get("", response_model=List[OSPlugin])
def list_os():
    return drive.get_os_plugins()


@router.post(
    "/{os_id}/launch",
    status_code=202,
    dependencies=[Depends(require_operator)],
)
def launch_os(os_id: str, body: LaunchOSRequest = LaunchOSRequest()):
    plugins = {p.id: p for p in drive.get_os_plugins()}
    if os_id not in plugins:
        raise HTTPException(404, f"OS '{os_id}' not found")
    if not settings.command_dispatch_enabled:
        raise HTTPException(503, "Command adapter is not connected")
    if not drive.write_signal(os_id, "launch", {
            "os_id": os_id,
            "task": body.task or f"operator-launched {os_id}",
            "inputs": body.inputs,
            "status": "RUNNING",
    }):
        raise HTTPException(503, "Launch command could not be delivered")
    return {"status": "accepted", "os": os_id}


@router.post(
    "/{os_id}/configure",
    dependencies=[Depends(require_operator)],
)
def configure_os(os_id: str):
    raise HTTPException(
        501,
        f"Configuration adapter for OS '{os_id}' is not connected",
    )
