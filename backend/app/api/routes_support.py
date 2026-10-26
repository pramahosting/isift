"""Customer chat assistant: answers questions about iSift on the public pages.

It only talks about iSift, answers from the facts below (never guesses prices or promises), and hands anything else
to a person at the support address. With a Groq key it uses the model chosen in Admin Console; without one (or if Groq
fails) it answers from the fixed answers below, so the chat icon always works. Messages are not stored.
"""
import re, time
from fastapi import APIRouter, HTTPException, Request
from app.services import groq, kb
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.core.db import get_db

router = APIRouter(prefix="/api/v1", tags=["support"])
SUPPORT_EMAIL = "info@isift.au"
OWNER_NAME, OWNER_ABN, OWNER_SITE = "Headstart Finances Australia Pty Ltd", "88 656 265 860", "https://hsfinances.com.au"

KNOWLEDGE = f"""You are the iSift assistant on the iSift website (www.isift.au). Answer visitors' questions about iSift helpfully and briefly
(2 to 4 sentences unless asked for more). Use only the facts below. Never invent features, prices, dates, certifications or promises.
If you are not sure, or the question is about a person's own account, billing problem, legal advice or anything not listed, say so and
suggest emailing {SUPPORT_EMAIL}. Do not give legal advice. Never ask for passwords or card numbers.

WHAT iSIFT IS: a meeting assistant. Hold video meetings in the browser, pool mail, calendar and contacts in one place (Commbox), and turn meetings
into briefings, minutes and action items that a person reviews and approves ("human-reviewed by design").

VIDEO MEETINGS: start an instant meeting or join with a link or meeting ID. Guests can join without an account. Hosts can use a waiting room,
a passcode or signed-in-only access, co-hosts, mute people, switch off video, remove people, and decide whether participants may unmute or start video.
Screen sharing, group and private chat, and inviting people by email are included. Larger meetings can be split into discussion groups:
people in a group only see, hear and chat with their group, the host can move people, send announcements and bring everyone back; groups of 10 or fewer can use a boardroom table view.
RECORDING: the host can record. Everyone sees a clear Recording banner. When the meeting ends, a Basic host is offered the recording to save on their own computer (it is not stored by iSift). On paid plans the recording is stored in the cloud and a download link is emailed to the host.

WEBINARS (paid plans): schedule a webinar under Meetings, Webinars. People register on a page (with your own questions, optional approval), panelists speak like the host, attendees are view-only (the server keeps their mic, camera and screen off),
a practice session lets the host prepare before pressing Go live, attendee chat goes to the host only by default, Q&A with upvotes and anonymous questions, polls, raise hand, letting one or several attendees speak, muting and turning off video, reports (CSV) and follow-up emails.
GIVE CONTROL: share a PDF or photo through iSift (More, Share a file) and give one participant control of it so they page and scroll it for everyone; the host takes it back or stops sharing at any time. It does not control a whole screen or other programs.
WORK TOGETHER: in a meeting open More, Work together, pick a note, document, spreadsheet, presentation or whiteboard (or start a blank one) and everyone sees it live. The owner or a host lets one person at a time edit it (Let someone edit, Allow), anyone can press Ask to edit, and the owner can take editing back or stop sharing. The owner's saved file stays up to date and others can save a copy. Webinar attendees only watch.
OWN EMAIL: isiftmail gives an address on iSift or on your own domain with team mailboxes, set up on phones and in Outlook or Thunderbird from one page (Commbox).
USER MANUALS: step-by-step PDF manuals with screenshots are on the website under User manuals (meetings and sharing, webinars, booking and follow-up, mail and calendar, documents and whiteboard).

BOOKING: booking pages you share by email, like Calendly, an embeddable booking widget for other websites, and an Outlook add-in. Schedule Zoom, Teams and Google Meet meetings from one place.

AI: minutes, action items and morning briefings are drafted by AI and must be reviewed by a person. Transcripts of recordings can be produced. AI can be wrong, so check it.

@@PLANS@@

WHO RUNS iSIFT: iSift is owned and operated by {OWNER_NAME} (ABN {OWNER_ABN}), website {OWNER_SITE}. Contact: {SUPPORT_EMAIL}. Say this if asked who runs, owns or is behind iSift.

SAFETY AND LEGAL PAGES: the Terms, Privacy, Trust Center, Acceptable Use Guidelines and Legal & Compliance pages are linked in the footer of the website.
Do not claim security certifications (such as SOC 2 or ISO 27001); iSift does not state any.
"""


