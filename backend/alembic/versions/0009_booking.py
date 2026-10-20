"""Booking pages (Calendly / Cal.com style scheduling).

Revision ID: 0009_booking
Revises: 0008_accounts
"""
from alembic import op

revision = "0009_booking"
down_revision = "0008_accounts"
branch_labels = None
depends_on = None
TABLES = ["booking_types", "bookings"]

def upgrade() -> None:
    from app.models import Base
    bind = op.get_bind()
    for name in TABLES:                       # idempotent: a fresh database may already have them
        Base.metadata.tables[name].create(bind, checkfirst=True)

def downgrade() -> None:
    for name in reversed(TABLES):
        op.drop_table(name)
