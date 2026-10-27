from datetime import datetime, timezone
import httpx
import re
from html import unescape
from app.core.config import settings

GRAPH="https://graph.microsoft.com/v1.0"

class GraphUnavailable(RuntimeError): pass

def mailbox_for(email: str) -> str | None:
    """Each person is read from their own mailbox. The built-in demo admin uses the configured calendar user."""
    if email.lower() == "admin@isift.au": return settings.graph_user_id or None
    return email or None

class GraphClient:
    async def _token(self) -> str:
        if not all([settings.entra_tenant_id, settings.graph_client_id, settings.graph_client_secret]):
            raise GraphUnavailable("Your calendar isn't connected yet. Connect Outlook or Google in Connections to see your meetings here. If you can't connect it yourself, ask your administrator to connect it.")
        url=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
        data={"client_id":settings.graph_client_id,"client_secret":settings.graph_client_secret,"grant_type":"client_credentials","scope":"https://graph.microsoft.com/.default"}
        async with httpx.AsyncClient(timeout=15) as c:
            r=await c.post(url,data=data)
            if r.status_code>=400:
                try: j=r.json(); why=str(j.get("error_description") or j.get("error") or "").split("\r\n")[0].split("\n")[0][:160]
                except Exception: why=""
                hint=" The saved client secret is probably wrong or has expired: an administrator should create a new client secret in Microsoft Entra (use its Value, not its Secret ID) and save it in Admin Console." if r.status_code in (400,401) and ("secret" in why.lower() or "AADSTS7000215" in why or "AADSTS7000222" in why or not why) else ""
                raise GraphUnavailable(f"Microsoft token request failed ({r.status_code}){': '+why if why else ''}.{hint}")
            return r.json()["access_token"]

    async def get(self, path: str, params: dict | None=None):
        token=await self._token(); url=path if path.startswith("https://") else GRAPH+path
        async with httpx.AsyncClient(timeout=25) as c:
            r=await c.get(url,params=params,headers={"Authorization":f"Bearer {token}","Prefer":"outlook.timezone=\"UTC\""})
            if r.status_code==429: raise GraphUnavailable("Microsoft Graph is throttling requests")
            if r.status_code>=400: raise GraphUnavailable(f"Microsoft Graph request failed ({r.status_code})")
            return r.json()

    async def create_teams_meeting(self, mailbox: str, subject: str, start: datetime, end: datetime, body: str = "") -> dict:
        """Creates a calendar event with a Teams meeting in that mailbox (needs the Calendars.ReadWrite application permission)."""
        token=await self._token(); fmt=lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        payload={"subject":subject[:250],"body":{"contentType":"text","content":body[:2000]},"start":{"dateTime":fmt(start),"timeZone":"UTC"},"end":{"dateTime":fmt(end),"timeZone":"UTC"},"isOnlineMeeting":True,"onlineMeetingProvider":"teamsForBusiness"}
        async with httpx.AsyncClient(timeout=25) as c:
            r=await c.post(f"{GRAPH}/users/{mailbox}/events",json=payload,headers={"Authorization":f"Bearer {token}"})
        if r.status_code in (401,403): raise GraphUnavailable("Microsoft refused the request. The app registration needs the Calendars.ReadWrite application permission with admin consent.")
        if r.status_code==404: raise GraphUnavailable(f"Microsoft could not find the mailbox {mailbox}.")
        if r.status_code>=400: raise GraphUnavailable(f"Microsoft could not create the Teams meeting ({r.status_code}).")
        j=r.json(); url=(j.get("onlineMeeting") or {}).get("joinUrl")
        if not url: raise GraphUnavailable("Microsoft created the event but did not return a Teams link. Check that Teams is licensed for this user.")
        return {"id":j["id"],"join_url":url}

    async def delete_event(self, mailbox: str, event_id: str) -> None:
        token=await self._token()
        async with httpx.AsyncClient(timeout=25) as c:
            await c.delete(f"{GRAPH}/users/{mailbox}/events/{event_id}",headers={"Authorization":f"Bearer {token}"})

    async def calendar(self,start: datetime,end: datetime,mailbox: str|None=None) -> list[dict]:
        mailbox=mailbox or settings.graph_user_id
        if not mailbox: raise GraphUnavailable("Your calendar isn't connected yet. Connect Outlook or Google in Connections to see your meetings here. If you can't connect it yourself, ask your administrator to connect it.")
        url=f"{GRAPH}/users/{mailbox}/calendarView"
        params={"startDateTime":start.astimezone(timezone.utc).isoformat(),"endDateTime":end.astimezone(timezone.utc).isoformat(),"$top":"100","$select":"id,subject,organizer,start,end,isCancelled,isAllDay,sensitivity,responseStatus,onlineMeeting,onlineMeetingUrl,webLink"}
        events=[]
        while url:
            data=await self.get(url,params); events.extend(data.get("value",[])); url=data.get("@odata.nextLink"); params=None
        return events

    async def transcript_text(self, meeting_id: str, online_meeting_id: str, transcript_id: str, mailbox: str|None=None) -> str:
        if not settings.graph_transcript_enabled: raise GraphUnavailable("Teams transcript access is disabled")
        user=mailbox or settings.graph_user_id
        path=f"/users/{user}/onlineMeetings/{online_meeting_id}/transcripts/{transcript_id}/content"
        token=await self._token()
        async with httpx.AsyncClient(timeout=30) as c:
            r=await c.get(GRAPH+path,headers={"Authorization":f"Bearer {token}","Accept":"text/vtt"})
            if r.status_code==404: raise GraphUnavailable("Official Teams transcript is not available")
            if r.status_code>=400: raise GraphUnavailable(f"Transcript request failed ({r.status_code})")
            return r.text

    async def transcript_for_calendar_event(self, event_id: str, mailbox: str|None=None) -> tuple[str, str]:
        """Return (transcript id, VTT content) for an event only when Graph confirms it exists."""
        if not settings.graph_transcript_enabled: raise GraphUnavailable("Teams transcript access is disabled")
        user=mailbox or settings.graph_user_id
        event=await self.get(f"/users/{user}/events/{event_id}",{"$select":"onlineMeeting,onlineMeetingUrl"})
        join_url=((event.get("onlineMeeting") or {}).get("joinUrl") or event.get("onlineMeetingUrl"))
        if not join_url: raise GraphUnavailable("Calendar event does not reference an online meeting")
        escaped=join_url.replace("'","''")
        meetings=await self.get(f"/users/{user}/onlineMeetings",{"$filter":f"JoinWebUrl eq '{escaped}'","$select":"id"})
        candidates=meetings.get("value",[])
        if not candidates: raise GraphUnavailable("No supported online meeting matched the calendar event")
        online_id=candidates[0]["id"]
        transcripts=await self.get(f"/users/{user}/onlineMeetings/{online_id}/transcripts")
        items=transcripts.get("value",[])
        if not items: raise GraphUnavailable("Official Teams transcript is not available yet")
        transcript_id=items[0]["id"]
        return transcript_id, await self.transcript_text(event_id,online_id,transcript_id,mailbox)

    async def related_context(self, events: list[dict], since: datetime, mailbox: str|None=None) -> dict[str,list[str]]:
        """Fetch bounded recent message previews, match in memory, and do not persist them."""
        if not settings.graph_context_enabled: return {}
        user=mailbox or settings.graph_user_id
        since_iso=since.astimezone(timezone.utc).isoformat()
        mail=await self.get(f"/users/{user}/messages",{"$filter":f"receivedDateTime ge {since_iso}","$select":"subject,bodyPreview,receivedDateTime,from,webLink","$top":"100","$orderby":"receivedDateTime desc"})
        chats=await self.get(f"/users/{user}/chats/getAllMessages",{"$filter":f"lastModifiedDateTime ge {since_iso}","$top":"100"})
        sources=[]
        for item in mail.get("value",[]):
            source=" ".join([item.get("subject", ""),item.get("bodyPreview", ""),((item.get("from") or {}).get("emailAddress") or {}).get("address", "")])
            sources.append(source)
        for item in chats.get("value",[]):
            source=re.sub(r"<[^>]+>"," ",item.get("body",{}).get("content", ""))
            sources.append(unescape(source))
        result={}
        for event in events:
            title=(event.get("subject") or "").lower()
            words={w for w in re.findall(r"[a-z0-9]{4,}",title) if w not in {"meeting","catchup","catch-up"}}
            matched=[]
            for source in sources:
                clean=" ".join(source.split())
                if words and any(w in clean.lower() for w in words): matched.append(clean[:350])
                if len(matched)>=3: break
            result[event.get("id","")]=matched
        return result