PLAN_NAMES = {"basic": "Basic", "individual": "Standard", "business": "Business"}

async def plan_facts(db) -> dict:
    """What each plan includes RIGHT NOW: the built-in limits with the administrator's plan changes on top, so the assistant never repeats old information."""
    from app.services import entitlements as E
    cfg = await E.plan_config(db); out = {}
    for pid in E.PLAN_IDS:
        lim = E.plan_defaults(pid); lim.update({k: v for k, v in (cfg.get(pid, {}).get("limits") or {}).items() if k in E.FIELDS})
        out[pid] = {"limits": lim, "modules_off": list(cfg.get(pid, {}).get("modules_off") or [])}
    return out

def _n(v, unit="", none="unlimited"): return none if not v else f"{v}{unit}"

def plans_text(facts: dict) -> str:
    lines = ["PLANS (these facts are generated from the live plan settings and are always current; if a feature is not listed for a plan, the plan does not include it).",
             "Prices are per host per month, shown in the website's currency. Do NOT quote an amount: point to the Pricing page for current monthly and yearly prices. Standard and Business are paid by card through Square and renew automatically."]
    for pid, f in facts.items():
        l = f["limits"]; yes, no = [], []
        (yes if l.get("commbox") else no).append("Commbox (mail, calendar and contacts in one place)")
        (yes if l.get("open_room") else no).append("open room")
        (yes if l.get("calls") else no).append("calling other iSift users (they can still receive calls)" if pid == "basic" else "calling other iSift users")
        (yes if l.get("recording") else no).append("meeting recording, " + ("stored in the cloud with a download link emailed to the host" if l.get("cloud_recording") else "saved on the host's own computer when the meeting ends"))
        (yes if l.get("multi_share") else no).append("several people sharing their screen at once")
        (yes if l.get("watch_together") else no).append("watch a video together")
        txt = (f"- {PLAN_NAMES[pid]}: up to {_n(l.get('max_participants'), ' people', 'a chosen number of people')} per meeting" if pid == "basic" else f"- {PLAN_NAMES[pid]}: 10 to 300 people per meeting (the host chooses)")
        txt += f"; meetings of {_n(l.get('meeting_minutes'), ' minutes', 'any length')}; AI summaries {_n(l.get('ai_per_month'), ' a month')}; booking pages {_n(l.get('booking_pages'))}; storage {_n(l.get('storage_mb'), ' MB')}."
        txt += " Includes: " + "; ".join(yes) + "." if yes else ""
        txt += " Does NOT include: " + "; ".join(no) + "." if no else ""
        if f["modules_off"]: txt += " Switched off on this plan: " + ", ".join(f["modules_off"]) + "."
        if pid == "business": txt += " Also: a company account under one plan, Microsoft Entra single sign-on, switching modules on and off for everyone, audit log and retention rules, team booking pages, priority support."
        lines.append(txt)
    lines.append("You can cancel any time and keep the plan until the end of the paid period. When you change plan the difference is worked out by days; refunds are reviewed and approved by a person.")
    return "\n".join(lines)

def knowledge(facts: dict) -> str:
    return KNOWLEDGE.replace("@@PLANS@@", plans_text(facts))

def feature_answer(facts: dict, text: str):
    """A plain answer straight from the live plan facts for 'which plan includes X' questions."""
    t = (text or "").lower(); table = [("commbox", "commbox", "Commbox (mail, calendar and contacts)"), ("mail", "commbox", "Commbox (mail, calendar and contacts)"), ("open room", "open_room", "the open room"), ("call", "calls", "calling other iSift users")]
    for key, field, label in table:
        if key in t:
            inc = [PLAN_NAMES[p] for p, f in facts.items() if f["limits"].get(field)]
            exc = [PLAN_NAMES[p] for p, f in facts.items() if not f["limits"].get(field)]
            if inc: return f"{label} is included in {' and '.join(inc)}" + (f", not in {' or '.join(exc)}." if exc else ".") + " The Pricing page lists every plan side by side."
    return None

