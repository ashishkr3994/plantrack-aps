# 5. Use React + TypeScript for the frontend

**Status:** Accepted

## Context
The prototype UI is a single HTML file with vanilla JavaScript and an in-memory `DB`.
It has well-defined screens (dashboard, orders, schedule, capacity, materials, reschedule,
analytics, configuration) but no component model, type safety, or real-time updates, and
state bugs from stringly-typed field names were a recurring pain.

## Decision
Use **React with TypeScript** for the production frontend, talking to the FastAPI backend.

Rationale:
- The existing screens map almost one-to-one onto React components, so the UI work ports
  rather than restarts.
- TypeScript catches the field-name/state-shape errors that bit us repeatedly in the
  vanilla build.
- Mature ecosystem for charts (e.g. Recharts/visx), tables, and real-time (WebSockets).

## Consequences
- The frontend lives in `frontend/`. The prototype `control-tower.html` is retained there
  as the reference implementation and demo until the React app surpasses it.
- The frontend consumes the backend API and a WebSocket channel for live schedule/alert
  updates; it holds no authoritative state.


