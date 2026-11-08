iSift admin Usage report. Unzip into the repo root (isift-main/), replacing files when asked.

New:      backend/app/services/meeting_log.py        records each real meeting: when it started, ended, minutes, host
          backend/tests/test_usage_report.py          tests
Changed:  backend/app/api/routes_rooms.py             writes a log entry when a meeting ends (the old minutes counter is unchanged)
          backend/app/api/routes_admin.py             new /admin/usage and /admin/usage/export
          frontend/src/Admin.tsx, App.tsx             new "Usage" tab under Admin > Users, with CSV export

No database change is needed. Dates and times are recorded from the first meeting that ends after you deploy.
Then: cd frontend && npm run build, redeploy, open Admin > Users > Usage.
