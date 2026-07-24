# Legal Agent OS Integration

Status: implementation foundation complete; live Gmail processing remains
disabled pending OAuth and shadow-mode verification.

## Dashboard contract

The combined Command Center exposes a fourth tab, `LEGAL AGENT OS`.

Read-only, sanitized endpoints:

- `GET /api/legal/dashboard`
- `GET /api/legal/matters`

Dashboard responses contain generated matter identifiers, workflow states,
counts, and connector health. They do not expose parties, message content,
attachments, work product, or legal analysis.

Protected operator endpoints:

- `POST /api/legal/intake`
- `POST /api/legal/pause`
- `POST /api/legal/resume`

Every mutation fails closed unless `LEGAL_API_TOKEN` is configured and supplied
by an authenticated server-side session or reverse proxy. The token must never
be compiled into the React application.

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

The runner starts only when `LEGAL_GMAIL_ENABLED=true`. It defaults to shadow
mode, where it observes labelled messages without writing state, copying files,
or changing labels. Live processing requires:

- Gmail OAuth with `gmail.modify`
- Drive OAuth with `drive.file`
- `LEGAL_DRIVE_MATTERS_FOLDER_ID`
- persistent `LEGAL_STATE_DB`
- completed shadow-mode verification

## Queue safety

SQLite provides transactional intake and work leases. The store enforces:

- one event per channel/source idempotency key
- one active lease per matter
- no more than four concurrent matter leases
- a global emergency pause
- generated matter identifiers in dashboard-facing responses

Google Drive remains the document and evidence system of record. SQLite is the
transactional control plane and must use persistent storage in production.
