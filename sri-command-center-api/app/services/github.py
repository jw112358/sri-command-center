"""app/services/github.py

GitHub data layer for SRI OS Command Center.

Surfaces real PR and CI data for Builder OS projects and agents.
Falls back gracefully when GITHUB_TOKEN is not set.

Data exposed:
  - get_github_projects()  →  List[Project]  (Builder OS lane from PR status)
  - get_github_agents()    →  List[Agent]    (CI workflow runs as running agents)
  - enrich_projects()      →  adds ciStatus + githubPrCount to existing projects
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models import (
    Agent, AgentStatus, Lane, Priority, Project,
)

log = logging.getLogger(__name__)

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


# ── GitHub client (lazy init) ──────────────────────────────────────────────────
_gh = None


def _get_github():
    global _gh
    if _gh is not None:
        return _gh
    if not settings.github_enabled:
        return None
    try:
        from github import Github
        _gh = Github(settings.github_token)
        log.info("GitHub client initialized")
    except Exception as e:
        log.warning(f"GitHub init failed ({e}); skipping GitHub data")
        _gh = None
    return _gh


# ── Repo helpers ───────────────────────────────────────────────────────────────

def _get_repos():
    gh = _get_github()
    if not gh:
        return []
    repos = []
    for slug in settings.github_repos_list:
        try:
            repos.append(gh.get_repo(slug))
        except Exception as e:
            log.warning(f"Could not access repo {slug}: {e}")
    return repos


# ── PR status → project lane mapping ──────────────────────────────────────────

def _pr_to_lane(pr) -> Lane:
    """Map a PR's state + review status to a Mission Control lane."""
    if pr.merged:
        return Lane.COMPLETE
    if pr.state == "closed":
        return Lane.COMPLETE
    # Check CI status via combined status
    try:
        combined = pr.head.repo.get_commit(pr.head.sha).get_combined_status()
        ci_state = combined.state  # "success" | "failure" | "pending"
    except Exception:
        ci_state = "pending"

    if ci_state == "failure":
        return Lane.BLOCKED
    if pr.draft:
        return Lane.PLANNING
    return Lane.IN_PROGRESS


def _ci_status_label(pr) -> str:
    """Return "passing" | "failing" | "pending" for a PR."""
    try:
        combined = pr.head.repo.get_commit(pr.head.sha).get_combined_status()
        state = combined.state
        return "passing" if state == "success" else "failing" if state == "failure" else "pending"
    except Exception:
        return "pending"


# ── Public service methods ────────────────────────────────────────────────────

def get_github_projects() -> List[Project]:
    """
    Return one Project per open pull request across all watched repos.
    PR number is used as project ID (prefixed with repo slug).
    """
    cached = _cached("gh_projects")
    if cached is not None:
        return cached

    if not settings.github_enabled:
        return _store("gh_projects", [])

    projects = []
    for repo in _get_repos():
        try:
            prs = list(repo.get_pulls(state="open", sort="updated", direction="desc"))
            for pr in prs[:20]:  # cap 20 per repo
                proj_id = f"gh:{repo.name}:pr{pr.number}"
                lane = _pr_to_lane(pr)
                ci = _ci_status_label(pr)

                # Priority from PR labels
                priority = Priority.MED
                label_names = [l.name.lower() for l in pr.labels]
                if any(l in label_names for l in ("high-priority", "critical", "urgent", "p0", "p1")):
                    priority = Priority.HIGH
                elif any(l in label_names for l in ("low-priority", "nice-to-have", "p3")):
                    priority = Priority.LOW

                projects.append(Project(
                    id=proj_id,
                    name=f"PR #{pr.number}: {pr.title[:60]}",
                    os="builder",
                    owner=pr.user.login if pr.user else "—",
                    priority=priority,
                    lane=lane,
                    updatedAt=pr.updated_at.isoformat() if pr.updated_at else _now_iso(),
                    githubRepo=repo.full_name,
                    githubPrCount=1,
                    ciStatus=ci,
                ))
        except Exception as e:
            log.warning(f"Error fetching PRs for {repo.full_name}: {e}")

    return _store("gh_projects", projects)


def get_github_agents() -> List[Agent]:
    """
    Return active CI workflow runs as agents (status RUNNING / ERROR / STOPPED).
    Each in-progress workflow run becomes a 'ci-runner' agent.
    """
    cached = _cached("gh_agents")
    if cached is not None:
        return cached

    if not settings.github_enabled:
        return _store("gh_agents", [])

    agents = []
    for repo in _get_repos():
        try:
            runs = repo.get_workflow_runs(status="in_progress")
            for run in list(runs)[:5]:  # cap 5 per repo
                agent_id = f"gh-ci:{repo.name}:{run.id}"
                agents.append(Agent(
                    id=agent_id,
                    name=f"ci-runner [{repo.name}]",
                    os="builder",
                    status=AgentStatus.RUNNING,
                    task=f"{run.name} on {run.head_branch} (run #{run.run_number})",
                    startedAt=run.created_at.isoformat() if run.created_at else _now_iso(),
                    skill="builder.ci_run",
                    inputs=[
                        f"repo={repo.full_name}",
                        f"branch={run.head_branch}",
                        f"run={run.run_number}",
                        f"trigger={run.event}",
                    ],
                    outputs=_workflow_outputs(run),
                ))
        except Exception as e:
            log.warning(f"Error fetching workflow runs for {repo.full_name}: {e}")

    return _store("gh_agents", agents)


