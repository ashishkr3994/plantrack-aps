# 9. Frontend data layer and real-time updates

**Status:** Accepted

## Context
The Phase 3 React app needs consistent data fetching, caching, and loading/error
handling across many screens, plus live updates so planners see schedule and alert
changes without manual refresh. The async solve (ADR 0008) returns a job id the UI
must poll.

## Decision
- **TanStack Query** owns server state: caching, background refetch, loading/error
  flags, and cache invalidation. Screens stay declarative; no ad-hoc fetch state.
- A typed **API client** (`src/api/client.ts`) wraps fetch, centralises the base URL
  and error mapping (`ApiError`), and exposes one function per endpoint. Types mirror
  the backend Pydantic schemas.
- **Async-solve UX** (`useSolve`): POST /schedule/solve, then poll /schedule/jobs/{id}
  every second, exposing phase (queued/running/succeeded/failed), elapsed time, and the
  result so the UI shows progress and surfaces the outcome. On success it invalidates
  schedule-dependent queries.
- **Real-time** (`useLiveUpdates` + backend `/ws` hub): a WebSocket pushes small JSON
  events; the client invalidates the affected queries so views update live. Auto-
  reconnects with backoff and degrades gracefully to "Offline" (data still loads via
  normal queries).

## Consequences
- Adding a screen means adding a query hook + a component; caching/loading/errors come
  for free.
- The WS hub is in-process for now; multi-worker deployments need Redis pub/sub behind
  it so an event from any worker reaches all clients (Phase 4).
- Optimistic updates are available via React Query mutations where wanted; creation
  flows currently invalidate-on-success for correctness, which is the safer default.