# fixed answers, used when Groq is not set up or does not answer
FAQ = [
    (("price", "pricing", "cost", "how much", "plan", "free", "basic", "individual", "business", "upgrade"),
     "iSift has three plans: Basic is free for ever (browser meetings with chat, screen sharing and recording saved on the host's computer), Standard adds Commbox, unlimited AI minutes and briefings, booking pages, cloud recording and full host controls, and Business adds a company account, single sign-on and audit controls. The Pricing page shows the current plans and prices in your currency, and you can cancel any time."),
    (("record", "recording"),
     "The host can record a meeting and everyone sees a clear Recording banner. On Basic, the recording is saved to the host's own computer when the meeting ends. On paid plans it is stored in the cloud and a download link is emailed to the host."),
    (("group", "breakout", "discussion"),
     "In a large meeting the host can split people into discussion groups. People only see, hear and chat with their own group, the host can move people, send announcements and bring everyone back, and groups of 10 or fewer get a boardroom table view."),
    (("book", "schedule", "calendly", "booking", "outlook", "embed"),
     "iSift has booking pages you share by email, like Calendly, a widget you can embed on your own website, and an Outlook add-in. Booking pages are part of the Standard and Business plans."),
    (("minutes", "action item", "briefing", "transcript", "ai "),
     "iSift drafts minutes, action items and morning briefings with AI, and a person reviews and approves them before they are final. AI can make mistakes, so please check the drafts."),
    (("join", "guest", "link", "meeting id", "waiting"),
     "To join a meeting, open the invitation link or enter the meeting ID on the home page. Guests do not need an account. The host may use a waiting room or a passcode."),
    (("privacy", "data", "secure", "security", "safe", "trust"),
     "Our Privacy page and Trust Center in the footer explain what we collect, who processes it and how it is protected. For anything specific to your organisation, email " + SUPPORT_EMAIL + "."),
    (("terms", "legal", "acceptable", "compliance", "law"),
     "The Terms, Privacy, Trust Center, Acceptable Use Guidelines and Legal & Compliance pages are linked in the footer of every page. I can't give legal advice, but you can email " + SUPPORT_EMAIL + " with questions."),
    (("refund", "cancel", "billing", "invoice", "payment", "card"),
     "You can change or cancel your plan any time under Plan and billing. When you change plan the difference is worked out by days, and refunds are reviewed and approved by a person. For a problem with your own account, email " + SUPPORT_EMAIL + "."),
    (("who runs", "who owns", "owner", "company", "who is behind", "who made", "abn", "operated"),
     f"iSift is owned and operated by {OWNER_NAME} (ABN {OWNER_ABN}), {OWNER_SITE}. You can reach a person at " + SUPPORT_EMAIL + "."),
    (("contact", "support", "help", "email", "human", "person"),
     "You can reach a person at " + SUPPORT_EMAIL + ". Include the email address you signed up with and what you were trying to do."),
]

def fallback(text: str) -> str:
    t = " " + (text or "").lower() + " "
    best, hits = None, 0
    for keys, answer in FAQ:
        n = sum(1 for k in keys if k in t)
        if n > hits: best, hits = answer, n
    return best or ("I can answer questions about iSift's meetings, recording, booking pages, AI minutes and plans. For anything else, please email " + SUPPORT_EMAIL + " and a person will help.")

def _faq_hits(text: str):
    t = " " + (text or "").lower() + " "; best, hits = None, 0
    for keys, answer in FAQ:
        n = sum(1 for k in keys if k in t)
        if n > hits: best, hits = answer, n
    return best, hits

def _local_answer(last: str, ask: str, admin: bool) -> str:
    """No language model: a fixed answer when the question clearly matches one, otherwise the best page of the documentation."""
    faq, hits = _faq_hits(last)
    if faq and hits >= 2: return faq
    return kb.best_answer(last, admin) or kb.best_answer(ask, admin) or faq or fallback(last)

async def _is_admin(request: Request, db) -> bool:
    """Is the person asking a signed-in administrator? (Administration material is only for them.)"""
    h = request.headers.get("authorization") or ""
    if not h.lower().startswith("bearer "): return False
    try:
        from fastapi.security import HTTPAuthorizationCredentials
        from app.core.security import principal
        u = await principal(request, HTTPAuthorizationCredentials(scheme="Bearer", credentials=h[7:].strip()), db)
        return u.role == "admin"
    except Exception: return False

_SEEN: dict[str, list[float]] = {}
LIMIT, WINDOW = 20, 600          # 20 messages per 10 minutes per address

