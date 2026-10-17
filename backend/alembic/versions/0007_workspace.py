"""Contacts, chat, docs and whiteboards.

Revision ID: 0007_workspace
Revises: 0006_meeting_details
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_workspace"
down_revision = "0006_meeting_details"
branch_labels = None
depends_on = None
TABLES = ["contacts", "contact_groups", "channels", "chat_messages", "notes"]

def upgrade() -> None:
    from app.models import Base
    bind = op.get_bind()
    for name in TABLES:                       # idempotent: 0001 may already have created them from the current models
        Base.metadata.tables[name].create(bind, checkfirst=True)

def downgrade() -> None:
    for name in reversed(TABLES):
        op.drop_table(name)