graph=GraphClient()


# ---- sign in as the person (delegated token from the browser popup) ----
async def _me_get(token: str, path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.get(path if path.startswith("https://") else GRAPH + path, params=params, headers={"Authorization": f"Bearer {token}", "Prefer": 'outlook.timezone="UTC"'})
    if r.status_code in (401, 403): raise GraphUnavailable("Microsoft did not accept the sign-in. Sign in again and accept the permissions (read your calendar and mail).")
    if r.status_code == 429: raise GraphUnavailable("Microsoft is throttling requests. Try again in a minute.")
    if r.status_code >= 400: raise GraphUnavailable(f"Microsoft request failed ({r.status_code}).")
    return r.json()

async def me_profile(token: str) -> dict:
    j = await _me_get(token, "/me", {"$select": "displayName,mail,userPrincipalName"})
    return {"name": j.get("displayName") or "", "email": (j.get("mail") or j.get("userPrincipalName") or "").lower()}

async def me_calendar(token: str, start: datetime, end: datetime) -> list[dict]:
    url = f"{GRAPH}/me/calendarView"
    params = {"startDateTime": start.astimezone(timezone.utc).isoformat(), "endDateTime": end.astimezone(timezone.utc).isoformat(), "$top": "100",
              "$select": "id,subject,organizer,start,end,isCancelled,isAllDay,sensitivity,showAs,onlineMeeting,onlineMeetingUrl,webLink,bodyPreview"}
    out = []
    while url and len(out) < 1000:
        j = await _me_get(token, url, params); out.extend(j.get("value", [])); url = j.get("@odata.nextLink"); params = None
    return out

async def me_mail(token: str, top: int = 50) -> list[dict]:
    j = await _me_get(token, "/me/messages", {"$top": str(top), "$orderby": "receivedDateTime desc", "$select": "subject,from,receivedDateTime,bodyPreview,isRead"})
    return [{"subject": (m.get("subject") or "(no subject)")[:200], "from": ((m.get("from") or {}).get("emailAddress") or {}).get("name") or ((m.get("from") or {}).get("emailAddress") or {}).get("address") or "",
             "at": m.get("receivedDateTime"), "preview": (m.get("bodyPreview") or "")[:240], "read": bool(m.get("isRead"))} for m in j.get("value", [])]


async def me_contacts(token: str, top: int = 500) -> list[dict]:
    """The person's Outlook contacts (name, first email, phone). Needs the Contacts.Read permission."""
    j = await _me_get(token, "/me/contacts", {"$top": str(min(top, 999)), "$select": "displayName,emailAddresses,mobilePhone,businessPhones,homePhones"})
    out = []
    for c in j.get("value", []):
        ems = [e.get("address") for e in (c.get("emailAddresses") or []) if e.get("address")]
        phone = c.get("mobilePhone") or next(iter(c.get("businessPhones") or c.get("homePhones") or []), "") or ""
        name = c.get("displayName") or (ems[0] if ems else "")
        if name: out.append({"name": name, "email": ems[0] if ems else "", "phone": phone})
    return out
