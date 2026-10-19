import os, uuid, re, logging, smtplib, secrets
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import jwt
from app.core.config import settings
from app.core.db import get_db
from app.core.security import principal, require_admin, hash_password, verify_password
from app.core import runtime_settings as rs
from app.models import User, Meeting, Transcript, TranscriptSegment, Minutes, ActionItem, Briefing, WorkflowRun, Job, IntegrationSetting, AuditLog, LocalAccount
from app.schemas.contracts import UserOut, MeetingOut, MinutesUpdate, ActionUpdate, SettingsUpdate, DeliveryCallback
from app.services.briefings import build_preview
from app.services import calendar_sync as cal
from app.services.llm import ai_configured
from app.integrations.graph import mailbox_for
from app.integrations.graph import GraphUnavailable, graph
from app.demo import seed_demo

api=APIRouter(prefix="/api/v1")
log=logging.getLogger("isift")

def _local_token(sub:str,email:str,name:str)->dict:
    token=jwt.encode({"sub":sub,"oid":sub,"preferred_username":email,"name":name,"roles":[],"aud":"isift-api","exp":datetime.now(timezone.utc)+timedelta(hours=8)},settings.local_auth_secret,algorithm="HS256")
    return {"access_token":token,"token_type":"bearer","expires_in":28800}

@api.get("/auth/options")
async def auth_options():
    return {"local":settings.is_local_demo,"signup":settings.is_local_demo and settings.allow_signup}

@api.post("/auth/local-login")
async def local_login(payload:dict,db:AsyncSession=Depends(get_db)):
    if not settings.is_local_demo: raise HTTPException(404,"Not found")
    username=str(payload.get("username","")).strip(); password=str(payload.get("password",""))
    if username.lower()=="admin":
        from app.services import store
        saved=await store.get(db,"admin_password",{})      # set from My account > Password; otherwise the LOCAL_ADMIN_PASSWORD setting
        if (verify_password(password,saved["hash"]) if saved.get("hash") else secrets.compare_digest(password,settings.local_admin_password)): return _local_token("local-admin","admin@isift.au","Pramod Singh")
        raise HTTPException(401,{"message":"Incorrect user ID or password.","code":"bad_password"})
    account=(await db.execute(select(LocalAccount).where(LocalAccount.email==username.lower()))).scalar_one_or_none()
    if not account: raise HTTPException(401,{"message":"No account was found for that user ID or email.","code":"no_account"})
    if not verify_password(password,account.password_hash): raise HTTPException(401,{"message":"Incorrect user ID or password.","code":"bad_password"})
    row=(await db.execute(select(User).where(User.entra_subject==account.id))).scalar_one_or_none()
    if row and row.is_active is False: raise HTTPException(403,{"message":"This account is disabled. Contact an administrator.","code":"disabled"})
    return _local_token(account.id,account.email,account.display_name or account.email)

@api.get("/auth/countries")
async def auth_countries():
    from app.services.countries import COUNTRIES
    return COUNTRIES

def _su_guard():
    if not (settings.is_local_demo and settings.allow_signup): raise HTTPException(404,"Sign-up is not available")

async def _su(coro):
    from app.services.signup import SignupError
    try: return await coro
    except SignupError as e: raise HTTPException(e.status,{"message":e.message,"code":e.code})

@api.post("/auth/signup/start")
async def signup_start(payload:dict,db:AsyncSession=Depends(get_db)):
    """Step 1: check every field, then email a 6-digit code. Nothing is created until the code is entered."""
    _su_guard(); from app.services import signup as su
    return await _su(su.start(db,payload))

@api.get("/auth/signup/status")
async def signup_status(email:str,db:AsyncSession=Depends(get_db)):
    """Did the verification email go out? (The send continues in the background when the mail server is slow.)"""
    _su_guard(); from app.services import signup as su
    return await su.status(db,email)

@api.post("/auth/signup/resend")
async def signup_resend(payload:dict,db:AsyncSession=Depends(get_db)):
    _su_guard(); from app.services import signup as su
    return await _su(su.resend(db,payload.get("email")))

@api.post("/auth/signup/verify")
async def signup_verify(payload:dict,db:AsyncSession=Depends(get_db)):
    """Step 2: the right code creates the account and signs the person in."""
    _su_guard(); from app.services import signup as su
    account=await _su(su.verify(db,payload.get("email"),payload.get("code")))
    return _local_token(account.id,account.email,account.display_name)

