# Handoff: SRI OS Command Center

## Overview
SRI OS Command Center is a full-screen desktop dashboard — the single pane of glass for an
operator running a fleet of "OS plugins" (Builder OS, Legal OS, Marketing OS, etc.), each of
which spawns agents that execute tasks. The dashboard has three tabs:

1. **COMMAND CENTER** — OS registry, live agent feed, streaming terminal log, agent inspector
   with an "INTERACT" channel into a running agent session, and a 3D constellation graph of
   every OS / project / agent ("PROJECT GRAPH — LIVE DEV MAP").
2. **NOTEBOOK** — markdown notes with sidebar, tags, timestamps, live preview.
3. **MISSION CONTROL** — kanban board (PLANNING / IN PROGRESS / BLOCKED / COMPLETE) with
   drag-and-drop between lanes.

The goal of this handoff: **recreate this UI in a production codebase and wire it to real
backend data**, replacing the mock layer described below.

## About the Design Files
The files in this bundle are **design references created in HTML** — working prototypes that
show intended look and behavior, NOT production code to ship directly. They use React 18 via
in-browser Babel (`<script type="text/babel">`), which is a prototyping convenience only.

Your task is to **recreate these designs in the target codebase's existing environment** —
e.g. a Vite/Next React + TypeScript app — using its established patterns. If no app exists
yet, a sensible default stack is: **React + TypeScript + Vite**, plain CSS (the stylesheets
here port almost verbatim), **three.js** for the graph, and a small **WebSocket** client for
live streams. The component decomposition in this bundle (one file per view) is a reasonable
production structure to keep.

`tweaks-panel.jsx` is design-tool scaffolding (a live design-variation panel). **Do not port
it.** Instead, read "Layout directions" below and pick/keep the layout variants you want as a
plain settings value.

## Fidelity
**High-fidelity.** Colors, typography, spacing, copy, and interactions are final design
intent. Recreate pixel-perfectly. The only intentionally-mocked parts are the data and the
streaming behavior (random log lines on a timer) — replace those with real data per the
Integration Contract (`INTEGRATION.md`).

## Files
| File | What it is |
|---|---|
| `SRI OS Command Center.html` | Entry point: font + library loads, script order |
| `styles.css` | Global HUD theme: tokens, header, panels, buttons, badges, scrollbars, scanlines |
| `layout.css` | Per-view layout: command-center grid (3 layout directions), graph overlays, notebook, kanban |
| `data.jsx` | **The entire mock data layer** — every entity the backend must supply |
| `app.jsx` | Shell: header, tab nav, clock, notification bell, footer, keyboard shortcuts, tweaks |
| `command-center.jsx` | Tab 1: registry, agent feed, live log, inspector |
| `graph.jsx` | 3D constellation graph (three.js r134, UMD global) |
| `notebook.jsx` | Tab 2: notes + minimal markdown renderer |
| `mission-control.jsx` | Tab 3: kanban with HTML5 drag-and-drop |
| `tweaks-panel.jsx` | Design-tool scaffolding — do not port |
| `INTEGRATION.md` | **Backend / live-data contract** — entities, endpoints, WS events, mapping to UI |

## Design Tokens
Strict two-tone: deep navy + gold. White only for secondary body text. The single allowed
exception is the error/blocked tint (`--err`).

```css
--bg:        #0A1628;  /* app background */
--bg-deep:   #060F1E;  /* terminal log, graph background, footer */
--panel:     #0D2050;  /* panel gradient top */
--panel-2:   #0b1a40;  /* panel gradient bottom */
--border:    #1A3A7A;  /* all borders/accents */
--border-soft:#152c5e; /* internal dividers */
--gold:      #FFD700;  /* primary text, buttons, icons, highlights */
--gold-dim:  #b9a23a;  /* secondary gold (timers, complete states) */
--gold-soft: rgba(255,215,0,.12); /* gold fills/hover washes */
--white:     #FFFFFF;  /* secondary body text and labels only */
--muted:     #8fa6cf;  /* tertiary text */
--muted-2:   #5d74a0;  /* faintest text / idle */
--err:       #ff6a4d;  /* ERROR / BLOCKED only */
--glow:      1;        /* 0–1.4 multiplier scaling every glow/shadow */
```

**Typography (all monospace):**
- Display/headings: `"Share Tech Mono"` (Google Fonts) — panel titles, brand, clock, agent name in inspector. Letter-spacing 2–2.5px, sizes 12–20px.
- UI/body/logs: `"JetBrains Mono"` 400/500/700 — everything else. Body 11–12.5px, labels 9–10px with 1–2px letter-spacing, log text 11.5px / line-height 1.55.

