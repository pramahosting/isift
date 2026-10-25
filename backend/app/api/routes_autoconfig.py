"""Auto-setup documents for isiftmail domains, so Outlook, Thunderbird, Apple Mail and phones can set a mailbox up from just the email address and password.
Public (the mail app asks before anybody has signed in) and read-only: the answers contain only server names and ports, never a password.
Outlook asks for /autodiscover/autodiscover.xml, Thunderbird and most phones ask for /mail/config-v1.1.xml."""
import re
from xml.sax.saxutils import escape
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.models import IntegrationSetting
from app.integrations import isiftmail as im

router = APIRouter(tags=["isiftmail-autoconfig"], include_in_schema=False)
ADDR = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@([A-Za-z0-9.-]{3,253})$")

async def _hosted(db: AsyncSession, dom: str) -> bool:
    """Only the isiftmail domain and domains somebody has proven they own are answered; the module being off or the server not set up means 404."""
    from app.api.routes_modules import disabled
    if not im.configured() or "isiftmail" in await disabled(db): return False
    if dom == im.domain(): return True
    rows = (await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like(f"isiftmail_dom:{dom}:%")))).scalars()
    return any((r.value or {}).get("status") == "verified" for r in rows)

def _login(local: str, dom: str) -> str: return im.principal_name(local.lower(), dom)

async def _config(emailaddress: str, db: AsyncSession) -> Response:
    m = ADDR.match((emailaddress or "").strip())
    if not m: raise HTTPException(404, "Not found")
    dom = m.group(1).lower()
    if not await _hosted(db, dom): raise HTTPException(404, "Not found")
    user = "%EMAILLOCALPART%" if dom == im.domain() else "%EMAILLOCALPART%." + dom.replace(".", "-")        # the login name the mail server uses (see principal_name)
    ih, ip, sh, sp = settings.isiftmail_imap_host.strip(), int(settings.isiftmail_imap_port or 993), settings.isiftmail_smtp_host.strip(), int(settings.isiftmail_smtp_port or 587)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<clientConfig version="1.1">
  <emailProvider id="{escape(dom)}">
    <domain>{escape(dom)}</domain>
    <displayName>{escape(dom)} email</displayName>
    <displayShortName>{escape(dom)}</displayShortName>
    <incomingServer type="imap"><hostname>{escape(ih)}</hostname><port>{ip}</port><socketType>SSL</socketType><authentication>password-cleartext</authentication><username>{user}</username></incomingServer>
    <outgoingServer type="smtp"><hostname>{escape(sh)}</hostname><port>{sp}</port><socketType>STARTTLS</socketType><authentication>password-cleartext</authentication><username>{user}</username></outgoingServer>
  </emailProvider>
</clientConfig>
"""
    return Response(xml, media_type="application/xml")

@router.get("/mail/config-v1.1.xml")
@router.get("/.well-known/autoconfig/mail/config-v1.1.xml")
async def autoconfig(emailaddress: str = "", db: AsyncSession = Depends(get_db)): return await _config(emailaddress, db)

@router.api_route("/autodiscover/autodiscover.xml", methods=["GET", "POST"])
@router.api_route("/Autodiscover/Autodiscover.xml", methods=["GET", "POST"])
async def autodiscover(request: Request, db: AsyncSession = Depends(get_db)):
    """Outlook's request: a small XML body naming the address (the older 'POX' form)."""
    body = (await request.body())[:20_000].decode("utf-8", "ignore")
    mm = re.search(r"<EMailAddress>\s*([^<\s]+)\s*</EMailAddress>", body, re.I)
    addr = mm.group(1) if mm else request.query_params.get("email", "")
    m = ADDR.match(addr.strip())
    if not m: raise HTTPException(404, "Not found")
    local, dom = addr.strip().split("@")[0], m.group(1).lower()
    if not await _hosted(db, dom): raise HTTPException(404, "Not found")
    login = _login(local, dom)
    ih, ip, sh, sp = settings.isiftmail_imap_host.strip(), int(settings.isiftmail_imap_port or 993), settings.isiftmail_smtp_host.strip(), int(settings.isiftmail_smtp_port or 587)
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
  <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
    <User><EMailAddress>{escape(addr.strip())}</EMailAddress></User>
    <Account><AccountType>email</AccountType><Action>settings</Action>
      <Protocol><Type>IMAP</Type><Server>{escape(ih)}</Server><Port>{ip}</Port><DomainRequired>off</DomainRequired><LoginName>{escape(login)}</LoginName><SPA>off</SPA><SSL>on</SSL><AuthRequired>on</AuthRequired></Protocol>
      <Protocol><Type>SMTP</Type><Server>{escape(sh)}</Server><Port>{sp}</Port><DomainRequired>off</DomainRequired><LoginName>{escape(login)}</LoginName><SPA>off</SPA><Encryption>TLS</Encryption><AuthRequired>on</AuthRequired><UsePOPAuth>off</UsePOPAuth><SMTPLast>off</SMTPLast></Protocol>
    </Account>
  </Response>
</Autodiscover>
"""
    return Response(xml, media_type="text/xml")
