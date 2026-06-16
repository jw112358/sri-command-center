"""app/services/drive.py

Google Drive data layer for SRI OS Command Center.

Signal file convention (from SRI Agent Platform spec):
  Path:  <DRIVE_ROOT>/<OS_ID>/signals/YYYY-MM-DD_<OS_SLUG>_<event-type>.md
  Front-matter keys the backend reads:
    agent_id, agent_name, status, task, skill, inputs, outputs,
    project_id, project_name, project_os, project_owner, priority, lane,
    note_id, note_title, note_tag, note_body

When DRIVE_ROOT_FOLDER_ID is not set the service falls back to mock data
so the frontend always has something to display during local development.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import frontmatter  # python-frontmatter

from app.config import settings
from app.models import (
    Agent, AgentStatus, GraphData, GraphLink, GraphNode,
    Lane, NodeKind, NodeStatus, Note, OSPlugin, OSStatus, Priority, Project,
    SystemEvent, EventSeverity,
)

log = logging.getLogger(__name__)

# ── OS registry (static identity; Drive enriches status + agent counts) ────────
OS_REGISTRY_STATIC: List[Dict[str, Any]] = [
    {"id": "builder",   "name": "Builder OS"},
    {"id": "legal",     "name": "Legal OS"},
    {"id": "marketing", "name": "Marketing OS"},
    {"id": "finance",   "name": "Finance OS"},
    {"id": "jkauthor",  "name": "JK Author OS"},
    {"id": "brand",     "name": "Brand Voice OS"},
    {"id": "blotato",   "name": "Marketing-OS (Blotato/Postiz)"},
    {"id": "prod",      "name": "Productivity OS"},
]

# ── Simple TTL cache ────────────────────────────────────────────────────────────
_cache: Dict[str, Any] = {}
_cache_ts: Dict[str, float] = {}


def _cached(key: str) -> Optional[Any]:
    if key in _cache and (time.time() - _cache_ts.get(key, 0)) < settings.cache_ttl:
        return _cache[key]
    return None


def _store(key: str, value: Any) -> Any:
    _cache[key] = value
    _cache_ts[key] = time.time()
    return value


# ── Drive client (lazy init) ───────────────────────────────────────────────────
_drive_service = None


def _get_drive_service():
    """Initialize Drive client.

    Auth priority:
      1. Application Default Credentials (ADC) — preferred; works when
         `gcloud auth application-default login` has been run, or inside
         GCP/Cloud Run with Workload Identity. No JSON key file needed.
         Organization policies that block service account key creation
         (iam.disableServiceAccountKeyCreation) are not a problem here.
      2. Service account JSON file — used only when
         GOOGLE_SERVICE_ACCOUNT_FILE is set in .env AND the file exists.
         Skip silently if the org policy blocks key creation.
    """
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    from googleapiclient.discovery import build

    # ── Attempt 1: Application Default Credentials ──────────────────────
    try:
        import google.auth
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        _drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
        log.info("Google Drive: authenticated via Application Default Credentials")
        return _drive_service
    except Exception as adc_err:
        log.debug(f"ADC not available ({adc_err}); trying service account file …")

    # ── Attempt 2: Service account JSON (optional) ───────────────────────
    sa_file = getattr(settings, "google_service_account_file", None)
    if sa_file and Path(sa_file).exists():
        try:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                sa_file,
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
            _drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
            log.info("Google Drive: authenticated via service account JSON")
            return _drive_service
        except Exception as sa_err:
            log.warning(f"Service account auth failed ({sa_err})")

    log.warning("Google Drive: no valid credentials found — using mock data fallback")
    _drive_service = None
    return _drive_service


# ── Drive file helpers ────────────────────────────────────────────────────────

def _list_files_in_folder(folder_id: str, name_contains: str = "") -> List[Dict]:
    svc = _get_drive_service()
    if not svc:
        return []
    query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    if name_contains:
        query += f" and name contains '{name_contains}'"
    try:
        result = svc.files().list(
            q=query,
            fields="files(id, name, modifiedTime)",
            orderBy="modifiedTime desc",
            pageSize=200,
        ).execute()
        return result.get("files", [])
    except Exception as e:
        log.warning(f"Drive list failed for folder {folder_id}: {e}")
        return []


def _list_subfolders(parent_id: str) -> List[Dict]:
    svc = _get_drive_service()
    if not svc:
        return []
    query = f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    try:
        result = svc.files().list(
            q=query,
            fields="files(id, name)",
            pageSize=100,
        ).execute()
        return result.get("files", [])
    except Exception as e:
        log.warning(f"Drive subfolder list failed: {e}")
        return []


def _read_file_text(file_id: str) -> str:
    svc = _get_drive_service()
    if not svc:
        return ""
    try:
        content = svc.files().get_media(fileId=file_id).execute()
        return content.decode("utf-8") if isinstance(content, bytes) else content
    except Exception as e:
        log.warning(f"Drive read failed for file {file_id}: {e}")
        return ""


def _find_folder_by_name(parent_id: str, name: str) -> Optional[str]:
    """Return folder ID of a direct child folder with the given name."""
    svc = _get_drive_service()
    if not svc:
        return None
    query = (
        f"'{parent_id}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{name}' "
        f"and trashed = false"
    )
    try:
        result = svc.files().list(q=query, fields="files(id)", pageSize=1).execute()
        files = result.get("files", [])
        return files[0]["id"] if files else None
    except Exception as e:
        log.warning(f"Drive folder search failed: {e}")
        return None


# ── Signal file parser ────────────────────────────────────────────────────────

def _parse_signal(raw: str) -> Dict[str, Any]:
    """Parse a signal .md file with YAML front-matter."""
    try:
        post = frontmatter.loads(raw)
        data = dict(post.metadata)
        data["_body"] = post.content
        return data
    except Exception:
        return {"_body": raw}


# ── OS-level signal scanning ──────────────────────────────────────────────────

def _scan_os_signals() -> Dict[str, List[Dict]]:
    """
    Returns a dict mapping os_id → list of parsed signal dicts.
    Walks: ROOT / <os_id> / signals / *.md
    Also checks ROOT / signals / *.md for cross-OS signals.
    """
    cached = _cached("raw_signals")
    if cached is not None:
        return cached

    if not settings.drive_enabled:
        return _store("raw_signals", {})

    root = settings.drive_root_folder_id
    result: Dict[str, List[Dict]] = {}

    # Scan per-OS subfolders
    os_folders = _list_subfolders(root)
    for folder in os_folders:
        os_id = folder["name"].lower().replace(" ", "").replace("-", "")
        # Normalize to our OS IDs
        os_id = _normalize_os_id(folder["name"])
        signals_folder_id = _find_folder_by_name(
            folder["id"], settings.drive_signals_folder_name
        )
        if not signals_folder_id:
            continue
        files = _list_files_in_folder(signals_folder_id, ".md")
        signals = []
        for f in files[:50]:  # cap at 50 most recent per OS
            raw = _read_file_text(f["id"])
            parsed = _parse_signal(raw)
            parsed["_filename"] = f["name"]
            parsed["_modified"] = f.get("modifiedTime", "")
            signals.append(parsed)
        result[os_id] = signals

    # Scan root-level signals/ folder (cross-OS)
    root_signals = _find_folder_by_name(root, settings.drive_signals_folder_name)
    if root_signals:
        files = _list_files_in_folder(root_signals, ".md")
        for f in files[:100]:
            raw = _read_file_text(f["id"])
            parsed = _parse_signal(raw)
            parsed["_filename"] = f["name"]
            parsed["_modified"] = f.get("modifiedTime", "")
            os_id = _os_id_from_filename(f["name"])
            result.setdefault(os_id, []).append(parsed)

    return _store("raw_signals", result)


def _normalize_os_id(folder_name: str) -> str:
    """Map Drive folder names to OS IDs."""
    mapping = {
        "builder": "builder", "builder os": "builder",
        "legal": "legal", "legal os": "legal",
        "marketing": "marketing", "marketing os": "marketing",
        "finance": "finance", "finance os": "finance",
        "jkauthor": "jkauthor", "jk author": "jkauthor", "jk author os": "jkauthor",
        "brand": "brand", "brand voice": "brand", "brand voice os": "brand",
        "blotato": "blotato", "marketing-os": "blotato", "postiz": "blotato",
        "prod": "prod", "productivity": "prod", "productivity os": "prod",
    }
    return mapping.get(folder_name.lower().strip(), folder_name.lower().replace(" ", ""))


def _os_id_from_filename(filename: str) -> str:
    """Extract OS slug from signal filename: YYYY-MM-DD_<OS_SLUG>_<event>.md"""
    parts = Path(filename).stem.split("_")
    return parts[1].lower() if len(parts) >= 3 else "unknown"


# ── Public service methods ────────────────────────────────────────────────────

def get_os_plugins() -> List[OSPlugin]:
    """
    Build OSPlugin list from static registry enriched with Drive signal data.
    Status is ACTIVE if any running agent signals exist, ERROR if error signals,
    IDLE otherwise.
    """
    signals = _scan_os_signals()

    plugins = []
    for os_def in OS_REGISTRY_STATIC:
        os_id = os_def["id"]
        os_signals = signals.get(os_id, [])

        # Count running agents from signal files
        running_agents = [
            s for s in os_signals
            if str(s.get("status", "")).upper() in ("RUNNING", "ACTIVE")
        ]
        error_agents = [
            s for s in os_signals
            if str(s.get("status", "")).upper() == "ERROR"
        ]

        if error_agents:
            status = OSStatus.ERROR
        elif running_agents:
            status = OSStatus.ACTIVE
        else:
            status = OSStatus.IDLE

        plugins.append(OSPlugin(
            id=os_id,
            name=os_def["name"],
            status=status,
            agents=len(running_agents),
        ))

    return plugins


def get_agents(status_filter: Optional[str] = None) -> List[Agent]:
    """
    Build Agent list from Drive signal files.
    Each signal file with agent_id / status fields becomes an Agent.
    """
    signals = _scan_os_signals()
    agents: List[Agent] = []
    seen_ids: set = set()

    for os_id, os_signals in signals.items():
        for sig in os_signals:
            agent_id = sig.get("agent_id") or sig.get("id")
            if not agent_id or agent_id in seen_ids:
                continue
            raw_status = str(sig.get("status", "RUNNING")).upper()
            try:
                agent_status = AgentStatus(raw_status)
            except ValueError:
                agent_status = AgentStatus.RUNNING

            if status_filter and agent_status.value.upper() != status_filter.upper():
                continue

            seen_ids.add(agent_id)
            agents.append(Agent(
                id=agent_id,
                name=sig.get("agent_name") or sig.get("name") or agent_id,
                os=os_id,
                status=agent_status,
                task=sig.get("task") or sig.get("_body", "")[:120] or "—",
                startedAt=sig.get("started_at") or sig.get("_modified") or _now_iso(),
                skill=sig.get("skill") or f"{os_id}.run",
                inputs=_coerce_list(sig.get("inputs", [])),
                outputs=_coerce_list(sig.get("outputs", [])),
            ))

    return agents


def get_agent(agent_id: str) -> Optional[Agent]:
    agents = get_agents()
    return next((a for a in agents if a.id == agent_id), None)


def get_agent_log(agent_id: str, limit: int = 80) -> list:
    """
    Return recent log lines for an agent.
    Looks for a log/ folder or a <agent_id>.log file in the OS signals folder.
    Falls back to empty list (WS streaming will fill the terminal).
    """
    # TODO: expand to read actual log files from Drive when they exist
    return []


def get_projects() -> List[Project]:
    """
    Build Project list, merging:
    1. SRI projects registry (data/sri-projects.json) — primary source for
       manually-curated project status and completionPct from session summaries
    2. Drive signal files — runtime agent/project signals from the OS folders
    3. GitHub PR projects — live repo data (when GitHub is connected)

    SRI registry projects take priority; signal-file and GitHub projects fill
    in any IDs not already covered.
    """
    # ── 1. SRI projects registry ────────────────────────────────────────────
    try:
        from app.services.sri_projects import get_sri_projects
        sri_projects = get_sri_projects()
    except Exception as e:
        log.debug(f"SRI projects registry unavailable: {e}")
        sri_projects = []

    seen_ids: set = {p.id for p in sri_projects}
    projects: List[Project] = list(sri_projects)

    # ── 2. Drive signal file projects ──────────────────────────────────────
    signals = _scan_os_signals()
    for os_id, os_signals in signals.items():
        for sig in os_signals:
            proj_id = sig.get("project_id") or sig.get("id")
            if not proj_id or proj_id in seen_ids:
                continue
            if not (sig.get("project_name") or sig.get("lane")):
                continue  # not a project signal

            seen_ids.add(proj_id)
            raw_lane = str(sig.get("lane", "PLANNING")).upper()
            lane_map = {
                "PLANNING": Lane.PLANNING,
                "IN PROGRESS": Lane.IN_PROGRESS,
                "IN_PROGRESS": Lane.IN_PROGRESS,
                "BLOCKED": Lane.BLOCKED,
                "COMPLETE": Lane.COMPLETE,
            }
            lane = lane_map.get(raw_lane, Lane.PLANNING)

            raw_priority = str(sig.get("priority", "MED")).upper()
            try:
                priority = Priority(raw_priority)
            except ValueError:
                priority = Priority.MED

            projects.append(Project(
                id=proj_id,
                name=sig.get("project_name") or sig.get("name") or proj_id,
                os=sig.get("project_os") or os_id,
                owner=sig.get("project_owner") or sig.get("owner") or "—",
                priority=priority,
                lane=lane,
                updatedAt=sig.get("updated_at") or sig.get("_modified") or _now_iso(),
            ))

    return projects


def get_notes() -> List[Note]:
    """Return notes (without body) from Drive signal files tagged as notes."""
    return [Note(**{**n.dict(), "body": None}) for n in _get_full_notes()]


def get_note(note_id: str) -> Optional[Note]:
    return next((n for n in _get_full_notes() if n.id == note_id), None)


def _get_full_notes() -> List[Note]:
    signals = _scan_os_signals()
    notes: List[Note] = []
    seen_ids: set = set()

    for os_id, os_signals in signals.items():
        for sig in os_signals:
            note_id = sig.get("note_id") or sig.get("id")
            if not note_id or note_id in seen_ids:
                continue
            if not (sig.get("note_title") or sig.get("note_body") or sig.get("title")):
                continue

            seen_ids.add(note_id)
            notes.append(Note(
                id=note_id,
                title=sig.get("note_title") or sig.get("title") or "Untitled",
                tag=sig.get("note_tag") or sig.get("tag") or "note",
                body=sig.get("note_body") or sig.get("_body") or "",
                updatedAt=sig.get("updated_at") or sig.get("_modified") or _now_iso(),
            ))

    return notes


def get_graph() -> GraphData:
    """Derive graph data from OS plugins + projects + agents + GitHub PRs.

    GitHub PR projects are included directly as project nodes. Completion %
    (merged / total PRs per repo) is attached to every project node so the
    3D graph can scale sphere size accordingly — larger sphere = closer to done.
    """
    os_plugins = get_os_plugins()
    projects = get_projects()
    agents = get_agents()

    nodes: List[GraphNode] = []
    links: List[GraphLink] = []
    skill_names = ["scaffold", "ci", "draft", "schedule", "score", "review", "sync", "index"]

    # ── GitHub completion data ────────────────────────────────────────────────
    gh_completion: Dict[str, float] = {}
    gh_projects: List[Project] = []
    try:
        from app.services.github import get_all_repo_completion, get_github_projects
        gh_completion = get_all_repo_completion()          # {repo_name: 0-100}
        gh_projects   = get_github_projects()              # PR-based project list
    except Exception as e:
        log.debug(f"GitHub graph data unavailable: {e}")

    # Merge GitHub projects, avoiding Drive duplicates
    existing_ids = {p.id for p in projects}
    all_projects = projects + [p for p in gh_projects if p.id not in existing_ids]

    # ── Hub nodes — one per OS ────────────────────────────────────────────────
    for i, os in enumerate(os_plugins):
        agent_count = sum(1 for a in agents if a.os == os.id)
        status = (
            NodeStatus.BLOCKED if os.status == OSStatus.ERROR
            else NodeStatus.ACTIVE
        )
        nodes.append(GraphNode(
            id=f"os:{os.id}",
            label=os.name.split("(")[0].strip(),
            kind=NodeKind.HUB,
            os=os.id,
            status=status,
            val=6 + agent_count,
        ))

        # Skill nodes for non-idle OSes
        if os.status != OSStatus.IDLE:
            for k in range(2):
                skill_id = f"skill:{os.id}:{k}"
                nodes.append(GraphNode(
                    id=skill_id,
                    label=f"{os.id}.{skill_names[(i + k) % len(skill_names)]}",
                    kind=NodeKind.SKILL,
                    os=os.id,
                    status=NodeStatus.COMPLETE,
                    val=1.0,
                ))
                links.append(GraphLink(source=f"os:{os.id}", target=skill_id))

    # ── Project nodes (Drive + GitHub) ────────────────────────────────────────
    for p in all_projects:
        node_status = (
            NodeStatus.BLOCKED  if p.lane == Lane.BLOCKED   else
            NodeStatus.COMPLETE if p.lane == Lane.COMPLETE  else
            NodeStatus.ACTIVE
        )

        # Derive completion %:
        # Priority order:
        #  1. p.completionPct  — set directly in sri-projects.json (session summaries)
        #  2. GitHub PR ratio  — merged/total PRs for the linked repo
        #  3. Lane fallback    — rough estimate when nothing else is available
        repo_name = (p.githubRepo or "").split("/")[-1].lower() if p.githubRepo else ""
        if p.completionPct is not None:
            completion_pct: Optional[float] = p.completionPct
        elif repo_name and repo_name in gh_completion:
            completion_pct = gh_completion[repo_name]
        else:
            lane_pct = {
                Lane.PLANNING:    10.0,
                Lane.IN_PROGRESS: 50.0,
                Lane.BLOCKED:     30.0,
                Lane.COMPLETE:   100.0,
            }
            completion_pct = lane_pct.get(p.lane, 10.0)

        nodes.append(GraphNode(
            id=f"proj:{p.id}",
            label=p.name[:40],          # cap label length for readability
            kind=NodeKind.PROJECT,
            os=p.os,
            status=node_status,
            val=3.0,
            completionPct=completion_pct,
        ))
        links.append(GraphLink(source=f"os:{p.os}", target=f"proj:{p.id}"))

    # ── Agent nodes ───────────────────────────────────────────────────────────
    for a in agents:
        status = NodeStatus.BLOCKED if a.status == AgentStatus.ERROR else NodeStatus.ACTIVE
        nodes.append(GraphNode(
            id=f"agent:{a.id}",
            label=a.name,
            kind=NodeKind.AGENT,
            os=a.os,
            status=status,
            val=1.6,
            agentId=a.id,
        ))
        links.append(GraphLink(source=f"os:{a.os}", target=f"agent:{a.id}"))

    return GraphData(nodes=nodes, links=links)


def get_events() -> List[SystemEvent]:
    """Derive recent system events from error signals."""
    events: List[SystemEvent] = []
    signals = _scan_os_signals()
    event_id = 0

    for os_id, os_signals in signals.items():
        for sig in os_signals:
            raw_status = str(sig.get("status", "")).upper()
            if raw_status == "ERROR":
                event_id += 1
                events.append(SystemEvent(
                    id=str(event_id),
                    severity=EventSeverity.ERROR,
                    text=f"{os_id} — {sig.get('agent_name', 'agent')} errored: {sig.get('task', '')}",
                    ts=sig.get("_modified") or _now_iso(),
                ))
            elif raw_status in ("RUNNING", "ACTIVE") and sig.get("agent_id"):
                event_id += 1
                events.append(SystemEvent(
                    id=str(event_id),
                    severity=EventSeverity.INFO,
                    text=f"{os_id} — {sig.get('agent_name', 'agent')} started: {sig.get('task', '')}",
                    ts=sig.get("_modified") or _now_iso(),
                ))

    return sorted(events, key=lambda e: e.ts, reverse=True)[:20]


def get_health():
    """Derive system health from OS plugin statuses."""
    plugins = get_os_plugins()
    faults = sum(1 for p in plugins if p.status == OSStatus.ERROR)
    return {
        "status": "DEGRADED" if faults else "NOMINAL",
        "faults": faults,
        "latencyMs": 0,
    }


# ── Mutation stubs (Drive is read-only; mutations write back via signal files) ─

def write_signal(os_id: str, event_type: str, data: Dict[str, Any]) -> bool:
    """
    Write a signal file back to Drive.
    Path: ROOT/<os_id>/signals/YYYY-MM-DD_<os_id>_<event_type>.md
    Returns True on success.
    """
    svc = _get_drive_service()
    if not svc or not settings.drive_enabled:
        log.info(f"[mock] write_signal {os_id}/{event_type}: {data}")
        return True  # no-op in dev

    try:
        from googleapiclient.http import MediaInMemoryUpload
        import yaml

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = f"{date_str}_{os_id}_{event_type}.md"
        front = yaml.dump(data, allow_unicode=True)
        content = f"---\n{front}---\n"

        # Find or create OS subfolder
        os_folders = _list_subfolders(settings.drive_root_folder_id)
        os_folder = next(
            (f for f in os_folders if _normalize_os_id(f["name"]) == os_id), None
        )
        if not os_folder:
            log.warning(f"OS folder not found for {os_id}")
            return False

        signals_folder_id = _find_folder_by_name(os_folder["id"], settings.drive_signals_folder_name)
        if not signals_folder_id:
            # Create signals folder
            meta = {"name": settings.drive_signals_folder_name, "mimeType": "application/vnd.google-apps.folder",
                    "parents": [os_folder["id"]]}
            signals_folder_id = svc.files().create(body=meta, fields="id").execute()["id"]

        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/markdown")
        svc.files().create(
            body={"name": filename, "parents": [signals_folder_id]},
            media_body=media,
            fields="id",
        ).execute()

        # Invalidate cache
        _cache.pop("raw_signals", None)
        return True

    except Exception as e:
        log.error(f"write_signal failed: {e}")
        return False


# ── Utilities ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        return [v] if v else []
    return []


def invalidate_cache() -> None:
    """Force re-fetch on next request."""
    _cache.clear()
    _cache_ts.clear()