**Spacing & shape:** 14px gutters between panels; panel padding 10–13px; border-radius 3px
(buttons/inputs) to 5px (panels); 1px borders everywhere. Buttons: navy fill, gold border,
gold text, gold glow on hover (`box-shadow: 0 0 14px rgba(255,215,0,.35)`). Scrollbars: 8px,
gold thumb on `--bg-deep` track. Full-viewport scanline overlay (3px repeating gradient,
`mix-blend-mode: screen`) and bottom vignette — both scale with `--glow`.

**Status colors:** ACTIVE/RUNNING = gold badge with pulsing dot · IDLE = muted blue ·
ERROR/BLOCKED = `--err` with pulsing dot · COMPLETE = `--gold-dim`.

## Screens / Views

### Shell (all tabs)
- **Header (64px):** shield+orbit SVG mark · brand title in Share Tech Mono 20px gold with
  glow, sub-line "CENTRAL OPS · v2.6" · system-health pill (gold pulsing dot, "ALL NOMINAL"
  or red dot "DEGRADED · n FAULT" — derived from OS error count) · tab nav
  `01 COMMAND CENTER / 02 NOTEBOOK / 03 MISSION CONTROL` (active = gold + 2px gold underline
  with glow; inactive = muted) · right: live clock (HH:MM:SS + date) and a gold notification
  bell with count badge that opens a "SYSTEM EVENTS" dropdown.
