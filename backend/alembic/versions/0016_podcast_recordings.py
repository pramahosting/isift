"""HD podcast recordings kept in the cloud.

Revision ID: 0016_podcast_recordings
Revises: 0015_marketing_assets
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_podcast_recordings"
down_revision = "0015_marketing_assets"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if "podcast_recordings" in set(sa.inspect(op.get_bind()).get_table_names()): return
    dt = sa.DateTime(timezone=True)
    op.create_table("podcast_recordings", sa.Column("id", sa.String(36), primary_key=True), sa.Column("group_id", sa.String(36), nullable=False, index=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False, server_default=""), sa.Column("label", sa.String(80), nullable=False, server_default="Master"),
        sa.Column("is_master", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("has_video", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"), sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_s", sa.Integer(), nullable=False, server_default="0"), sa.Column("audio_kbps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"), sa.Column("path", sa.Text(), nullable=False, server_default=""),
        sa.Column("storage", sa.String(12), nullable=False, server_default="file"), sa.Column("object_key", sa.Text()), sa.Column("mimetype", sa.String(60)),
        sa.Column("data", sa.LargeBinary()), sa.Column("created_at", dt))

def downgrade() -> None:
    op.drop_table("podcast_recordings")
