"""apply 0004_solver_eligibility_setup.sql

Revision ID: 0004_solver_eligibility_setup
Revises: 0003_auth_audit_stale
"""
import pathlib
from alembic import op

revision = "0004_solver_eligibility_setup"
down_revision = "0003_auth_audit_stale"
branch_labels = None
depends_on = None

SQL_DIR = pathlib.Path(__file__).resolve().parents[3] / "db" / "migrations"


def upgrade() -> None:
    sql = (SQL_DIR / "0004_solver_eligibility_setup.sql").read_text()
    op.execute(sql)


def downgrade() -> None:
    # Downgrades for the baseline SQL migrations are not provided; restore from
    # backup instead. (Forward-only migrations for the initial schema.)
    raise NotImplementedError("downgrade not supported for baseline migration 0004_solver_eligibility_setup")
