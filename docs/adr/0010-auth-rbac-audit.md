# 10. Authentication, role-based access, and audit (Phase 4)

**Status:** Accepted

## Context
The product moves from single-user prototype to a multi-user tool. We need to know
who is using it, restrict who can change what, and keep an accountable record of
changes — without heavyweight infrastructure for the current stage.

## Decision
- **Authentication:** username/password login issuing a signed **JWT** (HS256,
  8h default TTL). Passwords hashed with **PBKDF2-HMAC-SHA256** from the standard
  library (no external crypto dependency; avoids bcrypt version pitfalls).
- **Roles:** a single role per user — `viewer < procurement < supervisor < planner
  < admin` — checked by a `require_role` dependency using a rank hierarchy.
  - Reads are open to any authenticated context (and currently public) to keep the
    dashboard frictionless; **mutations require `planner`+**; user management and the
    audit trail require `admin`.
- **Audit:** an append-only `audit_log` table; the API records create/update/delete,
  solves, and logins with actor, entity, and a JSON detail. Actor username is
  denormalised so history survives user deletion.
- **Routing-change safety:** changing a routing's operations flags affected current
  schedules `is_stale` with a reason, surfaced in the UI so planners know to re-solve.

## Consequences
- The frontend stores the JWT (localStorage), attaches it to API calls, gates write
  UI by role, and shows a login screen + user menu.
- This is application-level auth suitable for an internal tool. Hardening for Phase 4
  deployment (refresh tokens, password reset, lockout, HTTPS/secret management, and
  moving reads behind auth if required) is follow-on work.
- Default seeded users exist for first login and MUST be changed in production.

