"""apply 0002_solve_jobs.sql

Revision ID: 0002_solve_jobs
Revises: 0001_initial_schema
"""
import pathlib
from alembic import op

revision = "0002_solve_jobs"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

SQL_DIR = pathlib.Path(__file__).resolve().parents[3] / "db" / "migrations"


def upgrade() -> None:
    sql = (SQL_DIR / "0002_solve_jobs.sql").read_text()
    op.execute(sql)


def downgrade() -> None:
    # Downgrades for the baseline SQL migrations are not provided; restore from
    # backup instead. (Forward-only migrations for the initial schema.)
    raise NotImplementedError("downgrade not supported for baseline migration 0002_solve_jobs")