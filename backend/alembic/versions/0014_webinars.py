"""Webinars: registration, panelists, Q&A and polls.

Revision ID: 0014_webinars
Revises: 0013_saved_signatures
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_webinars"
down_revision = "0013_saved_signatures"
branch_labels = None
depends_on = None

def _have(name): return name in set(sa.inspect(op.get_bind()).get_table_names())

def upgrade() -> None:
    dt = sa.DateTime(timezone=True)
    if not _have("webinars"):
        op.create_table("webinars", sa.Column("id", sa.String(36), primary_key=True), sa.Column("host_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("room_code", sa.String(40), nullable=False, server_default=""), sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("start_at", dt, nullable=False), sa.Column("minutes", sa.Integer(), nullable=False, server_default="60"), sa.Column("tz", sa.String(60), nullable=False, server_default="Australia/Sydney"),
            sa.Column("status", sa.String(12), nullable=False, server_default="scheduled"), sa.Column("settings", sa.JSON()), sa.Column("panelists", sa.JSON()), sa.Column("reminder_state", sa.JSON()),
            sa.Column("created_at", dt), sa.Column("started_at", dt), sa.Column("ended_at", dt))
        op.create_index("ix_webinars_host_id", "webinars", ["host_id"]); op.create_index("ix_webinars_room_code", "webinars", ["room_code"]); op.create_index("ix_webinars_start_at", "webinars", ["start_at"])
    if not _have("webinar_registrants"):
        op.create_table("webinar_registrants", sa.Column("id", sa.String(36), primary_key=True), sa.Column("webinar_id", sa.String(36), sa.ForeignKey("webinars.id", ondelete="CASCADE"), nullable=False),
            sa.Column("email", sa.String(320), nullable=False), sa.Column("name", sa.String(200), nullable=False, server_default=""), sa.Column("answers", sa.JSON()),
            sa.Column("status", sa.String(12), nullable=False, server_default="approved"), sa.Column("token", sa.String(40), nullable=False), sa.Column("source", sa.String(10), nullable=False, server_default="self"),
            sa.Column("created_at", dt), sa.Column("joined_at", dt), sa.Column("left_at", dt), sa.Column("seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("joins", sa.Integer(), nullable=False, server_default="0"), sa.Column("followup_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("webinar_id", "email", name="uq_webinar_registrant_email"))
        op.create_index("ix_webinar_registrants_webinar_id", "webinar_registrants", ["webinar_id"]); op.create_index("ix_webinar_registrants_token", "webinar_registrants", ["token"], unique=True)
    if not _have("webinar_questions"):
        op.create_table("webinar_questions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("webinar_id", sa.String(36), sa.ForeignKey("webinars.id", ondelete="CASCADE"), nullable=False),
            sa.Column("asker", sa.String(60), nullable=False, server_default=""), sa.Column("name", sa.String(200), nullable=False, server_default=""), sa.Column("email", sa.String(320), nullable=False, server_default=""),
            sa.Column("text", sa.Text(), nullable=False), sa.Column("anonymous", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("upvoters", sa.JSON()),
            sa.Column("status", sa.String(12), nullable=False, server_default="open"), sa.Column("answer", sa.Text(), nullable=False, server_default=""), sa.Column("answered_by", sa.String(200), nullable=False, server_default=""), sa.Column("created_at", dt))
        op.create_index("ix_webinar_questions_webinar_id", "webinar_questions", ["webinar_id"])
    if not _have("webinar_polls"):
        op.create_table("webinar_polls", sa.Column("id", sa.String(36), primary_key=True), sa.Column("webinar_id", sa.String(36), sa.ForeignKey("webinars.id", ondelete="CASCADE"), nullable=False),
            sa.Column("question", sa.Text(), nullable=False), sa.Column("options", sa.JSON()), sa.Column("multi", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(8), nullable=False, server_default="draft"), sa.Column("share_results", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("votes", sa.JSON()),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"), sa.Column("created_at", dt))
        op.create_index("ix_webinar_polls_webinar_id", "webinar_polls", ["webinar_id"])

def downgrade() -> None:
    for t in ("webinar_polls", "webinar_questions", "webinar_registrants", "webinars"): op.drop_table(t)
