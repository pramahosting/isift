from functools import lru_cache
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

def normalise_database_url(url: str) -> str:
    """Accept a plain PostgreSQL address as copied from Neon, Supabase, Render, etc. (postgresql://...?sslmode=require&channel_binding=require)
    and turn it into the form the async driver needs. SQLite and already-converted addresses pass through unchanged."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    u = (url or "").strip().strip('"').strip("'")
    if u.startswith("postgres://"): u = "postgresql://" + u[len("postgres://"):]
    if not u.startswith("postgresql://") and not u.startswith("postgresql+asyncpg://"): return u
    sp = urlsplit(u.replace("postgresql://", "postgresql+asyncpg://", 1))
    q = dict(parse_qsl(sp.query)); ssl = q.pop("sslmode", None); q.pop("channel_binding", None)
    if ssl in ("require", "verify-ca", "verify-full", "prefer", "allow") and "ssl" not in q: q["ssl"] = "require"
    if "-pooler" in (sp.hostname or "") or "pgbouncer" in q:                     # connection poolers cannot reuse prepared statements
        q.pop("pgbouncer", None); q.pop("statement_cache_size", None); q["prepared_statement_cache_size"] = "0"
    return urlunsplit(sp._replace(query=urlencode(q)))

def pg_connect_args(url: str) -> dict:
    """Extra driver arguments for PostgreSQL behind a connection pooler (Neon '-pooler' hosts): no server-side prepared statements."""
    return {"statement_cache_size": 0} if url.startswith("postgresql+asyncpg") and "prepared_statement_cache_size=0" in url else {}

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_env: str = "development"
    hosted: bool = False        # HOSTED=true: run as a public service (Northflank etc.) with the built-in accounts, sign-up and billing, but none of the demo extras
    app_name: str = "AI iSift"
    database_url: str = "postgresql+asyncpg://meeting:meeting@db:5432/isift"
    @field_validator("database_url", mode="after")
    @classmethod
    def _db_url(cls, v): return normalise_database_url(v)
    frontend_origin: str = "http://localhost:5173"
    auth_mode: str = "local"
    allow_local_auth: bool = True
    allow_signup: bool = True
    local_auth_secret: str = "development-only-change-before-deploy"
    settings_encryption_key: str = ""
    entra_tenant_id: str = ""
    entra_api_audience: str = ""
    entra_admin_role: str = "iSift.Admin"
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_user_id: str = ""
    graph_transcript_enabled: bool = False
    zoom_account_id: str = ""
    zoom_client_id: str = ""
    zoom_client_secret: str = ""
    google_service_account_json: str = ""
    square_environment: str = "sandbox"
    square_application_id: str = ""
    square_access_token: str = ""
    square_location_id: str = ""
    square_currency: str = "AUD"
    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_prefix: str = "isift-video"
    ms_signin_client_id: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    yahoo_oauth_client_id: str = ""
    yahoo_oauth_client_secret: str = ""
    ms_oauth_client_id: str = ""
    ms_oauth_client_secret: str = ""
    ms_oauth_tenant: str = "common"      # 'common' = any work account or personal account; or your Directory (tenant) ID for a single-company app
    google_calendar_user: str = ""
    calendar_feed_allow_private: bool = False
    local_admin_password: str = "Meeting$1"
    ice_servers: str = "stun:stun.l.google.com:19302"
    turn_username: str = ""
    turn_credential: str = ""
    room_max_people: int = 25
    room_default_access: str = "open"
    room_default_waiting: bool = True
    room_virtual_enabled: bool = True     # the virtual room (boardroom table view) is available at all
    graph_context_enabled: bool = False
    automation_user_email: str = "admin@example.test"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_transcription_model: str = "whisper-large-v3-turbo"
    automation_shared_token: str = ""
    default_timezone: str = "Australia/Sydney"
    briefing_time: str = "06:55"
    calendar_sync_minutes: int = 30
    db_pool_size: int = 10
    mock_data_enabled: bool = True
    load_mock_on_start: bool = True
    calendar_on_start: bool = True
    machine_calendar_allowed: bool = True
    machine_calendar_dir: str = ""
    mock_data_dir: str = ""
    lookback_days: int = 3
    max_briefing_words: int = 399
    admin_emails: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    error_email_to: str = ""
    audio_storage_dir: str = "/data/audio"
    audio_max_bytes: int = 25 * 1024 * 1024
    audio_retention_days: int = 0
    context_retention_days: int = 7

    @model_validator(mode="after")
    def _hosted_defaults(self):
        if self.hosted:       # a public service never loads sample data or reads a computer's calendar
            self.mock_data_enabled = False; self.load_mock_on_start = False; self.calendar_on_start = False; self.machine_calendar_allowed = False
        return self

    def hosted_problems(self) -> list[str]:
        """Things that must be fixed before a hosted service is allowed to start."""
        out = []
        if not self.hosted: return out
        if self.auth_mode == "local":
            if len(self.local_auth_secret) < 32 or self.local_auth_secret.startswith(("development-only", "replace-with")): out.append("LOCAL_AUTH_SECRET must be a random value of at least 32 characters.")
            if self.local_admin_password == "Meeting$1" or len(self.local_admin_password) < 10:
                import os
                got = os.environ.get("LOCAL_ADMIN_PASSWORD")
                seen = "the variable LOCAL_ADMIN_PASSWORD was not received by the container at all (check the name, that it is a runtime variable, and that its group is linked to this service)" if got is None else (f"the app received a value of {len(got)} characters" + (" - that is the demo password" if got == "Meeting$1" else "") + (" (a $ in the value can be shortened by some tools; use letters and digits only)" if "$" in got else ""))
                out.append("LOCAL_ADMIN_PASSWORD must be changed (at least 10 characters, not the demo password): " + seen + ".")
        if "@db:" in self.database_url or self.database_url.startswith("sqlite"): out.append("DATABASE_URL must point at a real PostgreSQL database (a Northflank PostgreSQL add-on or Neon), not the demo database.")
        if self.frontend_origin.startswith("http://localhost") or self.frontend_origin.startswith("http://127."): out.append("FRONTEND_ORIGIN must be the public https:// address of the service.")
        return out

    @property
    def is_local_demo(self) -> bool:
        return (self.app_env == "development" or self.hosted) and self.auth_mode == "local" and self.allow_local_auth

    @property
    def admins(self) -> set[str]:
        return {value.strip().lower() for value in self.admin_emails.split(",") if value.strip()}

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
