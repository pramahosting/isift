"""Recording storage in R2 or the database.

Revision ID: 0010_recording_storage
Revises: 0009_booking
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_recording_storage"
down_revision = "0009_booking"
branch_labels = None
depends_on = None

def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("room_recordings")}
    if "storage" not in cols: op.add_column("room_recordings", sa.Column("storage", sa.String(12), nullable=False, server_default="file"))
    if "object_key" not in cols: op.add_column("room_recordings", sa.Column("object_key", sa.Text(), nullable=True))
    if "mimetype" not in cols: op.add_column("room_recordings", sa.Column("mimetype", sa.String(60), nullable=True))
    if "data" not in cols: op.add_column("room_recordings", sa.Column("data", sa.LargeBinary(), nullable=True))

def downgrade() -> None:
    for c in ("data", "mimetype", "object_key", "storage"): op.drop_column("room_recordings", c)
