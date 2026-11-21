"""Wake the worker the moment a job is saved, so it does not have to ask the database "any work?" every few seconds.
Works when the worker runs inside the web process (RUN_WORKER=true). A separate worker service cannot be woken this way and keeps polling."""
import asyncio
from sqlalchemy import event
from sqlalchemy.orm import Session, object_session
from app.models import Job

job_event = asyncio.Event()

@event.listens_for(Job, "after_insert")
def _job_added(_mapper, _conn, target):
    s = object_session(target)
    if s is not None: s.info["job_added"] = True

@event.listens_for(Session, "after_commit")
def _committed(session):
    if session.info.pop("job_added", False): job_event.set()

@event.listens_for(Session, "after_rollback")
def _rolled_back(session): session.info.pop("job_added", None)
