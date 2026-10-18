"""Saved signatures for the PDF and Word editor.

Revision ID: 0013_saved_signatures
Revises: 0012_note_sharing
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_saved_signatures"
down_revision = "0012_note_sharing"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if "saved_signatures" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table("saved_signatures", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(80), nullable=False, server_default=""), sa.Column("png", sa.Text(), nullable=False, server_default=""), sa.Column("created_at", sa.DateTime(timezone=True)))
        op.create_index("ix_saved_signatures_user_id", "saved_signatures", ["user_id"])

def downgrade() -> None:
    op.drop_table("saved_signatures")