def enrich_projects(projects: List[Project]) -> List[Project]:
    """
    Add ciStatus and githubPrCount to existing projects whose name or ID
    matches a GitHub repo. Used to enrich Drive-sourced projects.
    """
    if not settings.github_enabled:
        return projects

    gh_projects = get_github_projects()
    # Build a lookup: repo_name → list of gh_projects
    repo_map: Dict[str, List[Project]] = {}
    for gp in gh_projects:
        if gp.githubRepo:
            repo_map.setdefault(gp.githubRepo.split("/")[-1].lower(), []).append(gp)

    enriched = []
    for p in projects:
        name_key = p.name.lower().replace(" ", "-")
        matches = repo_map.get(name_key, [])
        if matches:
            # Aggregate: failing if any fail, else passing if any pass, else pending
            statuses = [m.ciStatus for m in matches if m.ciStatus]
            ci = "failing" if "failing" in statuses else "passing" if "passing" in statuses else "pending"
            enriched.append(p.model_copy(update={
                "ciStatus": ci,
                "githubPrCount": len(matches),
            }))
        else:
            enriched.append(p)

    return enriched


def get_recent_commits_for_agent(agent_id: str, limit: int = 20) -> List[str]:
    """
    Return recent commit messages for a CI agent, formatted as log lines.
    Used to seed the terminal log for GitHub-sourced agents.
    """
    if not settings.github_enabled or not agent_id.startswith("gh-ci:"):
        return []
    parts = agent_id.split(":")
    if len(parts) < 3:
        return []
    repo_name = parts[1]
    run_id = int(parts[2]) if parts[2].isdigit() else None
    if not run_id:
        return []

    gh = _get_github()
    if not gh:
        return []

    lines = []
    try:
        # Find repo
        for slug in settings.github_repos_list:
            if slug.split("/")[-1] == repo_name:
                repo = gh.get_repo(slug)
                run = repo.get_workflow_run(run_id)
                lines.append(f"[{run.name}] run #{run.run_number} · {run.event}")
                lines.append(f"→ branch: {run.head_branch}")
                lines.append(f"→ commit: {run.head_sha[:8]} {run.head_commit.message.splitlines()[0] if run.head_commit else ''}")
                # Get job steps
                jobs = list(run.jobs())
                for job in jobs[:3]:
                    status_icon = "✓" if job.conclusion == "success" else "✗" if job.conclusion == "failure" else "…"
                    lines.append(f"{status_icon} {job.name}")
                    for step in list(job.steps)[:5]:
                        step_icon = "✓" if step.conclusion == "success" else "✗" if step.conclusion == "failure" else "  "
                        lines.append(f"  {step_icon} {step.name}")
                break
    except Exception as e:
        log.warning(f"Could not fetch commit log for {agent_id}: {e}")

    return lines[:limit]


# ── Utilities ─────────────────────────────────────────────────────────────────

def _workflow_outputs(run) -> List[str]:
    """Build output lines for a workflow run."""
    outputs = []
    try:
        jobs = list(run.jobs())
        total = len(jobs)
        done = sum(1 for j in jobs if j.conclusion in ("success", "failure", "skipped"))
        outputs.append(f"{done}/{total} jobs complete")
        failed = [j.name for j in jobs if j.conclusion == "failure"]
        if failed:
            outputs.extend(f"ERR: {n}" for n in failed[:3])
        passed = [j.name for j in jobs if j.conclusion == "success"]
        if passed:
            outputs.append(f"✓ {len(passed)} jobs passed")
    except Exception:
        outputs.append("status: in_progress")
    return outputs


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_repo_completion_pct(repo_slug: str) -> Optional[float]:
    """
    Return 0-100 completion % for a repo based on merged vs total PRs
    (merged / (merged + open)) * 100. Cached separately per repo.

    Falls back to None if GitHub is not enabled or the repo is inaccessible.
    """
    cache_key = f"completion:{repo_slug}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    gh = _get_github()
    if not gh:
        return None

    try:
        repo = gh.get_repo(repo_slug)
        open_prs   = repo.get_pulls(state="open").totalCount
        closed_prs = repo.get_pulls(state="closed").totalCount  # includes merged + rejected
        total = open_prs + closed_prs
        if total == 0:
            return _store(cache_key, 0.0)
        pct = round((closed_prs / total) * 100, 1)
        return _store(cache_key, pct)
    except Exception as e:
        log.warning(f"Could not compute completion for {repo_slug}: {e}")
        return None


def get_all_repo_completion() -> Dict[str, float]:
    """
    Return {repo_name_lower: completion_pct} for all watched repos.
    Used by drive.get_graph() to size project nodes.
    """
    result: Dict[str, float] = {}
    for slug in settings.github_repos_list:
        pct = get_repo_completion_pct(slug)
        if pct is not None:
            name = slug.split("/")[-1].lower()
            result[name] = pct
    return result


def invalidate_cache() -> None:
    _cache.clear()
    _cache_ts.clear()
