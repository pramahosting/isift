"""Customer chat assistant: answers questions about iSift on the public pages.

It only talks about iSift, answers from the facts below (never guesses prices or promises), and hands anything else
to a person at the support address. With a Groq key it uses the model chosen in Admin settings; without one (or if Groq
fails) it answers from the fixed answers below, so the chat icon always works. Messages are not stored.
"""
import re, time
from fastapi import APIRouter, HTTPException, Request
from app.services import groq

router = APIRouter(prefix="/api/v1", tags=["support"])
SUPPORT_EMAIL = "info@isift.au"

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
RECORDING: the host can record. Everyone sees a clear Recording banner. The recording is saved to the host's own computer by default; the host can also tick a box to keep a copy in the cloud.
On the Basic plan a cloud copy is kept for 2 days.

SCHEDULING: booking pages you share by email, like Calendly, an embeddable booking widget for other websites, and an Outlook add-in. Schedule Zoom, Teams and Google Meet meetings from one place.

AI: minutes, action items and morning briefings are drafted by AI and must be reviewed by a person. Transcripts of recordings can be produced. AI can be wrong, so check it.

PLANS (prices per user per month, shown in the website's currency; Individual and Business are paid by card through Square and renew automatically):
- Basic: free for ever. Browser video meetings with chat and screen sharing, shared docs and whiteboard, Commbox, transcripts and action items.
- Individual: about 13.59 monthly or 12.91 per month billed yearly (5% less than paying monthly) (US dollar list price; the pricing page shows the local currency). Adds AI minutes and briefings, booking pages, recording and full host controls, scheduling across Zoom, Teams and Google Meet.
- Business: about 17.59 monthly or 16.71 per month billed yearly (5% less than paying monthly). Adds a company account under one plan, Microsoft Entra single sign-on, switching modules on and off, audit log and retention rules, priority support.
You can cancel any time and keep the plan until the end of the paid period. When you change plan the difference is worked out by days; refunds are reviewed and approved by a person.

SAFETY AND LEGAL PAGES: the Terms, Privacy, Trust Center, Acceptable Use Guidelines and Legal & Compliance pages are linked in the footer of the website.
Do not claim security certifications (such as SOC 2 or ISO 27001); iSift does not state any.
"""

# fixed answers, used when Groq is not set up or does not answer
FAQ = [
    (("price", "pricing", "cost", "how much", "plan", "free", "basic", "individual", "business", "upgrade"),
     "iSift has three plans: Basic is free for ever, Individual adds AI minutes, booking pages, recording and full host controls, and Business adds a company account, single sign-on and audit controls. The Pricing page shows current prices in your currency, and you can cancel any time."),
    (("record", "recording"),
     "The host can record a meeting and everyone sees a clear Recording banner. The recording is saved to the host's own computer by default, and the host can tick a box to also keep a copy in the cloud (on the Basic plan cloud copies are kept for 2 days)."),
    (("group", "breakout", "discussion"),
     "In a large meeting the host can split people into discussion groups. People only see, hear and chat with their own group, the host can move people, send announcements and bring everyone back, and groups of 10 or fewer get a boardroom table view."),
    (("book", "schedule", "calendly", "booking", "outlook", "embed"),
     "iSift has booking pages you share by email, like Calendly, a widget you can embed on your own website, and an Outlook add-in. Booking pages are part of the Individual and Business plans."),
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

_SEEN: dict[str, list[float]] = {}
LIMIT, WINDOW = 20, 600          # 20 messages per 10 minutes per address

def _allowed(ip: str) -> bool:
    now = time.time(); hits = [t for t in _SEEN.get(ip, []) if now - t < WINDOW]
    if len(hits) >= LIMIT: _SEEN[ip] = hits; return False
    hits.append(now); _SEEN[ip] = hits
    if len(_SEEN) > 5000: _SEEN.clear()
    return True

@router.post("/support/chat")
async def support_chat(payload: dict, request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "x")).split(",")[0].strip()
    if not _allowed(ip): raise HTTPException(429, "You have sent a lot of messages. Please wait a few minutes, or email " + SUPPORT_EMAIL + ".")
    raw = payload.get("messages")
    if not isinstance(raw, list) or not raw: raise HTTPException(422, "Send at least one message.")
    msgs = [{"role": "assistant" if m.get("role") == "assistant" else "user", "content": re.sub(r"\s+", " ", str(m.get("content") or "")).strip()[:1000]} for m in raw[-10:] if isinstance(m, dict)]
    msgs = [m for m in msgs if m["content"]]
    if not msgs or msgs[-1]["role"] != "user": raise HTTPException(422, "The last message must be a question from you.")
    last = msgs[-1]["content"]
    reply = await groq.converse(KNOWLEDGE, msgs)
    return {"reply": reply or fallback(last), "ai": bool(reply)}


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
