# SRI OS Command Center — Session Handoff
Last updated: 2026-06-11

---

## What's Done

All 6 backend/frontend integration phases are complete:

| # | Task | Status |
|---|------|--------|
| 1 | Scaffold FastAPI backend (`sri-command-center-api/`) | ✅ |
| 2 | Google Drive data layer (`services/drive.py`) | ✅ |
| 3 | GitHub data layer (`services/github.py`) | ✅ |
| 4 | WebSocket live agent log streaming | ✅ |
| 5 | Frontend mock data → live API calls | ✅ |
| 6 | Concurrency launcher (`Makefile` + `npm run dev:all`) | ✅ |
| 7 | Full stack end-to-end verification | 🔄 In progress |
| 8 | Fix Google Drive ADC scope | ⏳ Next session |

---

## Current State

### API Server — RUNNING ✅
- Python 3.11 venv is correct and working
- `make dev-api` works from repo root
- FastAPI starts cleanly, WebSockets connect
- GitHub data: loading (token in `.env` is current)
- Google Drive data: **403 insufficientPermissions** (see blocker below)

### Frontend — RUNNING ✅
- Vite dev server on `http://localhost:5173`
- Footer shows "CONNECTED · LIVE DATA"
- GitHub projects visible in Mission Control

### One Remaining Blocker: Google Drive Scope
ADC credentials exist at:
```
~/.config/gcloud/application_default_credentials.json
```
But they were granted **without** the Drive read scope. Attempt to re-login with Drive scope was blocked by Google (org policy rejects the default ADC OAuth client).

---

## Next Session — Exact Steps to Fix Drive

### Step 1: Create an OAuth Client ID (one-time)
1. Go to https://console.cloud.google.com → project **legal-agent-os**
2. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Name: `SRI Command Center Dev`
5. Click **Create** → **Download JSON**
6. Save to: `~/.config/gcloud/sri-oauth-client.json`

### Step 2: Re-run ADC login with Drive scope
```bash
gcloud auth application-default login \
  --client-id-file=~/.config/gcloud/sri-oauth-client.json \
  --scopes=https://www.googleapis.com/auth/drive.readonly,https://www.googleapis.com/auth/cloud-platform
```
Browser opens → sign in with `jeff@sri-intel.com` → grant access.

> **If consent screen says "Testing" / access blocked:**
> Go to APIs & Services → OAuth consent screen → Test users → Add `jeff@sri-intel.com`

### Step 3: Restart the API
```bash
cd ~/Downloads/design_handoff_sri_os_command_center
make dev-api
```
Drive poll runs every 30s — signals should start loading within a minute.

---

## Key File Locations

```
design_handoff_sri_os_command_center/
├── Makefile                          # make dev-api, make dev, make dev-ui
├── sri-command-center/               # React/Vite frontend (port 5173)
│   ├── src/
│   │   ├── App.tsx                   # Boot, health poll, WebSocket
│   │   ├── components/
│   │   │   ├── CommandCenter.tsx     # Agent control panel
│   │   │   ├── MissionControl.tsx    # GitHub project board
│   │   │   ├── Notebook.tsx          # Notes
│   │   │   └── Graph.tsx             # 3D agent graph
│   │   ├── api/client.ts             # All API calls (REST + WS)
│   │   └── types.ts                  # Shared TypeScript types
│   └── .env.local                    # VITE_API_URL=http://localhost:8000
└── sri-command-center-api/           # FastAPI backend (port 8000)
    ├── .env                          # DRIVE_ROOT_FOLDER_ID, GITHUB_TOKEN, etc.
    ├── setup.sh                      # Rebuild venv with Python 3.11+
    ├── requirements.txt
    └── app/
        ├── main.py
        ├── config.py
        ├── services/
        │   ├── drive.py              # Google Drive signal reader (ADC auth)
        │   ├── github.py             # PyGithub PR + CI data
        │   └── ws_manager.py         # WebSocket broadcast manager
        └── routers/
            ├── agents.py
            ├── projects.py
            ├── notes.py
            ├── events.py
            ├── graph.py
            └── os.py
```

## Critical Credentials (NEVER commit)

| Credential | Location |
|-----------|----------|
| Google ADC | `~/.config/gcloud/application_default_credentials.json` |
| OAuth client (to create) | `~/.config/gcloud/sri-oauth-client.json` |
| GitHub token | `sri-command-center-api/.env` → `GITHUB_TOKEN` |
| Drive folder ID | `sri-command-center-api/.env` → `DRIVE_ROOT_FOLDER_ID=18LyrWJbV2L01N_6T52BmPcsRr1nJjBcV` |

## Start Commands (both servers)
```bash
cd ~/Downloads/design_handoff_sri_os_command_center
make dev          # frontend + backend together
# or separately:
make dev-ui       # Vite on :5173
make dev-api      # uvicorn on :8000
```
