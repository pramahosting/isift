"""Sharing notes and whiteboards, and comments on them.

Revision ID: 0012_note_sharing
Revises: 0011_recording_expiry
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_note_sharing"
down_revision = "0011_recording_expiry"
branch_labels = None
depends_on = None

def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    if "note_shares" not in have:
        op.create_table("note_shares",
            sa.Column("id", sa.String(36), primary_key=True), sa.Column("note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False), sa.Column("user_id", sa.String(36)), sa.Column("email", sa.String(320), nullable=False, server_default=""),
            sa.Column("group_id", sa.String(36)), sa.Column("permission", sa.String(10), nullable=False, server_default="viewer"),
            sa.Column("token_hash", sa.String(64), nullable=False, server_default=""), sa.Column("via_link", sa.String(36)), sa.Column("restrict_emails", sa.JSON()),
            sa.Column("message", sa.String(2000), nullable=False, server_default=""), sa.Column("created_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("revoked_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True)))
        op.create_index("ix_note_shares_note_id", "note_shares", ["note_id"]); op.create_index("ix_note_shares_user_id", "note_shares", ["user_id"]); op.create_index("ix_note_shares_token_hash", "note_shares", ["token_hash"])
    if "note_comments" not in have:
        op.create_table("note_comments",
            sa.Column("id", sa.String(36), primary_key=True), sa.Column("note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False), sa.Column("author", sa.String(200), nullable=False, server_default=""),
            sa.Column("text", sa.Text(), nullable=False, server_default=""), sa.Column("created_at", sa.DateTime(timezone=True)))
        op.create_index("ix_note_comments_note_id", "note_comments", ["note_id"])

def downgrade() -> None:
    op.drop_table("note_comments"); op.drop_table("note_shares")