- **Footer (30px):** keyboard hints (`1/2/3` switch view, `\` toggle sidebar, `G` graph
  fullscreen, `Esc` close), link-latency readout, live agent count.
- **Sidebar collapse toggle:** 16×54px tab on the left edge, collapses the registry/notes sidebar.
- Tab switching is instant (no reload), entering view slides up 10px over 0.3s ease.
  **Important:** animate transform only — never animate opacity for view visibility (a paused
  animation must not hide content).

### Tab 1 — Command Center
Grid layout, three directions (a user/setting choice; "classic" is default):
- **classic:** columns `290px 1fr 330px`, rows `1.05fr .95fr`; registry | feed+log | inspector, graph spans bottom-left/center, inspector full height.
- **focus:** `220px 1fr 340px`; slim registry rail (no meta line, no header count), taller feed/log, graph spans full width below.
- **graph:** `270px 1fr 320px`, rows `1.45fr .55fr`; the graph is center stage between registry and inspector; bottom strip = running agents (420px) + log side-by-side.

Panels:
- **OS REGISTRY:** vertical card list. Card = OS name (gold, truncates), status badge,
  meta line ("N AGENTS RUNNING" / "NO ACTIVE AGENTS"), two equal buttons `▶ LAUNCH`
  `⚙ CONFIGURE`. Hover: gold border + glow. Card highlights when the selected agent belongs to it.
- **RUNNING AGENTS:** rows = agent name, parent OS, RUNNING/ERROR badge, task (single line,
  ellipsis), elapsed `MM:SS` ticking every second, `■ STOP` (red-tinted). Click selects;
  selected row gets a 2px gold left rail.
- **AGENT LOG — LIVE OUTPUT:** terminal box, `--bg-deep` background, gold monospace text with
  subtle text-shadow, auto-scrolls to bottom, blinking block cursor. Line styling by prefix:
  `✗/ERROR` red, `⚠` amber, `✓`/heartbeats dim gold. Shows the selected agent's stream.
- **AGENT INSPECTOR:** agent name (Share Tech Mono 16px), status badge + parent OS + elapsed,
  CURRENT TASK paragraph, SKILL/COMMAND chip (e.g. `builder.scaffold_route`), INPUTS PASSED
  (`›` list), OUTPUTS RETURNED (`✓` list, `✗` red for errors), SESSION INTERACTIONS (messages
  sent), button row `≣ VIEW FULL TRANSCRIPT · ❚❚ PAUSE · ■ STOP · ⟲ RESTART`, and the
  **INTERACT** input + gold SEND button at the bottom. Sending appends `‹ operator: <msg>` to
  the log and an acknowledgement line. Selecting a non-agent graph node shows a node card
  (status, parent OS, connected skills, OPEN / VIEW LOG / MARK COMPLETE).
- **PROJECT GRAPH — LIVE DEV MAP:** see graph.jsx. Black `#060F1E` space with faint gold
  star-field; nodes are additive-blended glow sprites — hubs largest (label always visible),
  projects medium, agents small (fast pulse while running), skills smallest; sized by
  connection count. Links are thin `#1A3A7A` lines with bright pulse sprites traveling along
  active links. Status: active = bright yellow-white pulse, blocked = amber/red tint,
  complete = muted gray-gold, drifted ~35% outward from cluster. Auto-rotates when idle
  (pauses on interaction), drag to rotate, scroll to zoom (clamped), hover = gold-bordered
  tooltip (name, kind, OS, status, last active), click = select → inspector, right-click =
  context menu `Open OS / View Log / Add Connection / Mark Complete`. Header shows live
  node/link counts; controls: reset view `⟲`, fullscreen `⤢` (also keyboard `G`); legend
  bottom-left; hint line bottom-right.

### Tab 2 — Notebook
`250px` sidebar + editor. Sidebar: gold `+ NEW NOTE` (solid gold button, dark text), note
cards (title gold, `#tag` chip, timestamp). Editor: title input (Share Tech Mono 17px,
borderless) + tag input in a toolbar, then a 50/50 split — raw markdown textarea
(`--bg-deep`) on the left, rendered preview on the right. Markdown support: `#`/`##`
headings, bold→gold, italic→pale gold, `code` chips, `>` blockquotes, lists, `- [ ]`/`- [x]`
checklists (gold ✓ / muted ▢). Edits update title/tag/preview live.

### Tab 3 — Mission Control
Header row: "MISSION CONTROL" title, live "N IN FLIGHT" and "N BLOCKED" badges, gold
`+ ADD PROJECT` on the right. Board: 4 equal lanes, each a panel with header (lane name —
red for BLOCKED — and count chip) and scrollable card stack. Card: project name (gold),
priority chip (HIGH gold / MED muted / LOW faint), OS name, footer with owner (initials in a
gold-ringed avatar circle) and last-update time, separated by a hairline. Cards drag between
lanes (HTML5 DnD): dragged card dims to 40%, target lane gets a dashed gold outline; drop
updates lane + timestamp ("just now").

## Interactions & Behavior
- Keyboard: `1/2/3` tabs · `\` sidebar collapse · `G` graph fullscreen (command tab) · `Esc`
  closes fullscreen/dropdown. Ignored while typing in inputs.
- Agent elapsed timers tick 1s; log lines stream in every ~1.1–1.8s per running agent.
- ERROR agents: log stops at the error lines, no cursor animation, outputs show `✗` line.
- All hover states: gold border + outer glow (see `.btn:hover`, `.os-card:hover`, `.mc-card:hover`).
- Graph intro: nodes scale in with a slight stagger on mount.
- `prefers-reduced-motion` is not yet wired — respect it in production (disable pulses,
  auto-rotation, scanlines).

## State Management
Current prototype state (all client-side) and what should own it in production:
- `tab`, `collapsed`, `graphFs`, `notifOpen` — local UI state.
- `selection` (agent | graph node | none) — shared between feed, graph, inspector.
- `elapsed` per agent — derive from agent `startedAt` server field instead of a client ticker.
- Log buffers per agent (capped at ~80 lines in the prototype) — replace with WS stream + ring buffer.
- Notes, projects/lanes — server CRUD (see INTEGRATION.md).
- Layout direction (`classic/focus/graph`), glow, scanlines, spin speed, gold tone — user
  preferences; persist per user.

## Assets
No raster assets. The brand mark (shield + orbit) and bell are inline SVGs in `app.jsx`.
Fonts from Google Fonts: Share Tech Mono, JetBrains Mono. three.js r134 (UMD build) for the graph.

## Backend & Live Data
See **`INTEGRATION.md`** — it maps every UI region to the entities, REST endpoints, and
WebSocket events the backend needs to provide, and points at the exact mock seam
(`data.jsx`) to replace.

## Screenshots
Annotated captures in `screenshots/` (gold tags map UI regions to the endpoints/WS events in `INTEGRATION.md`):

| File | Shows |
|---|---|
| `01-command-center-classic.png` | Tab 1, default **classic** layout — numbered tags 1–7: registry, agent feed, live log, inspector + INTERACT, project graph, health pill, event bell |
| `02-notebook.png` | Tab 2 — notes sidebar, markdown source, live preview, title/tag toolbar |
| `03-mission-control.png` | Tab 3 — kanban lanes, card anatomy, add-project / drag-drop endpoints |
| `04-layout-focus.png` | Command Center **focus** layout direction |
| `05-layout-graph-first.png` | Command Center **graph-first** layout direction |

Note: timestamps, elapsed values, and graph rotation differ between captures — the prototype is live. Tags are screenshot overlays, not part of the UI.
