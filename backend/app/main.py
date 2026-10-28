import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import api
from app.api.routes_admin import router as admin_router
from app.api.routes_connections import router as connections_router
from app.api.routes_rooms import router as rooms_router
from app.api.routes_calls import router as calls_router
from app.api.routes_workspace import router as workspace_router
from app.api.routes_sharing import router as sharing_router
from app.api.routes_docedit import router as docedit_router
from app.api.routes_docconvert import router as docconvert_router
from app.api.routes_mailbox import router as mailbox_router
from app.api.routes_isiftmail import router as isiftmail_router
from app.api.routes_isiftmail_abuse import router as isiftmail_abuse_router
from app.api.routes_webinars import router as webinars_router, pub as webinars_public_router
from app.api.routes_autoconfig import router as autoconfig_router
from app.api.routes_oauth import router as oauth_router
from app.api.routes_booking import router as booking_router
from app.api.routes_modules import router as modules_router
from app.api.routes_manuals import router as manuals_router
from app.api.routes_account import router as account_router
from app.api.routes_billing import router as billing_router
from app.api.routes_support import router as support_router
from app.api.routes_rsvp import router as rsvp_router
from app.core.config import settings

_bad = settings.hosted_problems()
if _bad: raise RuntimeError("iSift will not start in HOSTED mode until this is fixed:\n - " + "\n - ".join(_bad))

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
app=FastAPI(title=settings.app_name,version="1.0.0",description="Meeting preparation, transcript processing and human-reviewed minutes",**({} if settings.enable_api_docs else {"docs_url":None,"redoc_url":None,"openapi_url":None}))
@app.middleware("http")
async def keep_errors_readable(request: Request, call_next):
    # Unhandled errors would otherwise skip the CORS headers and the browser would only say "Failed to fetch".
    from app.core.tz import set_request_zone
    set_request_zone(request.headers.get("x-timezone"))      # the device's own time zone, sent by the web app
    try:
        return await call_next(request)
    except Exception as exc:
        logging.getLogger("app").exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": f"Server error: {type(exc).__name__}: {str(exc)[:300]}"}, status_code=500)

app.add_middleware(CORSMiddleware,allow_origins=sorted({settings.frontend_origin,settings.frontend_origin.replace("//localhost","//127.0.0.1"),settings.frontend_origin.replace("//127.0.0.1","//localhost")}),allow_credentials=True,allow_methods=["GET","POST","PATCH","PUT","DELETE"],allow_headers=["Authorization","Content-Type","X-Correlation-ID","X-Timezone"])
app.include_router(api)
app.include_router(admin_router)
app.include_router(connections_router)
app.include_router(rooms_router)
app.include_router(calls_router)
app.include_router(workspace_router)
app.include_router(sharing_router)
app.include_router(docedit_router)
app.include_router(docconvert_router)
app.include_router(mailbox_router)
app.include_router(isiftmail_router)
app.include_router(isiftmail_abuse_router)
app.include_router(webinars_router)
app.include_router(webinars_public_router)
app.include_router(autoconfig_router)
app.include_router(oauth_router)
app.include_router(booking_router)
app.include_router(modules_router)
app.include_router(manuals_router)
app.include_router(account_router)
app.include_router(billing_router)
app.include_router(support_router)
app.include_router(rsvp_router)
from app.api.routes_marketing import router as marketing_router
app.include_router(marketing_router)

@app.on_event("startup")
async def load_saved_settings():
    from app.core.db import SessionLocal
    from app.core.runtime_settings import apply_overrides, import_env_to_db
    try:
        async with SessionLocal() as db:
            moved=await import_env_to_db(db)
            if moved: logging.getLogger("isift").info("Copied %d settings from the environment into the database: %s",len(moved),", ".join(moved))
            await apply_overrides(db)
    except Exception: logging.getLogger("isift").warning("Saved settings could not be loaded yet (database not migrated?)")

import asyncio, os
from pathlib import Path

@app.on_event("startup")
async def start_embedded_worker():
    """Single-binary mode: run the background worker inside the same process."""
    if os.environ.get("RUN_WORKER","").lower()=="true":
        from app.workers import runner
        app.state.worker=asyncio.create_task(runner.main())

_web=os.environ.get("WEB_DIR","")
if _web and (Path(_web)/"index.html").is_file():
    from fastapi.staticfiles import StaticFiles
    # Built web app is served from the same address as the API (no separate frontend server).
    from fastapi.responses import FileResponse
    @app.get("/embed/")
    async def embed_page():
        # Same app, but this address may be shown inside other websites (booking widget).
        return FileResponse(Path(_web)/"index.html",headers={"Content-Security-Policy":"frame-ancestors *"})
    from fastapi.responses import RedirectResponse
    def _legal(slug):
        async def go(): return RedirectResponse(f"/#/{slug}", status_code=302)
        return go
    for _slug in ("terms","privacy","trust","acceptable-use","legal-compliance"):
        app.add_api_route(f"/{_slug}",_legal(_slug),methods=["GET"],include_in_schema=False)     # shareable addresses, e.g. for Google and Microsoft app settings
    app.mount("/",StaticFiles(directory=_web,html=True),name="web")
else:
    @app.get("/")
    async def root(): return {"name":settings.app_name,"version":"1.0.0"}
