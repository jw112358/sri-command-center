"""app/routers/os.py — OS Registry endpoints"""
from fastapi import APIRouter, HTTPException
from typing import List

from app.models import OSPlugin, LaunchOSRequest
from app.services import drive

router = APIRouter(prefix="/api/os", tags=["os"])


@router.get("", response_model=List[OSPlugin])
def list_os():
    return drive.get_os_plugins()


@router.post("/{os_id}/launch", status_code=202)
def launch_os(os_id: str, body: LaunchOSRequest = LaunchOSRequest()):
    plugins = {p.id: p for p in drive.get_os_plugins()}
    if os_id not in plugins:
        raise HTTPException(404, f"OS '{os_id}' not found")
    drive.write_signal(os_id, "launch", {
        "os_id": os_id,
        "task": body.task or f"operator-launched {os_id}",
        "inputs": body.inputs,
        "status": "RUNNING",
    })
    return {"status": "accepted", "os": os_id}


@router.post("/{os_id}/configure", status_code=202)
def configure_os(os_id: str):
    return {"status": "accepted", "os": os_id, "message": "configuration UI not yet implemented"}
