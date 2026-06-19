# SRI OS Command Center — Deployment Guide (Render)

## Overview

Two services deploy to Render:
- **Backend** (`sri-command-center-api`) — FastAPI + uvicorn, Python 3.11
- **Frontend** (`sri-command-center`) — React + Vite static site

Both are free-tier Render services. The `render.yaml` at the repo root
defines both automatically.

---

## Step 1 — Push the repo to GitHub ✅ DONE (2026-06-15)

Repo is live at: **https://github.com/jw112358/sri-command-center**

```bash
# Already done — remote is set to:
# https://github.com/jw112358/sri-command-center.git
# Future updates: git add . && git commit -m "..." && git push
```

> Note: Repo is under `jw112358` (personal account). The `sri-intel` org
> was not accessible from this GitHub account. Repo can be transferred to
> an org later via GitHub Settings → Transfer ownership.

---

## Step 2 — Deploy on Render via render.yaml 🔄 IN PROGRESS (2026-06-15)

1. Go to https://dashboard.render.com
2. Click **Blueprints** → **+ New Blueprint Instance**
3. Select `jw112358/sri-command-center` → **Connect**
4. Blueprint Name: `SRI OS Command Center`, Branch: `main`
5. Render detects `render.yaml` and shows both services
6. Fill in env vars (see Step 3) → Click **Apply**

**Status:** Stopped at Step 6 — `VITE_API_URL` is filled in.
`GITHUB_TOKEN` needs to be entered before clicking Apply.

---

## Step 3 — Set environment variables in Render dashboard

### Backend (`sri-command-center-api`)

Fill these in the Blueprint form before clicking Apply (or via service → Environment tab):

| Key | Value | Status |
|-----|-------|--------|
| `GITHUB_TOKEN` | Classic PAT, `repo` scope — generate at github.com/settings/tokens | ⏳ TODO |
| `DRIVE_ROOT_FOLDER_ID` | `18LyrWJbV2L01N_6T52BmPcsRr1nJjBcV` | ✅ in render.yaml |
| `GITHUB_REPOS` | `jw112358/legal-agent-os,jw112358/builder-os,jw112358/marketing-os` | ✅ in render.yaml |
| `CACHE_TTL` | `300` | ✅ in render.yaml |

> **Security rule (verbatim):** All credentials (API keys, OAuth tokens,
> signing keys) are stored in operator-managed `.env` files or system keychain.
> Never in Drive. Never in any OS file.

### Frontend (`sri-command-center`)

| Key | Value | Status |
|-----|-------|--------|
| `VITE_API_URL` | `https://sri-command-center-api.onrender.com` | ✅ filled in Blueprint form |

---

## Step 4 — Verify the deployment

1. Frontend URL: `https://sri-command-center.onrender.com`
2. Backend health: `https://sri-command-center-api.onrender.com/api/health`
3. Projects API: `https://sri-command-center-api.onrender.com/api/projects`
4. Graph API: `https://sri-command-center-api.onrender.com/api/graph`

If the backend shows healthy and the frontend loads the 3D graph with 8
SRI projects, deployment is complete.

---

## Custom Domain (optional)

In the Render dashboard → frontend service → **Custom Domains**:
- Add `command-center.sri-intel.com` (or your preferred subdomain)
- Add the CNAME record your DNS provider shows
- Render provisions SSL automatically

---

## Updating project status (session summaries)

After each working session, update `sri-command-center-api/data/sri-projects.json`:

```json
{
  "id": "legal-agent-os",
  "completionPct": 75,    ← update this after progress
  "lane": "IN_PROGRESS",
  "notes": "Week 3 complete. QA skill deployed. Docket-watcher live.",
  "updatedAt": "2026-06-20"
}
```

Then commit and push — Render redeploys the backend automatically,
and the 3D graph spheres update on next page load.

---

## Architecture notes

```
Render static site (sri-command-center)
  │  VITE_API_URL →
  └─► Render web service (sri-command-center-api)
        │  reads
        ├─► data/sri-projects.json   (session-summary project registry)
        ├─► GitHub API (PyGithub)    (PR completion per repo)
        └─► Google Drive API (ADC)   (signal files — when Drive scope fixed)
```

**Note on Google Drive ADC (2026-06-15):** The sri-intel Google Workspace org
policy blocks OAuth flows entirely — "This app is blocked" regardless of test
user settings. Drive ADC is abandoned. The backend reads `data/sri-projects.json`
as the primary data source instead. This is sufficient for the current use case.

---

## Local dev (unchanged)

```bash
cd ~/Downloads/design_handoff_sri_os_command_center
make install    # sets up Python venv + npm deps
make dev-api    # FastAPI on :8000
make dev        # Vite on :5173
```
