"""apply 0006_dashboard_snapshots.sql

Revision ID: 0006_dashboard_snapshots
Revises: 0005_auth_hardening
"""
import pathlib
from alembic import op

revision = "0006_dashboard_snapshots"
down_revision = "0005_auth_hardening"
branch_labels = None
depends_on = None

SQL_DIR = pathlib.Path(__file__).resolve().parents[3] / "db" / "migrations"


def upgrade() -> None:
    sql = (SQL_DIR / "0006_dashboard_snapshots.sql").read_text()
    op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboard_snapshot")

