# SRI OS Command Center — Deployment Guide (Render)

## Overview

Two services deploy to Render:
- **Backend** (`sri-command-center-api`) — FastAPI + uvicorn, Python 3.11
- **Frontend** (`sri-command-center`) — React + Vite static site

Both are free-tier Render services. The `render.yaml` at the repo root
defines both automatically.

---

## Step 1 — Push the repo to GitHub

The code currently lives locally. It needs to be in a GitHub repo for
Render to deploy it.

```bash
cd ~/Downloads/design_handoff_sri_os_command_center
git init
git add .
git commit -m "feat: SRI OS Command Center v2 — full stack with Drive projects integration"
git remote add origin https://github.com/sri-intel/sri-command-center.git
git push -u origin main
```

> If the repo already exists on GitHub, skip `git init` and `git remote add`.
> Just commit and push.

---

## Step 2 — Deploy on Render via render.yaml

1. Go to https://dashboard.render.com
2. Click **New** → **Blueprint**
3. Connect your GitHub account and select the `sri-intel/sri-command-center` repo
4. Render will detect `render.yaml` and show both services
5. Click **Apply** — Render creates and deploys both services

---

## Step 3 — Set environment variables in Render dashboard

### Backend (`sri-command-center-api`)

After the first deploy, go to the service → **Environment** tab and set:

| Key | Value |
|-----|-------|
| `GITHUB_TOKEN` | Your GitHub personal access token (classic, `repo` scope) |
| `DRIVE_ROOT_FOLDER_ID` | `18LyrWJbV2L01N_6T52BmPcsRr1nJjBcV` (already in render.yaml) |
| `GITHUB_REPOS` | `sri-intel/legal-agent-os,sri-intel/builder-os,sri-intel/marketing-os` |
| `CACHE_TTL` | `300` |

> **Security rule (verbatim):** All credentials (API keys, OAuth tokens,
> signing keys) are stored in operator-managed `.env` files or system keychain.
> Never in Drive. Never in any OS file.

### Frontend (`sri-command-center`)

| Key | Value |
|-----|-------|
| `VITE_API_URL` | `https://sri-command-center-api.onrender.com` (your backend URL) |

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

When the Google Drive ADC scope is fixed (Task #8 — create OAuth Client ID
in Google Cloud Console, re-run gcloud auth), the backend will also read
Drive signal files for real-time agent status updates.

---

## Local dev (unchanged)

```bash
cd ~/Downloads/design_handoff_sri_os_command_center
make install    # sets up Python venv + npm deps
make dev-api    # FastAPI on :8000
make dev        # Vite on :5173
```
