"""app/routers/graph.py — Graph endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from app.config import settings
from app.models import GraphData, AddGraphLinkRequest
from app.routers.legal import require_operator
from app.services import drive
from app.services.ws_manager import broadcast_graph_node_updated, manager

router = APIRouter(prefix="/api/graph", tags=["graph"])

# In-memory extra links (added via POST /api/graph/links)
_extra_links: list = []


@router.get(
    "",
    response_model=GraphData,
    dependencies=[Depends(require_operator)],
)
def get_graph():
    data = drive.get_graph()
    data.links.extend(_extra_links)
    return data


@router.post(
    "/links",
    status_code=201,
    dependencies=[Depends(require_operator)],
)
async def add_link(body: AddGraphLinkRequest):
    if not settings.command_dispatch_enabled:
        raise HTTPException(503, "Graph mutation adapter is not connected")
    link = {"source": body.source, "target": body.target}
    _extra_links.append(link)
    await manager.broadcast({"type": "graph.link.added", "link": link})
    return link


@router.post(
    "/nodes/{node_id}/complete",
    status_code=202,
    dependencies=[Depends(require_operator)],
)
async def mark_complete(node_id: str):
    if not settings.command_dispatch_enabled:
        raise HTTPException(503, "Graph mutation adapter is not connected")
    data = drive.get_graph()
    node = next((n for n in data.nodes if n.id == node_id), None)
    if not node:
        raise HTTPException(404, f"Node '{node_id}' not found")
    if not drive.write_signal(
        node.os,
        "graph-node-complete",
        {"node_id": node_id, "status": "COMPLETE"},
    ):
        raise HTTPException(503, "Graph update could not be delivered")
    updated = node.model_copy(update={"status": "COMPLETE"})
    await broadcast_graph_node_updated(updated.model_dump())
    return updated
