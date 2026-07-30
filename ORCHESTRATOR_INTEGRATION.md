# SRI Orchestrator integration

The Command Center now exposes one durable, Jeff-only task lifecycle for Codex,
Claude, OpenCode, and future approved SRI surfaces.

## Security boundary

- Browser/operator routes use Jeff's short-lived Google Workspace session.
- Worker routes use `ORCHESTRATOR_RUNNER_TOKEN`, stored only in the Command
  Center API and the trusted SRI Orchestrator runner.
- A worker token cannot approve production or external action.
- Only Jeff can call `Approve & Ship`.
- A task cannot become `completed` unless it passed through `review_ready` and
  `shipping`, and the worker filed a final material summary.

## Lifecycle

1. Jeff creates a task in Notebook → Tasks. It enters `queued`.
2. A trusted surface claims work with `POST /api/tasks/claim`. The API enforces
   the global four-task concurrency limit and returns the oldest queued tasks.
3. The worker performs safe internal work and sends
   `POST /api/tasks/{id}/review-ready`. The API files the material session
   summary in the canonical Drive folder before changing the task state.
4. Jeff reviews the linked packet and clicks `Approve & Ship`. This moves the
   task to `shipping`; it is the authorization signal for the reviewed external
   or production action only.
5. The assigned worker verifies the result and sends
   `POST /api/tasks/{id}/complete`. The API files the final material summary
   before marking the task `completed`.
6. Any unresolved failure uses `POST /api/tasks/{id}/blocked`; that path also
   files a material summary. Jeff may later requeue the task.

## Cross-surface material summaries

An approved surface may file a non-task summary with
`POST /api/session-briefs`. `materialChange` must be `true`; read-only or
conversational sessions are intentionally not added to the continuity feed.
Every summary must state the project, surface, outcome, current state, evidence,
and the exact `Begin Next Session Here` action.

The companion script at
`sri-command-center-api/scripts/orchestrator_surface_client.py` provides a
provider-neutral command-line adapter for claim, review-ready, complete,
blocked, and standalone-summary calls.
