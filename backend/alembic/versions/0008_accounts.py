"""Which account a meeting or contact came from (combined and per-account views).

Revision ID: 0008_accounts
Revises: 0007_workspace
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_accounts"
down_revision = "0007_workspace"
branch_labels = None
depends_on = None

def _add(table: str) -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}      # idempotent: a fresh database already has it
    if "account" not in cols:
        op.add_column(table, sa.Column("account", sa.String(320), nullable=False, server_default=""))

def upgrade() -> None:
    _add("meetings"); _add("contacts")

def downgrade() -> None:
    op.drop_column("contacts", "account"); op.drop_column("meetings", "account")
