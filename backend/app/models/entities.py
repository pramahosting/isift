import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Boolean, Integer, ForeignKey, UniqueConstraint, Index, JSON, LargeBinary
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, deferred

def now_utc(): return datetime.now(timezone.utc)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entra_subject: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(40), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    role_override: Mapped[str | None] = mapped_column(String(40), nullable=True)   # set by an administrator
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class LocalAccount(Base):
    """Sign-up accounts for local demo mode only (Entra mode uses Microsoft sign-in)."""
    __tablename__ = "local_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (UniqueConstraint("owner_id", "external_id", name="uq_meeting_owner_external"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500))
    organizer: Mapped[str] = mapped_column(String(320), default="")
    account: Mapped[str] = mapped_column(String(320), default="")        # the mailbox/calendar account it came from ('' = iSift itself)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    sensitivity: Mapped[str] = mapped_column(String(30), default="normal")
    join_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="scheduled")
    transcript_status: Mapped[str] = mapped_column(String(40), default="not_available")
    minutes_status: Mapped[str] = mapped_column(String(40), default="not_started")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="ready")
    language: Mapped[str] = mapped_column(String(20), default="en")
    full_text: Mapped[str] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    segments: Mapped[list["TranscriptSegment"]] = relationship(cascade="all, delete-orphan", order_by="TranscriptSegment.sequence")

