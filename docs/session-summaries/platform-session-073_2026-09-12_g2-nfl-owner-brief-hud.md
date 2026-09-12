# Platform Session 073 — G2 NFL Owner Brief HUD

Date: 2026-09-12
Status: Code complete; physical G2/R1 acceptance pending
Projects: Citadel Command G2 Plugin, SRI Command Center, GTD v2

## Outcome

Citadel Command HUD v0.4.0 now consumes `gtd.nflOwnerBrief` from the authenticated Command Center `GET /api/hud/summary` response. The GTD tab surfaces the exact owner-only NFL snapshot published after the Owners Brief email is accepted.

Each category is rendered as a separate G2 screen with ranks 1–5. R1 or temple swipe up/down moves between briefing categories. Long press refreshes the live summary. The Daily Command screen also reports the number of current NFL categories.

## Source updated

Drive source root: `SRI Agent Platform/Citadel Command G2 Plugin`

Files updated:

- `src/api.ts`: NFL snapshot/category/pick types; summary cache advanced to v3.
- `src/main.ts`: GTD NFL menu, five-pick category display, category navigation, refresh and empty-state handling.
- `src/phone.ts`: preserved pairing workflow.
- `package.json` and `package-lock.json`: version 0.4.0 build inputs.
- `app.json`: version 0.4.0 and updated network-purpose description.
- `README.md`: feature, controls, validation and release instructions.
- `tsconfig.json`: verified TypeScript configuration.

## Verification completed here

- `npm install`: passed.
- `npm run build`: passed.
- TypeScript compiler: passed.
- Vite 8.3.0 production build: passed.
- Even Hub SDK: 0.0.14.
- Production API origin remains whitelisted: `https://sri-command-center-api.onrender.com`.

## Backend dependency already deployed

The SRI Command Center accepts the post-email NFL snapshot at `POST /api/hud/gtd/nfl-owner-brief` and exposes it under `gtd.nflOwnerBrief`. GTD v2 publishes only after Resend accepts the Owners Brief. Render publisher secrets were added and both services were redeployed before this session.

## Balance of instructions — perform on the G2 development Mac

1. Allow Google Drive to finish syncing `SRI Agent Platform/Citadel Command G2 Plugin`.
2. Open the project root containing `package.json` and `app.json`; do not open `src` as the project root.
3. Run `npm install` and `npm run build`.
4. Start the plugin: `npm run dev -- --port 5174`.
5. In a second terminal, run `evenhub-simulator http://localhost:5174 --automation-port 9899` (or adjust the saved `simulate` script to port 5174 before using it).
6. Verify the menu shows **GTD NFL Picks**.
7. Open the GTD screen and confirm every briefing category displays exactly ranks 1–5, including player, direction, line and model probability.
8. Verify R1 swipe down/up moves forward/backward through categories and wraps correctly.
9. Verify press opens the selected section, double-press returns, and long-press refreshes without approving anything outside Coding Approvals.
10. Check physical line wrapping and readability on G2; report any clipped category or player names.
11. Generate the hardware QR: `evenhub qr --url "http://MAC_LAN_IP:5174"`, scan it in Even Realities Developer Center, and repeat the R1 tests on the glasses.
12. After the next Owners Brief email, long-press refresh and confirm the HUD board ID/date/category content advances to the emailed board.
13. Test offline behavior by briefly removing phone network access; confirm the last cached snapshot remains readable.
14. Package only after hardware acceptance: `npm run pack`. Expected file: `citadel-command-hud-v0.4.0.ehpk`.
15. Upload the accepted `.ehpk` to the Drive `Citadel Command G2 Plugin/releases` folder and record the acceptance result in the next session summary.

## Acceptance gate

Version 0.4.0 is build-verified but not release-accepted until simulator, physical G2, R1, live post-email refresh, and offline-cache checks pass on the configured Mac.

## Begin next session here

Resume on the Mac used for the original G2 setup. Start at Balance instruction 1 above. If a step fails, preserve the full terminal output and the visible G2 screen text for correction.
