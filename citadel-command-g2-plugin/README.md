# Citadel Command HUD

Private Even G2 command interface for SRI Command Center. Version 0.4.0 adds the daily GTD NFL Owner Brief board while preserving Builder OS, Legal OS, Event Edge, coding approval, and system-status views.

## GTD NFL board

- Source of truth: `gtd.nflOwnerBrief` from `GET /api/hud/summary`.
- The published snapshot is the exact board released after the Owners Brief email is accepted.
- The GTD screen shows one current category at a time and all five ranked picks.
- Swipe up/down with R1 or either temple to move between categories.
- Long press/release refreshes the current summary.
- If no snapshot exists, the HUD reports that the briefing has not been published.

## Controls

- Swipe up/down: move through the command menu or NFL categories.
- Press: open the selected section.
- Double-press: return to the menu; from the root, show the system exit prompt.
- Long press/release: refresh most views; approve eligible low/medium-risk coding requests after a 1.5-second hold.
- R1, left-temple, and right-temple events are identified separately.

## Run and verify

```sh
npm install
npm run build
npm run dev -- --port 5173
```

In another terminal:

```sh
npm run simulate
```

For hardware testing, use the Mac's current LAN address:

```sh
evenhub qr --url "http://MAC_LAN_IP:5173"
```

Scan the QR code from Developer Center in the Even Realities app. Pair Citadel Command if necessary, open **GTD NFL Picks**, and confirm every category contains ranks 1–5 from the latest emailed Owners Brief.

## Package

```sh
npm run pack
```

Expected artifact: `citadel-command-hud-v0.4.0.ehpk`.

## Remaining hardware acceptance

On the G2 development Mac, verify R1 swipe up/down, press, double-press, long-press refresh, display line wrapping, live refresh after the next Owners Brief email, and offline-cache behavior. Do not declare release acceptance until those checks pass on the physical G2 and R1.
