# Deploying iSift on Northflank

iSift ships as **one container** (web app + API + background worker). The `Dockerfile` in the project root builds it.

## 1. What you need first
- A Git repository containing this project (GitHub, GitLab or Bitbucket), connected to Northflank.
- A PostgreSQL database: a **Northflank PostgreSQL add-on** or **Neon**. Use its connection string as `DATABASE_URL` (both `postgresql://…` and `postgresql+asyncpg://…` are accepted).
- Your public address, e.g. `https://meet.yourcompany.com` (a Northflank `*.code.run` address works for a first test).
- Optional, set later in the Admin Console screen: Cloudflare R2, Square, email (SMTP), AI keys, TURN server.

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
| `SETTINGS_ENCRYPTION_KEY` | another random string; encrypts secrets saved in Admin Console (do not lose it) |

`HOSTED=true`, `APP_ENV=production`, `AUTH_MODE=local`, `RUN_WORKER=true` are already set in the image. In HOSTED mode the service **refuses to start** (and prints why in the log) if the secret is short, the admin password is the demo one, the database is the demo one, or `FRONTEND_ORIGIN` is still localhost. Sample data and the computer-calendar import are switched off.

Database tables are created and upgraded automatically each time the container starts.

## 4. After it is running
1. Open the address, sign in as `admin`, and go to **Admin Console**. Work down the Setup checklist.
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


## 7. Database quota, standby databases and idle usage (Neon)
**Why quota ran out with nobody using iSift:** a serverless database (Neon) only stops billing compute after about 5 minutes with no queries.
The health check, the worker's polling and the push loop were querying every few seconds, so it never slept. Now:
- `/api/v1/health` does **not** use the database (probes are free). `/api/v1/health?deep=1` checks it (cached 60 s).
- The worker is woken the moment a job is saved and otherwise looks only every `WORKER_IDLE_MAX_SECONDS` (300 s when `RUN_WORKER=true`, 15 s as a separate service). Admin settings are cached in memory (`WORKER_SETTINGS_SECONDS`, 300 s). Price list and plan matrix are cached 30 s.
- Set `PUSH_LOOP_SECONDS=300` (or `PUSH_LOOP=false` if nobody uses push) so the push loop does not keep the database awake.
- Keep `DB_POOL_SIZE` small (3 is plenty for one instance).

**Standby databases (several Neon accounts):** put the extra addresses in `DATABASE_STANDBY_URLS` (comma or newline separated). When the main
database refuses connections because of quota (or is unreachable) the app moves to the next one by itself, logs `DATABASE FAILOVER`, and
`/api/v1/health?deep=1` shows `database_failover`. It does **not** switch back by itself, because the copies would differ. After a failover set
`DATABASE_ACTIVE_INDEX` to the number now in use (0 = `DATABASE_URL`, 1 = first standby, ...) so a restart does not go back to an older copy.
Nothing is copied on a timer. Data moves only at two moments:
1. **Failover** (main out of quota, app moves to a standby): the app tries once to copy the old database into the new one. An exhausted database usually cannot be read, so the standby then simply carries on with what it has.
2. **Fail-back:** while a standby is in use, the main database is tried every `DB_FAILBACK_MINUTES` (default 30; 0 = off). As soon as it accepts connections, everything in the standby is merged into it and the app switches back (a second quick pass catches rows written meanwhile). Set `DATABASE_ACTIVE_INDEX=0` afterwards.

A copy is a **merge**: rows are inserted or updated by primary key and nothing is deleted, so data that only exists in the older database is kept. A row that would break another unique rule (same e-mail under a different id) is skipped and counted. `DB_SYNC_SKIP_TABLES=a,b` leaves out big tables.
Admin can also merge by hand: `POST /api/v1/admin/db-sync?source=1&target=0` and read the result with `GET /api/v1/admin/db-sync`; or `python tools/sync_standby.py --from 1 --to 0`.
Because a quota-exhausted database cannot be read, data written to it before the failover reaches the standby only if you merge it later (`--from 0 --to 1`, once the main works again; fail-back does the standby-to-main direction by itself).
