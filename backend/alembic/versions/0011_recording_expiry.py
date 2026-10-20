"""Cloud copies of recordings expire on the Basic plan.

Revision ID: 0011_recording_expiry
Revises: 0010_recording_storage
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_recording_expiry"
down_revision = "0010_recording_storage"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if "expires_at" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("room_recordings")}:
        op.add_column("room_recordings", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_room_recordings_expires_at", "room_recordings", ["expires_at"])

def downgrade() -> None:
    op.drop_index("ix_room_recordings_expires_at", table_name="room_recordings"); op.drop_column("room_recordings", "expires_at")
