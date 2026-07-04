# db/seeds/

- `0001_sample_data.sql` — the prototype's sample dataset translated to INSERTs:
  2 plants, a 2-shift calendar, lead-time master per family, 11 alert thresholds,
  4 routings with 19 operations, 10 products, 19 BOM lines, and 10 orders.
  Idempotent (ON CONFLICT), safe to re-run. Apply AFTER the migration.

```bash
psql "$PGURL" -f db/migrations/0001_initial_schema.sql
psql "$PGURL" -f db/seeds/0001_sample_data.sql
# or: PGURL=... ./scripts/db_init.sh
```