@api.post("/auth/signup")
async def signup_old(payload:dict):
    raise HTTPException(410,{"message":"Sign-up now needs an emailed verification code.","code":"use_start"})

def _is_local(request:Request)->bool:
    host=(request.client.host if request.client else "") or ""
    return host in ("127.0.0.1","::1","localhost") and not request.headers.get("x-forwarded-for")

@api.get("/calendar/machine")
async def machine_calendar_status(request:Request,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    return await cal.machine_status(db,user.id,_is_local(request))

@api.post("/calendar/machine/consent")
async def machine_calendar_consent(payload:dict,request:Request,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    allow=bool(payload.get("allow"))
    if allow:
        if not settings.machine_calendar_allowed: raise HTTPException(403,"An administrator has switched off reading the calendar on this computer.")
        if not _is_local(request): raise HTTPException(403,"The calendar on a computer can only be allowed from that computer.")
        if not cal.machine.detect()["available"]: raise HTTPException(404,"No calendar was found on this computer.")
    await cal.set_consent(db,user.id,allow)
    db.add(AuditLog(actor=user.email,action="calendar.machine.allow" if allow else "calendar.machine.deny",resource_type="calendar",safe_metadata={}));await db.commit()
    return await cal.machine_status(db,user.id,_is_local(request))

@api.post("/calendar/machine/search")
async def machine_calendar_search(request:Request,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    cal.machine.detect(True)
    return await cal.machine_status(db,user.id,_is_local(request))

@api.post("/calendar/upload")
async def calendar_upload(request:Request,file:UploadFile=File(...),user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    raw=await file.read(cal.machine.MAX_ICS_BYTES+1)
    if len(raw)>cal.machine.MAX_ICS_BYTES: raise HTTPException(413,"That file is too large (limit 20 MB).")
    text=raw.decode("utf-8-sig",errors="ignore")
    if "BEGIN:VCALENDAR" not in text.upper(): raise HTTPException(422,"That does not look like a calendar (.ics) file.")
    tz=await cal.user_timezone(db); start,_=cal.today_window(tz)
    found=cal.machine.events_from_ics_text(text,start,start+timedelta(days=cal.DAYS_AHEAD+1))
    await cal.save_upload(db,user.id,text,file.filename or "calendar.ics")
    db.add(AuditLog(actor=user.email,action="calendar.upload",resource_type="calendar",safe_metadata={"events_in_window":len(found)}));await db.commit()
    try: result=await cal.sync_calendar(db,user.id)
    except GraphUnavailable as exc: raise HTTPException(502,str(exc))
    return {"message":f"Calendar uploaded: {result['eligible']} meeting(s) in the next {cal.DAYS_AHEAD} days ({result['added']} new).","result":result}

@api.get("/auth/me",response_model=UserOut)
async def whoami(user:User=Depends(principal)): return user

@api.get("/dashboard")
async def dashboard(request:Request,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    now=datetime.now(timezone.utc)
    meetings=(await db.execute(select(Meeting).where(Meeting.owner_id==user.id,Meeting.start_at>=now).order_by(Meeting.start_at).limit(12))).scalars().all()
    actions=(await db.execute(select(ActionItem).join(Meeting).where(Meeting.owner_id==user.id,ActionItem.status!="completed").order_by(ActionItem.due_date).limit(12))).scalars().all()
    briefing=(await db.execute(select(Briefing).where(Briefing.user_id==user.id).order_by(Briefing.created_at.desc()).limit(1))).scalar_one_or_none()
    runs=(await db.execute(select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(10))).scalars().all() if user.role=="admin" else []
    from app.services.identity import shown_email
    tz=await cal.user_timezone(db); wstart,wend=cal.today_window(tz); local=datetime.now(tz)
    todays=(await db.execute(select(Meeting).where(Meeting.owner_id==user.id,Meeting.status!="cancelled",Meeting.start_at>=wstart.astimezone(timezone.utc),Meeting.start_at<wend.astimezone(timezone.utc)).order_by(Meeting.start_at))).scalars().all()
    sync_row=await db.get(IntegrationSetting,cal.status_key(user.id)); sync=dict(sync_row.value) if sync_row and sync_row.value else {}
    today={"date":local.date().isoformat(),"weekday":local.strftime("%A"),"timezone":str(tz),"briefing_time":settings.briefing_time,"calendar_connected":bool((cal.graph_configured() and mailbox_for(user.email)) or await cal.machine_usable(db,user.id) or bool(await cal.get_upload(db,user.id)) or bool(await cal.get_feeds(db,user.id))),"machine":await cal.machine_status(db,user.id,_is_local(request)),"auto_refresh_minutes":settings.calendar_sync_minutes,"last_sync":{"at":sync.get("at"),"ok":sync.get("ok"),"error":sync.get("error"),"source":sync.get("source")},"meetings":[{"id":m.id,"title":m.title,"organizer":shown_email(m.organizer or ""),"start_at":cal.as_utc(m.start_at).isoformat(),"end_at":cal.as_utc(m.end_at).isoformat(),"join_url":m.join_url,"transcript_status":m.transcript_status,"minutes_status":m.minutes_status} for m in todays]}
    return {"today":today,"meetings":[MeetingOut.model_validate(x) for x in meetings],"actions":[{"id":x.id,"meeting_id":x.meeting_id,"description":x.description,"owner":x.owner,"due_date":x.due_date,"status":x.status} for x in actions],"latest_briefing":briefing,"recent_runs":runs,"integrations":integration_status()}

@api.post("/demo/seed")
async def load_demo_data(reset:bool=False,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    """Kept for older clients; same as POST /data/mock/load."""
    from app.api.routes_admin import mock_load, mock_guard
    await mock_guard(db)
    return await mock_load(reset,user,db,None)

def integration_status():
    return {"entra":settings.auth_mode=="entra" and bool(settings.entra_tenant_id),"calendar":bool(settings.graph_client_id and settings.graph_user_id),"transcripts":settings.graph_transcript_enabled and bool(settings.graph_client_id),"ai":ai_configured(),"scheduler":"Power Automate (external setup)","teams_delivery":"Power Automate connector (configure and validate)"}

@api.get("/meetings",response_model=list[MeetingOut])
async def meetings(user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    from app.services.identity import shown_email
    out=[MeetingOut.model_validate(m) for m in (await db.execute(select(Meeting).where(Meeting.owner_id==user.id).order_by(Meeting.start_at.desc()).limit(200))).scalars().all()]
    for m in out:
        if m.organizer: m.organizer=shown_email(m.organizer)     # never show the placeholder admin@isift.au
    return out

@api.get("/meetings/{meeting_id}")
async def meeting_detail(meeting_id:str,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    m=(await db.execute(select(Meeting).where(Meeting.id==meeting_id,Meeting.owner_id==user.id))).scalar_one_or_none()
    if not m: raise HTTPException(404,"Meeting not found")
    transcript=(await db.execute(select(Transcript).where(Transcript.meeting_id==m.id).order_by(Transcript.created_at.desc()).limit(1))).scalar_one_or_none()
    minutes=(await db.execute(select(Minutes).where(Minutes.meeting_id==m.id).order_by(Minutes.version.desc()).limit(1))).scalar_one_or_none()
    from app.services.identity import shown_email
    mo=MeetingOut.model_validate(m)
    if mo.organizer: mo.organizer=shown_email(mo.organizer)
    return {"meeting":mo,"transcript":transcript,"minutes":minutes}

@api.post("/meetings/sync")
async def sync_calendar(user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    try: result=await cal.sync_calendar(db,user.id)
    except GraphUnavailable as exc: raise HTTPException(503,str(exc))
    return {"synced_eligible_meetings":result["eligible"],**result}

@api.post("/briefings/preview")
async def briefing_preview(user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    try: result=await build_preview(db,user.id)
    except GraphUnavailable as exc: raise HTTPException(503,str(exc))
    return {k:v for k,v in result.items() if k!="events"}

@api.post("/briefings/run")
async def briefing_run(user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    result=await build_preview(db,user.id,persist=True,run_type="manual")
    key=(user.id,result["local_date"],"manual")
    old=(await db.execute(select(Briefing).where(Briefing.user_id==key[0],Briefing.local_date==key[1],Briefing.run_type==key[2]))).scalar_one_or_none()
    if old: return {"briefing_id":old.id,"rendered_text":old.rendered_text,"delivery_status":old.delivery_status,"reused":True}
    b=Briefing(user_id=user.id,local_date=result["local_date"],run_type="manual",payload={"meeting_count":result["eligible_meetings"]},rendered_text=result["rendered_text"],word_count=result["word_count"],generation_status="generated",delivery_status="preview_only")
    db.add(b)
    try: await db.commit()
    except IntegrityError:
        await db.rollback()      # a parallel request for the same person created it first
        old=(await db.execute(select(Briefing).where(Briefing.user_id==key[0],Briefing.local_date==key[1],Briefing.run_type==key[2]))).scalar_one()
        return {"briefing_id":old.id,"rendered_text":old.rendered_text,"delivery_status":old.delivery_status,"reused":True}
    await db.refresh(b)
    return {"briefing_id":b.id,"rendered_text":b.rendered_text,"word_count":b.word_count,"delivery_status":b.delivery_status,"reused":False}

@api.get("/briefings")
async def briefing_history(user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    return (await db.execute(select(Briefing).where(Briefing.user_id==user.id).order_by(Briefing.created_at.desc()).limit(90))).scalars().all()

@api.get("/briefings/latest")
async def latest_briefing(user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    return (await db.execute(select(Briefing).where(Briefing.user_id==user.id).order_by(Briefing.created_at.desc()).limit(1))).scalar_one_or_none()

@api.post("/automation/briefings/run")
async def automation_run(authorization:str|None=Header(default=None),db:AsyncSession=Depends(get_db)):
    if not settings.automation_shared_token or authorization!=f"Bearer {settings.automation_shared_token}": raise HTTPException(401,"Automation authorization failed")
    user=(await db.execute(select(User).where(User.email==settings.automation_user_email.lower()))).scalar_one_or_none()
    if not user: raise HTTPException(409,"The briefing recipient must sign in once before scheduled delivery is enabled")
    try: result=await build_preview(db,user.id,persist=True,run_type="scheduled")
    except GraphUnavailable as exc: raise HTTPException(503,str(exc))
    row=(await db.execute(select(Briefing).where(Briefing.user_id==user.id,Briefing.local_date==result["local_date"],Briefing.run_type=="scheduled"))).scalar_one_or_none()
    if row: return {"briefing_id":row.id,"local_date":row.local_date,"text":row.rendered_text,"word_count":row.word_count,"idempotent_replay":True}
    row=Briefing(user_id=user.id,local_date=result["local_date"],run_type="scheduled",payload={"meeting_count":result["eligible_meetings"]},rendered_text=result["rendered_text"],word_count=result["word_count"],generation_status="generated",delivery_status="pending")
    db.add(row); await db.commit(); await db.refresh(row)
    return {"briefing_id":row.id,"local_date":row.local_date,"text":row.rendered_text,"word_count":row.word_count,"idempotent_replay":False}

@api.post("/automation/briefings/delivery")
async def delivery_callback(data:DeliveryCallback,authorization:str|None=Header(default=None),db:AsyncSession=Depends(get_db)):
    if not settings.automation_shared_token or authorization!=f"Bearer {settings.automation_shared_token}": raise HTTPException(401,"Automation authorization failed")
    b=(await db.execute(select(Briefing).where(Briefing.id==data.briefing_id))).scalar_one_or_none()
    if not b: raise HTTPException(404,"Briefing not found")
    b.delivery_status=data.status; b.delivery_reference=data.reference
    await db.commit(); return {"ok":True,"delivery_status":b.delivery_status}

@api.get("/runs")
async def runs(user:User=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return (await db.execute(select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(100))).scalars().all()

@api.get("/meetings/{meeting_id}/minutes")
async def get_minutes(meeting_id:str,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    owns=(await db.execute(select(Meeting.id).where(Meeting.id==meeting_id,Meeting.owner_id==user.id))).scalar_one_or_none()
    if not owns: raise HTTPException(404,"Meeting not found")
    return (await db.execute(select(Minutes).where(Minutes.meeting_id==meeting_id).order_by(Minutes.version.desc()))).scalars().all()

@api.patch("/minutes/{minutes_id}")
async def update_minutes(minutes_id:str,data:MinutesUpdate,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    old=(await db.execute(select(Minutes).join(Meeting).where(Minutes.id==minutes_id,Meeting.owner_id==user.id))).scalar_one_or_none()
    if not old: raise HTTPException(404,"Minutes not found")
    # Immutable versions preserve the original generated draft and reviewer edits.
    new=Minutes(meeting_id=old.meeting_id,version=old.version+1,content=data.content,review_status=data.review_status,edited_by=user.email,approved_at=datetime.now(timezone.utc) if data.review_status=="approved" else None)
    db.add(new); old.review_status="superseded"; await db.commit(); await db.refresh(new)
    db.add(AuditLog(actor=user.email,action="minutes.updated",resource_type="minutes",resource_id=new.id,safe_metadata={"review_status":new.review_status})); await db.commit()
    return new

@api.get("/action-items")
async def action_items(user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    return (await db.execute(select(ActionItem).join(Meeting).where(Meeting.owner_id==user.id).order_by(ActionItem.due_date))).scalars().all()

@api.patch("/action-items/{action_id}")
async def update_action(action_id:str,data:ActionUpdate,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    row=(await db.execute(select(ActionItem).join(Meeting).where(ActionItem.id==action_id,Meeting.owner_id==user.id))).scalar_one_or_none()
    if not row: raise HTTPException(404,"Action item not found")
    for key,value in data.model_dump(exclude_unset=True).items(): setattr(row,key,value)
    await db.commit(); return row

async def _team_items(db,user,action_id=None):
    from app.services import team
    emails=await team.need_team(db,user); ids=[u.id for u in (await team.users_by_email(db,emails)).values()]
    q=select(ActionItem,Meeting).join(Meeting).where(Meeting.owner_id.in_(ids),Meeting.sensitivity=="normal")
    if action_id: q=q.where(ActionItem.id==action_id)
    return (await db.execute(q.order_by(ActionItem.due_date))).all()

@api.get("/team/action-items")
async def team_action_items(user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    """Action items from teammates' normal (not sensitive) meetings, for everyone on a Business company account."""
    rows=await _team_items(db,user); owners={u.id:u.email for u in (await db.execute(select(User).where(User.id.in_({m.owner_id for _,m in rows})))).scalars().all()} if rows else {}
    return [{"id":a.id,"description":a.description,"owner":a.owner,"due_date":a.due_date,"priority":a.priority,"status":a.status,"meeting_id":m.id,"meeting_title":m.title,"meeting_owner":owners.get(m.owner_id,""),"mine":m.owner_id==user.id} for a,m in rows]

@api.patch("/team/action-items/{action_id}")
async def team_update_action(action_id:str,data:ActionUpdate,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    rows=await _team_items(db,user,action_id)
    if not rows: raise HTTPException(404,"Action item not found")
    row=rows[0][0]
    for key,value in data.model_dump(exclude_unset=True).items(): setattr(row,key,value)
    db.add(AuditLog(actor=user.email,action="team.action.update",resource_type="action_item",resource_id=row.id,safe_metadata={})); await db.commit()
    return {"id":row.id,"status":row.status,"owner":row.owner,"due_date":row.due_date,"priority":row.priority}

@api.post("/meetings/{meeting_id}/minutes/generate")
async def enqueue_minutes(meeting_id:str,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    m=(await db.execute(select(Meeting).where(Meeting.id==meeting_id,Meeting.owner_id==user.id))).scalar_one_or_none()
    if not m: raise HTTPException(404,"Meeting not found")
    t=(await db.execute(select(Transcript).where(Transcript.meeting_id==meeting_id,Transcript.status=="ready").order_by(Transcript.created_at.desc()).limit(1))).scalar_one_or_none()
    if not t: raise HTTPException(409,"A transcript must be available before minutes can be generated")
    from app.services import entitlements as ent
    await ent.use_ai(db,user)                  # Basic: 3 AI summaries a month
    correlation_id=str(uuid.uuid4())
    run=WorkflowRun(correlation_id=correlation_id,workflow_name="generate_minutes",status="queued"); db.add(run); await db.flush()
    job=Job(kind="generate_minutes",payload={"meeting_id":m.id,"transcript_id":t.id,"workflow_run_id":run.id})
    db.add(job); m.minutes_status="queued"
    await db.commit(); return {"job_id":job.id,"status":"queued"}

@api.post("/meetings/{meeting_id}/transcribe")
async def enqueue_transcript(meeting_id:str,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    m=(await db.execute(select(Meeting).where(Meeting.id==meeting_id,Meeting.owner_id==user.id))).scalar_one_or_none()
    if not m: raise HTTPException(404,"Meeting not found")
    from app.services.meeting_links import provider_for
    if provider_for(m.join_url)=="room": raise HTTPException(409,"Meeting-room recordings are transcribed automatically when the host saves the recording.")
    kind="fetch_zoom_transcript" if provider_for(m.join_url)=="zoom" else "fetch_graph_transcript"
    job=Job(kind=kind,payload={"meeting_id":m.id})
    db.add(job); m.transcript_status="queued"; await db.commit()
    return {"job_id":job.id,"status":"queued","note":"Processing an existing official transcript only; this does not record or join the meeting."}

@api.post("/meetings/{meeting_id}/audio")
async def upload_audio(meeting_id:str,consent_acknowledged:bool=Form(...),file:UploadFile=File(...),user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    if not consent_acknowledged: raise HTTPException(400,"Confirm authorization and applicable meeting consent before upload")
    m=(await db.execute(select(Meeting).where(Meeting.id==meeting_id,Meeting.owner_id==user.id))).scalar_one_or_none()
    if not m: raise HTTPException(404,"Meeting not found")
    allowed={"audio/mpeg","audio/mp4","audio/x-m4a","audio/wav","audio/ogg","audio/webm","audio/flac","video/mp4"}
    if file.content_type not in allowed: raise HTTPException(415,"Unsupported audio media type")
    suffix=Path(file.filename or "audio").suffix.lower()
    if suffix not in {".mp3",".mp4",".m4a",".wav",".ogg",".webm",".flac",".mpeg",".mpga"}: raise HTTPException(415,"Unsupported audio file extension")
    os.makedirs(settings.audio_storage_dir,exist_ok=True); path=Path(settings.audio_storage_dir)/(str(uuid.uuid4())+suffix)
    size=0; header=b""
    try:
        with path.open("wb") as out:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>settings.audio_max_bytes: raise HTTPException(413,"Audio exceeds configured upload size limit")
                if not header: header=chunk[:16]
                out.write(chunk)
    except Exception:
        path.unlink(missing_ok=True); raise
    signatures={".wav":header.startswith(b"RIFF") and header[8:12]==b"WAVE",".ogg":header.startswith(b"OggS"),".flac":header.startswith(b"fLaC"),".webm":header.startswith(bytes.fromhex("1A45DFA3")),".mp4":b"ftyp" in header,".m4a":b"ftyp" in header,".mp3":header.startswith(b"ID3") or (len(header)>1 and header[0]==0xff and header[1]&0xe0==0xe0),".mpeg":header.startswith(b"ID3") or (len(header)>1 and header[0]==0xff and header[1]&0xe0==0xe0),".mpga":header.startswith(b"ID3") or (len(header)>1 and header[0]==0xff and header[1]&0xe0==0xe0)}
    if not signatures.get(suffix,False): path.unlink(missing_ok=True); raise HTTPException(415,"File signature does not match a supported audio/video format")
    job=Job(kind="transcribe_audio",payload={"meeting_id":m.id,"path":str(path),"filename":file.filename or path.name,"owner_id":user.id})
    db.add(job); m.transcript_status="queued"; await db.commit()
    return {"job_id":job.id,"status":"queued","bytes":size,"retention":"Temporary processing copy; deletion depends on configured retention policy."}

@api.get("/jobs/{job_id}")
async def job_status(job_id:str,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    job=(await db.execute(select(Job).where(Job.id==job_id))).scalar_one_or_none()
    if not job: raise HTTPException(404,"Job not found")
    meeting_id=job.payload.get("meeting_id")
    owns=(await db.execute(select(Meeting.id).where(Meeting.id==meeting_id,Meeting.owner_id==user.id))).scalar_one_or_none()
    if not owns: raise HTTPException(404,"Job not found")
    return {"id":job.id,"kind":job.kind,"status":job.status,"attempts":job.attempts,"safe_error":job.last_error}

@api.get("/transcripts/{meeting_id}")
async def get_transcript(meeting_id:str,user:User=Depends(principal),db:AsyncSession=Depends(get_db)):
    owns=(await db.execute(select(Meeting.id).where(Meeting.id==meeting_id,Meeting.owner_id==user.id))).scalar_one_or_none()
    if not owns: raise HTTPException(404,"Meeting not found")
    return (await db.execute(select(Transcript).options(selectinload(Transcript.segments)).where(Transcript.meeting_id==meeting_id).order_by(Transcript.created_at.desc()).limit(1))).scalar_one_or_none()

@api.get("/admin/settings")
async def admin_settings(user:User=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    saved=(await db.execute(select(IntegrationSetting))).scalars().all(); values={x.key:x.value for x in saved}
    return {"preferences":values.get("preferences",{"timezone":settings.default_timezone,"briefing_time":settings.briefing_time,"lookback_days":settings.lookback_days,"human_review_required":True,"transcript_retention_days":365,"minutes_retention_days":365,"sensitive_context_enabled":False}),"integrations":integration_status(),"fields":await rs.describe(db),"database":rs.database_display(),"secrets":{"ai_configured":ai_configured(),"microsoft_client_configured":bool(settings.graph_client_secret),"database_configured":bool(settings.database_url),"automation_token_configured":bool(settings.automation_shared_token)},"secret_policy":"Secret values are stored encrypted and only a masked preview is ever shown."}

@api.patch("/admin/integration-settings")
async def update_integration_settings(payload:dict,user:User=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    values=payload.get("values")
    if not isinstance(values,dict): raise HTTPException(422,"Expected a 'values' object")
    try: changed=await rs.save(db,values)
    except ValueError as exc: raise HTTPException(422,str(exc))
    db.add(AuditLog(actor=user.email,action="admin.integration_settings.updated",resource_type="settings",safe_metadata={"keys":changed}))
    await db.commit()
    return {"changed":changed,"fields":await rs.describe(db)}

@api.patch("/admin/settings")
async def update_admin_settings(data:SettingsUpdate,user:User=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    row=(await db.execute(select(IntegrationSetting).where(IntegrationSetting.key=="preferences"))).scalar_one_or_none()
    current=row.value if row else {"timezone":settings.default_timezone,"briefing_time":settings.briefing_time,"lookback_days":settings.lookback_days,"human_review_required":True,"transcript_retention_days":365,"minutes_retention_days":365,"sensitive_context_enabled":False}
    current.update(data.model_dump(exclude_unset=True))
    if row: row.value=current
    else: db.add(IntegrationSetting(key="preferences",value=current))
    db.add(AuditLog(actor=user.email,action="admin.settings.updated",resource_type="settings",safe_metadata={"keys":list(data.model_dump(exclude_unset=True).keys())}))
    await db.commit(); return {"preferences":current,"secrets":"unchanged"}

@api.post("/admin/integrations/test")
async def test_integrations(user:User=Depends(require_admin)):
    result={"entra":{"configured":bool(settings.entra_tenant_id),"status":"configured" if settings.entra_tenant_id else "not_configured"},"graph":{"configured":False,"status":"not_configured"},"teams_delivery":{"configured":bool(settings.automation_shared_token),"status":"requires Power Automate tenant validation"}}
    if settings.graph_client_id and settings.graph_client_secret and settings.graph_user_id:
        try:
            from datetime import time, timedelta
            from app.core.tz import zone
            local_now=datetime.now(zone(settings.default_timezone)); start=datetime.combine(local_now.date(),time.min,tzinfo=local_now.tzinfo)
            await graph.calendar(start,start+timedelta(days=1)); result["graph"]={"configured":True,"status":"calendar_connected","detail":"Calendar view request succeeded for the configured user. Transcript and message scopes are separate."}
        except Exception as exc: result["graph"]={"configured":True,"status":"failed","detail":str(exc)[:160]}
    from app.services import groq as _groq
    if _groq.configured():
        ok,detail=await _groq.ping(); result["groq_ai"]={"configured":True,"status":"connected" if ok else "failed","detail":detail}
    from app.services import billing as _bill
    result["square"]=await _bill.test_square()
    from app.services import storage as _st
    result["recording_storage_r2"]=await _st.test_r2()
    return result

@api.get("/health")
async def health(db:AsyncSession=Depends(get_db)):
    try: await db.execute(select(func.count()).select_from(User)); db_ok=True
    except Exception: db_ok=False
    return {"status":"ok" if db_ok else "degraded","database":"ok" if db_ok else "unavailable","integrations":integration_status()}