class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transcript_id: Mapped[str] = mapped_column(ForeignKey("transcripts.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    start_seconds: Mapped[float | None] = mapped_column(nullable=True)
    end_seconds: Mapped[float | None] = mapped_column(nullable=True)
    speaker: Mapped[str | None] = mapped_column(String(200), nullable=True)
    text: Mapped[str] = mapped_column(Text)

class Minutes(Base):
    __tablename__ = "meeting_minutes"
    __table_args__ = (UniqueConstraint("meeting_id", "version", name="uq_minutes_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    source_job_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(30), default="draft")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    edited_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class ActionItem(Base):
    __tablename__ = "action_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(320), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(30), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(30), default="needs_review")
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Briefing(Base):
    __tablename__ = "briefings"
    __table_args__ = (UniqueConstraint("user_id", "local_date", "run_type", name="uq_briefing_idempotency"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    local_date: Mapped[str] = mapped_column(String(10))
    run_type: Mapped[str] = mapped_column(String(30), default="scheduled")
    payload: Mapped[dict] = mapped_column(JSON)
    rendered_text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    generation_status: Mapped[str] = mapped_column(String(30), default="generated")
    delivery_status: Mapped[str] = mapped_column(String(30), default="pending")
    delivery_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)
    workflow_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    failure_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "available_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class IntegrationSetting(Base):
    __tablename__ = "integration_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor: Mapped[str] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Room(Base):
    """A built-in video meeting room. The room code in the link is the secret that lets people in."""
    __tablename__ = "rooms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    meeting_id: Mapped[str | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    allow_guests: Mapped[bool] = mapped_column(Boolean, default=True)
    access: Mapped[str] = mapped_column(String(16), default="open")          # open | passcode | signed_in
    passcode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    waiting_room: Mapped[bool] = mapped_column(Boolean, default=False)
    options: Mapped[dict] = mapped_column(JSON, default=dict)             # mute_on_entry, video_off_on_entry, auto_record, invitees
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class RoomRecording(Base):
    __tablename__ = "room_recordings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    has_video: Mapped[bool] = mapped_column(Boolean, default=True)
    storage: Mapped[str] = mapped_column(String(12), default="file")            # r2 | database | file
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    mimetype: Mapped[str | None] = mapped_column(String(60), nullable=True)
    data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))   # only when stored in the database
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)   # Basic plan: cloud copy is removed after 2 days
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Contact(Base):
    """A person in someone's contact list. `user_id` is filled when the address belongs to an iSift user (so chat works)."""
    __tablename__ = "contacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    account: Mapped[str] = mapped_column(String(320), default="")        # which mailbox the contact came from ('' = kept in iSift)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ContactGroup(Base):
    __tablename__ = "contact_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    contact_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Channel(Base):
    """A chat conversation: direct (two users) or group."""
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind: Mapped[str] = mapped_column(String(10), default="direct")
    name: Mapped[str] = mapped_column(String(200), default="")
    member_ids: Mapped[list] = mapped_column(JSON, default=list)       # user ids
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[str] = mapped_column(String(36))
    sender_name: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)

class Note(Base):
    """A personal doc (text) or whiteboard (drawing strokes)."""
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="doc")       # doc | board
    title: Mapped[str] = mapped_column(String(200), default="Untitled")
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class BookingType(Base):
    """A shareable booking page (like Calendly or Cal.com): the owner's weekly hours and meeting length."""
    __tablename__ = "booking_types"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=0)
    min_notice_hours: Mapped[int] = mapped_column(Integer, default=4)
    days_ahead: Mapped[int] = mapped_column(Integer, default=30)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    availability: Mapped[dict] = mapped_column(JSON, default=dict)       # {"0": [["09:00","17:00"]], ...} 0 = Monday
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type_id: Mapped[str] = mapped_column(ForeignKey("booking_types.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)      # lets the guest cancel or reschedule
    guest_name: Mapped[str] = mapped_column(String(200))
    guest_email: Mapped[str] = mapped_column(String(320))
    guest_note: Mapped[str] = mapped_column(Text, default="")
    guest_timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="booked")           # booked | cancelled
    meeting_id: Mapped[str | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    room_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class NoteShare(Base):
    """Who may open a note or whiteboard besides its owner. kind: user (one person, by account or email), group (a contact group, live membership), link (a secret link, signed-in people only)."""
    __tablename__ = "note_shares"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id: Mapped[str] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(320), default="")
    group_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    permission: Mapped[str] = mapped_column(String(10), default="viewer")       # viewer | commenter | editor (never owner)
    token_hash: Mapped[str] = mapped_column(String(64), default="", index=True)  # sha-256 of the secret in the invitation or link; the secret itself is never stored
    via_link: Mapped[str | None] = mapped_column(String(36), nullable=True)      # set on the row made when someone opens a link
    restrict_emails: Mapped[list] = mapped_column(JSON, default=list)            # link only: if not empty, only these addresses (or people already shared with) may use it
    message: Mapped[str] = mapped_column(String(2000), default="")
    created_by: Mapped[str] = mapped_column(String(36), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class NoteComment(Base):
    __tablename__ = "note_comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id: Mapped[str] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36))
    author: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SavedSignature(Base):
    """A signature the person drew and chose to keep. Private to the owner."""
    __tablename__ = "saved_signatures"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    png: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# ---------------------------------------------------------------- webinars (registration, panelists, view-only attendees, Q&A, polls)
class Webinar(Base):
    __tablename__ = "webinars"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    host_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    room_code: Mapped[str] = mapped_column(String(40), index=True, default="")
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=60)
    tz: Mapped[str] = mapped_column(String(60), default="Australia/Sydney")
    status: Mapped[str] = mapped_column(String(12), default="scheduled")     # scheduled | ended | cancelled
    settings: Mapped[dict] = mapped_column(JSON, default=dict)                # registration, approval, questions, capacity, qa, chat, practice, reminders, recording_url
    panelists: Mapped[list] = mapped_column(JSON, default=list)               # [{email, name, token}]
    reminder_state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class WebinarRegistrant(Base):
    __tablename__ = "webinar_registrants"
    __table_args__ = (UniqueConstraint("webinar_id", "email", name="uq_webinar_registrant_email"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    webinar_id: Mapped[str] = mapped_column(ForeignKey("webinars.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200), default="")
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="approved")       # pending | approved | denied | cancelled
    token: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(10), default="self")           # self | host
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seconds: Mapped[int] = mapped_column(Integer, default=0)                  # total time watched
    joins: Mapped[int] = mapped_column(Integer, default=0)
    followup_sent: Mapped[bool] = mapped_column(Boolean, default=False)

class WebinarQuestion(Base):
    __tablename__ = "webinar_questions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    webinar_id: Mapped[str] = mapped_column(ForeignKey("webinars.id", ondelete="CASCADE"), index=True)
    asker: Mapped[str] = mapped_column(String(60), default="")                # who asked (their key, so they see their own)
    name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    text: Mapped[str] = mapped_column(Text)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    upvoters: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(12), default="open")           # open | answered | dismissed
    answer: Mapped[str] = mapped_column(Text, default="")
    answered_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class WebinarPoll(Base):
    __tablename__ = "webinar_polls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    webinar_id: Mapped[str] = mapped_column(ForeignKey("webinars.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)
    multi: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(8), default="draft")           # draft | open | closed
    share_results: Mapped[bool] = mapped_column(Boolean, default=False)      # attendees see the results
    votes: Mapped[dict] = mapped_column(JSON, default=dict)                   # voter key -> [option numbers]
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MarketingAsset(Base):
    """A video, playbook or other file the administrator keeps for sales and marketing. `public` files can be opened without signing in (the landing-page video is one)."""
    __tablename__ = "marketing_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind: Mapped[str] = mapped_column(String(12), default="document")          # video | document | other
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(String(255), default="")
    mimetype: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage: Mapped[str] = mapped_column(String(12), default="database")       # r2 | database
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    landing: Mapped[bool] = mapped_column(Boolean, default=False)              # the video behind the Watch button on the home page (only one)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
