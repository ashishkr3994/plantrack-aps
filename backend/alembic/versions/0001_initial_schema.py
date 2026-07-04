"""apply 0001_initial_schema.sql

Revision ID: 0001_initial_schema
Revises: None
"""
import pathlib
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

SQL_DIR = pathlib.Path(__file__).resolve().parents[3] / "db" / "migrations"


def upgrade() -> None:
    sql = (SQL_DIR / "0001_initial_schema.sql").read_text()
    op.execute(sql)


def downgrade() -> None:
    # Downgrades for the baseline SQL migrations are not provided; restore from
    # backup instead. (Forward-only migrations for the initial schema.)
    raise NotImplementedError("downgrade not supported for baseline migration 0001_initial_schema")
