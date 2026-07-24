# Legal Agent OS Integration

Status: authenticated control foundation complete; live Gmail processing
remains disabled pending production secrets, persistent storage, and
shadow-mode verification.

## Dashboard contract

The combined Command Center exposes a fourth tab, `LEGAL AGENT OS`.

Read-only, sanitized endpoints:

- `GET /api/legal/dashboard`
- `GET /api/legal/matters`
- `GET /api/legal/assignments`
- `GET /api/notes`

Dashboard responses contain generated matter identifiers, workflow states,
counts, and connector health. They do not expose parties, message content,
attachments, work product, or legal analysis.

Protected operator endpoints:

- `POST /api/legal/auth/google`
- `GET /api/legal/auth/session`
- `POST /api/legal/intake`
- `POST /api/legal/assignments/start`
- `POST /api/legal/assignments/{lease_id}/complete`
- `POST /api/legal/pause`
- `POST /api/legal/resume`

Google Identity Services supplies a signed ID token to the API. The API verifies
Google's signature, audience, expiry, Workspace domain, verified email, and the
exact authorized account (`jeff@sri-intel.com`). It then issues a short-lived,
HMAC-signed Legal OS session stored only for the browser session.

Every mutation fails closed unless either that Jeff-only session or the
server-to-server `LEGAL_API_TOKEN` is valid. No secret is compiled into the
React application. Manual intake additionally remains blocked until persistent
state and `LEGAL_MANUAL_INTAKE_ENABLED=true` are both configured.

## Google configuration

Use the existing `legal-agent-os` Google Cloud project:

1. Configure the OAuth consent screen as an internal SRI Workspace app.
2. Create a Web OAuth client for dashboard sign-in.
3. Add these authorized JavaScript origins:
   - `https://sri-command-center.onrender.com`
   - `http://localhost:5173`
4. Store its public client ID as `LEGAL_GOOGLE_CLIENT_ID` on the API.
5. Generate a random secret of at least 32 characters and store it only as
   `LEGAL_SESSION_SECRET` on the API.
6. Create a Desktop OAuth client for the background Gmail/Drive grant.
7. Enable Gmail API and Drive API in the project.
8. Run `scripts/authorize_legal_google.py --client-secrets <downloaded-json>`.
9. Store the resulting ignored file contents only in the API secret
   `LEGAL_GOOGLE_USER_TOKEN_JSON`.

The two-client design keeps dashboard sign-in separate from the offline
Gmail/Drive grant. Neither client secret nor refresh token belongs in GitHub or
the frontend.

## Intake runner

The Gmail runner:

1. Reads only messages carrying `LegalOS/Intake`.
2. Applies a deterministic idempotency key.
3. Matches revisions by Gmail thread, explicit matter ID, then case number.
4. Creates or updates a sanitized matter record.
5. Copies the source message and allowlisted attachments to the canonical Drive
   matter workspace.
6. Moves the Gmail message to `LegalOS/Processed` only after Drive persistence
   succeeds.
7. Routes unsupported attachment types to `LegalOS/NeedsReview`.
8. Routes processing failures to `LegalOS/Error`.
9. Never sends email or delivers work product.

The runner starts only when `LEGAL_GMAIL_ENABLED=true` and every required safety
condition is present. It defaults to shadow mode, where it observes labelled
messages without writing state, copying files, or changing labels. Live
processing requires:

- Gmail OAuth with `gmail.modify`
- Drive OAuth with `drive.file`
- `LEGAL_DRIVE_MATTERS_FOLDER_ID`
- persistent `LEGAL_STATE_DB`
- completed shadow-mode verification

Production activation sequence:

1. Attach encrypted persistent storage and set
   `LEGAL_STATE_DB=/var/data/legal-os-state.db`.
2. Set `LEGAL_STATE_PERSISTENT=true`.
3. Add the Web client ID, session secret, and authorized-user grant as API
   environment secrets.
4. Set the canonical Matters folder ID.
5. Set `LEGAL_GMAIL_ENABLED=true` while leaving
   `LEGAL_GMAIL_SHADOW_MODE=true`.
6. Verify labelled-message counts and logs without changing Gmail or Drive.
7. Only after the shadow run passes, set `LEGAL_GMAIL_SHADOW_MODE=false`.
8. Enable `LEGAL_MANUAL_INTAKE_ENABLED=true` only after manual intake is also
   Drive-first.

## Queue safety

SQLite provides transactional intake and work leases. The store enforces:

- one event per channel/source idempotency key
- one active lease per matter
- no more than four concurrent matter leases
- a global emergency pause
- generated matter identifiers in dashboard-facing responses

Google Drive remains the document and evidence system of record. SQLite is the
transactional control plane and must use persistent storage in production.
On Render, mount a paid-service persistent disk at `/var/data`; only paths under
that mount survive deploys and restarts. The disk should be attached through the
Render service settings after confirming the storage cost.

## Dashboard activity

The protected assignment lifecycle endpoints are the worker-facing boundary.
Starting an assignment acquires one of the four work slots and transactionally
creates both a running assignment record and a `legal-os` activity note.
Completing that lease transactionally closes the assignment, advances the matter,
and creates the completion note.

The Command Center and Notebook refresh these public-safe records every five
seconds. Activity notes are read-only in the Notebook and include only generated
matter and assignment identifiers, workflow state, and timestamps. Party names,
source communications, legal analysis, and work product never enter these
dashboard records.
