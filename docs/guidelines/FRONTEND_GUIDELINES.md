# Frontend Development Guidelines (React · Vite)

The dashboard is a **port of the approved prototype** (`prototype/final-cryptopilot`)
onto real APIs — the design is decided; don't redesign, refine. Visual rules:
`UIUX_GUIDELINES.md`.

## Stack & structure

- React 19 + Vite. TypeScript for all new code (the prototype's JSX gets typed as it
  is ported). Recharts for charts, lucide-react for icons — same as the prototype.
- Structure: `src/views/` (one folder per screen), `src/components/` (shared),
  `src/api/` (typed client + WebSocket manager), `src/styles/`.
- State: server state via TanStack Query (candles, trades, settings); live state via
  the WebSocket manager feeding a small store (Zustand); local UI state stays in
  components. No Redux; no state duplication between Query and the store.
- ESLint + Prettier clean; `tsc --noEmit` in CI.

## Data & correctness rules

- **Money renders from strings.** The API returns `numeric` values as strings; the UI
  formats them (`Intl.NumberFormat`) without ever converting through `Number` for
  arithmetic. No float math on money in the frontend — the backend computes, the
  frontend displays.
- All timestamps arrive UTC; format at the component edge; label the timezone (`UTC`)
  wherever ambiguity could matter (events, decisions).
- WebSocket manager: auto-reconnect with backoff; on reconnect, re-sync via REST; the
  UI must render a truthful "stale/reconnecting" state — never show frozen numbers as
  live (the prototype's `Streaming` badge pattern).
- Optimistic updates are forbidden for trading controls — start/stop/kill reflect
  **server-confirmed** state only. A button that lies about bot state is a Major bug.

## Componentry

- Reuse the prototype's component vocabulary (`Panel`, `StatusPill`, `StatCard`,
  drawers, guarded `ConfirmationModal` with typed confirmation) — port them once into
  `components/` and use everywhere; no per-view re-implementations.
- Destructive/irreversible actions always go through the guarded modal (tone, kicker,
  optional typed word, explicit consequence list) — as prototyped.
- Accessibility: every interactive element keyboard-reachable and labelled
  (`aria-label` on icon buttons); modals trap focus and close on Escape; color never
  the only signal (pair icon/text with tone). Playwright asserts the basics.

## Error & loading states

Every data surface has explicit loading / empty / error states (the prototype's
empty-state pattern). API errors surface as toasts + inline state, never silent
console noise. The app must remain navigable with the backend down (shell + cached
data + clear degraded banners).
