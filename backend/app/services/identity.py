"""Real, deliverable addresses for the host.

The built-in local administrator is stored with the placeholder admin@isift.au, which no mail server accepts. These helpers
put a real address from Admin Console in its place wherever an address is shown or emailed.
"""
from app.core.config import settings

PLACEHOLDER_ADMIN = "admin@isift.au"      # how the built-in administrator is stored; never shown
FAKE_DOMAINS = {"example.test", "example.com", "example.org", "example.net", "localhost", "invalid"}

def routable(addr: str) -> bool:
    a = (addr or "").strip().lower()
    if "@" not in a: return False
    d = a.rsplit("@", 1)[1]
    return d not in FAKE_DOMAINS and not d.endswith((".test", ".invalid", ".local", ".localhost", ".example"))

def shown_email(addr: str) -> str:
    """The address to display as organizer/host: the person's own if it is real, otherwise the app's From address, then the admin's alert address, then the app email login."""
    if routable(addr): return addr
    for cand in (settings.smtp_from, settings.error_email_to, settings.smtp_user):
        if routable(cand): return cand.strip()
    if (addr or "").strip().lower() == PLACEHOLDER_ADMIN: return (settings.admin_display_email or "info@isift.au").strip()     # nothing configured: show iSift's own admin address
    return addr

def reply_email(addr: str) -> str:
    """Where replies and host copies should go: a mailbox that exists. Prefers the admin's alert address, then the app email login."""
    if routable(addr): return addr
    for cand in (settings.error_email_to, settings.smtp_user, settings.smtp_from):
        if routable(cand): return cand.strip()
    return ""
