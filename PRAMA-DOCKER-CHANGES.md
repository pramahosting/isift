# Prama Monitor for iSift

This repository is already set up for Prama Monitor. No iSift feature was changed.

## What was added or changed

| File | Change |
|---|---|
| `prama-northflank-env.ps1` | New. Sets the monitoring variables on the iSift Northflank service (PowerShell) |
| `prama-northflank-env.sh` | New. The same for macOS, Linux or Git Bash |
| `PRAMA-DOCKER-CHANGES.md` | New. This page |
| `backend/prama-start.sh` | New. Start wrapper: turns tracing on only when the Northflank variables are set |
| `backend/prama_monitor.py` | New, optional helper for reporting AI token usage. Not used by the app yet |
| `backend/requirements.txt` | 4 OpenTelemetry lines added at the end |
| `Dockerfile` | Last line: `exec uvicorn ...` became `exec sh prama-start.sh uvicorn ...` |
| `frontend/index.html` | One script line added before `</head>` (real-visitor monitoring) |

If the Northflank variables are missing, the app starts exactly as before.

## Run once: set the Northflank variables

In PowerShell, in this folder:

```powershell
$env:NORTHFLANK_API_TOKEN = "your Northflank API token"
$env:PRAMA_INGEST_TOKEN   = "the monitor INGEST_TOKEN"
.\prama-northflank-env.ps1 -DryRun
.\prama-northflank-env.ps1
```

If PowerShell says scripts are disabled, run `Set-ExecutionPolicy -Scope Process Bypass` first.
It changes only the Prama and OpenTelemetry variables and keeps all other iSift variables as they are.
iSift is Python, so it uses `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` (the Python exporter cannot send http/json; the monitor accepts both).

## Check it worked

Northflank logs show `[isift] Prama Monitor tracing on (service isift...)` at start-up.
Within a few minutes Prama Monitor > Platforms > iSift shows the backend, and Telemetry > Traces lists iSift requests.