def _allowed(ip: str) -> bool:
    now = time.time(); hits = [t for t in _SEEN.get(ip, []) if now - t < WINDOW]
    if len(hits) >= LIMIT: _SEEN[ip] = hits; return False
    hits.append(now); _SEEN[ip] = hits
    if len(_SEEN) > 5000: _SEEN.clear()
    return True

@router.post("/support/chat")
async def support_chat(payload: dict, request: Request, db: AsyncSession = Depends(get_db)):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "x")).split(",")[0].strip()
    if not _allowed(ip): raise HTTPException(429, "You have sent a lot of messages. Please wait a few minutes, or email " + SUPPORT_EMAIL + ".")
    raw = payload.get("messages")
    if not isinstance(raw, list) or not raw: raise HTTPException(422, "Send at least one message.")
    msgs = [{"role": "assistant" if m.get("role") == "assistant" else "user", "content": re.sub(r"\s+", " ", str(m.get("content") or "")).strip()[:1000]} for m in raw[-10:] if isinstance(m, dict)]
    msgs = [m for m in msgs if m["content"]]
    if not msgs or msgs[-1]["role"] != "user": raise HTTPException(422, "The last message must be a question from you.")
    last = msgs[-1]["content"]
    facts = await plan_facts(db)
    admin = await _is_admin(request, db)
    ask = " ".join(m["content"] for m in msgs if m["role"] == "user")[-600:]          # the question and what led to it, so follow-ups still find the right pages
    ref = kb.excerpts(ask, admin)
    system = knowledge(facts) + ("\nREFERENCE EXCERPTS from the iSift manuals, website and guides. They are accurate: use them to answer in detail, and point to the User manuals section of the website for step-by-step PDFs:\n" + ref if ref else "")
    reply = await groq.converse(system, msgs)
    return {"reply": reply or feature_answer(facts, last) or _local_answer(last, ask, admin), "ai": bool(reply)}


# ---- support request / contact / feedback forms in the page footer: emailed to the support address, nothing stored ----
_FORM_SEEN: dict[str, list[float]] = {}
FORM_KINDS = {"support": "Support request", "contact": "Contact us", "feedback": "Feedback"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@router.post("/support/contact")
async def support_contact(payload: dict, request: Request):
    from app.services import signup
    from app.integrations import mail as mailer
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "x")).split(",")[0].strip()
    now = time.time(); hits = [t for t in _FORM_SEEN.get(ip, []) if now - t < 3600]
    if len(hits) >= 5: raise HTTPException(429, "You have sent several messages already. Please wait a while, or email " + SUPPORT_EMAIL + ".")
    kind = str(payload.get("kind") or "contact")
    if kind not in FORM_KINDS: raise HTTPException(422, "Choose support request, contact us or feedback.")
    name = re.sub(r"\s+", " ", str(payload.get("name") or "")).strip()[:100]
    addr = str(payload.get("email") or "").strip()[:200]
    msg = str(payload.get("message") or "").strip()[:5000]
    topic = re.sub(r"\s+", " ", str(payload.get("topic") or "")).strip()[:150]
    if payload.get("website"): return {"ok": True}                     # hidden field: only bots fill it in
    if not name: raise HTTPException(422, "Please enter your name.")
    if not _EMAIL_RE.match(addr): raise HTTPException(422, "Please enter a valid email address so we can reply.")
    if len(msg) < 5: raise HTTPException(422, "Please write your message.")
    sender = signup.app_sender()
    if not sender: raise HTTPException(503, "The form cannot send email right now. Please email " + SUPPORT_EMAIL + " instead.")
    hits.append(now); _FORM_SEEN[ip] = hits
    if len(_FORM_SEEN) > 5000: _FORM_SEEN.clear()
    label = FORM_KINDS[kind]
    subject = f"[iSift {label}] " + (topic or re.sub(r"\s+", " ", msg)[:60])
    body = f"{label}\nFrom: {name} <{addr}>\n" + (f"Subject: {topic}\n" if topic else "") + f"\n{msg}\n"
    try: await mailer.send({**sender, "reply_to": addr}, [SUPPORT_EMAIL], subject, body)
    except Exception: raise HTTPException(503, "Your message could not be sent. Please email " + SUPPORT_EMAIL + " instead.")
    return {"ok": True}
