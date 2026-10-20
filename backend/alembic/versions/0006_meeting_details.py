"""Meeting description and room options (mute on entry, camera off, auto-record, invitees).

Revision ID: 0006_meeting_details
"""
import sqlalchemy as sa
from alembic import op

revision="0006_meeting_details"
down_revision="0005_room_access"
branch_labels=None
depends_on=None

def _cols(t): return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(t)}

def upgrade():
    if "agenda" not in _cols("meetings"): op.add_column("meetings", sa.Column("agenda", sa.Text(), nullable=True))
    if "options" not in _cols("rooms"): op.add_column("rooms", sa.Column("options", sa.JSON(), nullable=True))

def downgrade():
    op.drop_column("rooms", "options"); op.drop_column("meetings", "agenda")
