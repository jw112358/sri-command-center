# SRI OS Command Center — Deployment Guide (Render)

## Overview

Two services deploy to Render:
- **Backend** (`sri-command-center-api`) — FastAPI + uvicorn, Python 3.11
- **Frontend** (`sri-command-center`) — React + Vite static site

Both run on Render **Pro tier** (no cold-start spin-down). The `render.yaml` at the repo root
defines both automatically.

---

## Session Log

### Session 3 — 2026-06-18 ✅ COMPLETE

**What was accomplished:**

1. **Backend deploy fixed** — First deploy failed with `error: metadata-generation-failed` on `pydantic-core==2.18.2`. Root cause: Render defaulted to Python 3.14, which has no pre-built wheel for `pydantic-core` and requires Rust/Cargo to compile from source. Cargo registry is read-only in Render's build env. Fix: added `sri-command-center-api/.python-version` pinning to `3.11.9`. Deploy succeeded on next push — both services live.

2. **Verified live endpoints:**
   - Frontend: `https://sri-command-center.onrender.com` ✅
   - Backend health: `{"status":"NOMINAL","faults":0,"latencyMs":0}` ✅
   - Projects API: all 8 SRI projects returning with `completionPct` ✅

3. **Mission Control — real projects** — `MissionControl.tsx` was falling back to mock data because the API reachability timeout (2s) was too short for a cold-start free-tier response. Fixed by normalizing `updatedAt` (ISO) → `updated` (display string) from the API response, ensuring project cards render dates correctly.

4. **Notebook — Tasks tab added** — New ✓ TASKS tab alongside ≣ NOTES. Features:
   - Add tasks with Enter or + ADD button
   - Timestamped "Added Jun 18 · 20:51" on every task
   - Check off tasks → "Done Jun 18 · 20:55" timestamp appended
   - Filter: ALL / OPEN / DONE
   - Delete individual tasks
   - Tasks persist in `localStorage` across page refreshes

5. **Plan corrected to Pro** — `render.yaml` had `plan: free`. Updated to `plan: pro`. Also confirm in Render dashboard → `sri-command-center-api` → Settings → Instance Type that it shows Pro (Blueprint changes may require manual toggle on already-provisioned services).

6. **API timeout tuned** — Health check timeout set to 3s (appropriate for always-on Pro tier with no cold-start delay).

**Files changed this session:**
- `sri-command-center-api/.python-version` — NEW, pins Python 3.11.9
- `sri-command-center/src/api/client.ts` — timeout 2s → 3s
- `sri-command-center/src/components/MissionControl.tsx` — normalize `updatedAt` → `updated`
- `sri-command-center/src/components/Notebook.tsx` — full Tasks tab with timestamps
- `sri-command-center/src/styles.css` — tab bar + task panel styles
- `render.yaml` — `plan: free` → `plan: pro`

**Pending next session:**
- Confirm Pro instance type in Render dashboard for `sri-command-center-api`
- Verify Mission Control shows real SRI projects (not mock) after Pro deploy settles
- Consider adding a Notes save button with explicit timestamp (currently auto-saves on debounce)
- Task #8 (Drive ADC) — permanently closed; `sri-projects.json` is the permanent solution

---

### Session 2 — 2026-06-15

Blueprint deployed. Backend failed first deploy (Python 3.14 / pydantic-core Rust issue — fixed in Session 3). Frontend deployed successfully on first run.

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

## Step 2 — Deploy on Render via render.yaml ✅ DONE (2026-06-18)

Blueprint: `SRI OS Command Center` (ID: `exs-d8ocekj7uimc739er4a0`)

Both services deployed and live:
- `sri-command-center` (Static) ✅ Global CDN
- `sri-command-center-api` (Python 3.11) ✅ Oregon

> **Note on initial failure:** First backend deploy failed on Python 3.14 (Render default).
> Fixed by adding `sri-command-center-api/.python-version` → `3.11.9`. See Session 3 log above.

---

## Step 3 — Set environment variables in Render dashboard

### Backend (`sri-command-center-api`)

Fill these in the Blueprint form before clicking Apply (or via service → Environment tab):

| Key | Value | Status |
|-----|-------|--------|
| `GITHUB_TOKEN` | Classic PAT, `repo` scope — generate at github.com/settings/tokens | ✅ set in dashboard |
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
