"""Sales and marketing files kept by the administrator.

Revision ID: 0015_marketing_assets
Revises: 0014_webinars
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_marketing_assets"
down_revision = "0014_webinars"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if "marketing_assets" in set(sa.inspect(op.get_bind()).get_table_names()): return
    dt = sa.DateTime(timezone=True)
    op.create_table("marketing_assets", sa.Column("id", sa.String(36), primary_key=True), sa.Column("kind", sa.String(12), nullable=False, server_default="document"),
        sa.Column("title", sa.String(200), nullable=False, server_default=""), sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("filename", sa.String(255), nullable=False, server_default=""), sa.Column("mimetype", sa.String(120), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"), sa.Column("storage", sa.String(12), nullable=False, server_default="database"),
        sa.Column("object_key", sa.Text()), sa.Column("data", sa.LargeBinary()), sa.Column("public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("landing", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", dt), sa.Column("updated_at", dt))

def downgrade() -> None:
    op.drop_table("marketing_assets")
