# Deploying iSift on Northflank

iSift ships as **one container** (web app + API + background worker). The `Dockerfile` in the project root builds it.

## 1. What you need first
- A Git repository containing this project (GitHub, GitLab or Bitbucket), connected to Northflank.
- A PostgreSQL database: a **Northflank PostgreSQL add-on** or **Neon**. Use its connection string as `DATABASE_URL` (both `postgresql://…` and `postgresql+asyncpg://…` are accepted).
- Your public address, e.g. `https://meet.yourcompany.com` (a Northflank `*.code.run` address works for a first test).
- Optional, set later in the Admin settings screen: Cloudflare R2, Square, email (SMTP), AI keys, TURN server.

## 2. Create the service
1. New **Combined service** from your repository. Build type: **Dockerfile**, Dockerfile path `/Dockerfile`, build context `/`.
2. Port: **8000**, protocol **HTTP**, publicly exposed (Northflank adds HTTPS).
3. Health check (liveness and readiness): HTTP `GET /api/v1/health` on port 8000.
4. **Instances: 1.** Live meeting rooms are held in the server's memory, so more than one instance would split people across servers. Resources: at least 1 vCPU and 1 GB memory (video compression uses more; 2 GB is comfortable).
5. No persistent volume is needed: accounts live in PostgreSQL and recordings in R2 or the database.

## 3. Environment variables (put them in a Northflank secret group)
| Name | Value |
|---|---|
| `DATABASE_URL` | your PostgreSQL connection string |
| `FRONTEND_ORIGIN` | the public address, `https://…`, no trailing slash |
| `LOCAL_AUTH_SECRET` | a random string of 40+ characters (signs sessions; keep it stable, changing it signs everyone out) |
| `LOCAL_ADMIN_PASSWORD` | the first administrator password (10+ characters). User name is `admin`. Change it afterwards under My account > Password |
| `SETTINGS_ENCRYPTION_KEY` | another random string; encrypts secrets saved in Admin settings (do not lose it) |

`HOSTED=true`, `APP_ENV=production`, `AUTH_MODE=local`, `RUN_WORKER=true` are already set in the image. In HOSTED mode the service **refuses to start** (and prints why in the log) if the secret is short, the admin password is the demo one, the database is the demo one, or `FRONTEND_ORIGIN` is still localhost. Sample data and the computer-calendar import are switched off.

Database tables are created and upgraded automatically each time the container starts.

## 4. After it is running
1. Open the address, sign in as `admin`, and go to **Admin settings**. Work down the Setup checklist.
2. **Email (SMTP)** first: sign-up codes cannot be delivered without it. Use **Send a test email**.
3. **Recording storage (Cloudflare R2)** then **Connection test**.
4. **Payments (Square)**: start in sandbox, switch to production only when ready.
5. **Video meetings > STUN/TURN servers**: the default is a free public STUN server, which works for many people but fails behind strict firewalls and mobile networks. For a real service add a TURN server (Cloudflare Calls TURN, Twilio, Metered or your own coturn), e.g. `stun:stun.l.google.com:19302,turn:turn.example.com:3478?transport=udp|user|password` in the format shown in the help text.
6. Mail sign-in (Google/Microsoft/Yahoo) and the Outlook add-in: register the redirect addresses and add-in URL using your **https** address.
7. Add your domain under the service's **Domains** tab; point your DNS at the target Northflank shows.

## 5. Updating
Push to the repository; Northflank rebuilds and starts a new container. Keep instances at 1; a short interruption (a few seconds to a minute) ends live meetings in progress, so update when nobody is meeting.

## 6. Known limits to be aware of
- One instance only (see above). Scaling out needs the room state moved to Redis; not built.
- Very large cloud uploads (a long meeting is hundreds of MB) pass through the platform's HTTP proxy, which may have a request-size or time limit. If cloud uploads fail on long meetings, the local copy on the host's computer is unaffected; ask Northflank for the limit on your plan.
- The worker runs inside the web container. If you later want to separate it, run a second service with the command `python -m app.workers.runner` and `RUN_WORKER=false` on the web service.
- Backups are your responsibility: enable backups on the PostgreSQL add-on or Neon.
