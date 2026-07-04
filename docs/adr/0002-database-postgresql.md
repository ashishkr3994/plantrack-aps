# 2. Use PostgreSQL as the primary datastore

**Status:** Accepted

## Context
The prototype stores all state in the browser's `localStorage` (a single JSON blob,
~5 MB cap, single-user, wiped on clear). The product needs durable, multi-user,
queryable storage with transactional integrity and an audit trail. The data model is
strongly relational: Product → BOM → Order → Operation → Schedule → Events →
Deviations → Alerts, with derived capacity load and a reschedule log.

## Decision
Use **PostgreSQL 14+** as the primary datastore. The schema is defined in
`db/migrations/0001_initial_schema.sql` (17 tables, 10 enum types, 4 views) and has been
validated against PostgreSQL 16.

Rationale:
- The domain is relational with strong integrity requirements (foreign keys, unique
  business keys, check constraints) — a natural fit for a relational database.
- PostgreSQL adds JSONB (used for the reschedule-log `options`), partial indexes (used
  for the "one current schedule version per order" guarantee), GIN indexes, and rich
  constraint support — all of which the schema already relies on.
- Mature, open-source, no licensing cost, ubiquitous hosting and tooling.

## Consequences
- We adopt SQL migrations (`db/migrations/`) as the source of truth for schema changes.
- We will add Redis later for caching and as the async job/queue broker (not a datastore).
- Optional `citext` is intentionally avoided in the base schema so it runs on any vanilla
  PostgreSQL; case-insensitive keys can be enabled later if needed.
