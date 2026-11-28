#!/usr/bin/env bash
# Prama Monitor - set observability environment variables on Northflank for iSift
#
# Run from this repository's root folder (macOS, Linux or Git Bash on Windows; needs curl and python3):
#     bash prama-northflank-env.sh            (asks before changing anything)
#     bash prama-northflank-env.sh --dry-run  (only shows what would change)
#     bash prama-northflank-env.sh --yes      (saves without asking)
#
# Tokens come from the environment, or the script asks for them without showing what you type:
#     export NORTHFLANK_API_TOKEN=...   (Northflank > Account or Team settings > API > Tokens)
#     export PRAMA_INGEST_TOKEN=...     (the monitor's INGEST_TOKEN; Accfino already uses it)
#
# It keeps every other variable of the service as it is and only adds or updates the Prama / OpenTelemetry ones.
set -euo pipefail
APP_KEY="isift"
APP_NAME="iSift"
PREFIXES="isift"     # Northflank service names that belong to this app start with one of these
ENDPOINT="${PRAMA_OTLP_ENDPOINT:-https://monitor.prama-ai.workers.dev/api/otlp}"
API="${NORTHFLANK_API_URL:-https://api.northflank.com/v1}"
DRY=0; YES=0; STACK=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --yes) YES=1 ;;
    --stack) STACK="$2"; shift ;;
    *) echo "Unknown option $1"; exit 2 ;;
  esac; shift
done
command -v python3 >/dev/null || { echo "python3 is needed"; exit 1; }
NF="${NORTHFLANK_API_TOKEN:-}"; ING="${PRAMA_INGEST_TOKEN:-}"
[ -n "$NF" ] || { read -rsp "Northflank API token: " NF; echo; }
[ -n "$ING" ] || { read -rsp "Prama INGEST_TOKEN: " ING; echo; }
[ -n "$NF" ] && [ -n "$ING" ] || { echo "Both tokens are needed."; exit 1; }

if [ -z "$STACK" ]; then
  if [ -f requirements.txt ] || [ -f pyproject.toml ] || [ -f Pipfile ]; then STACK=python
  elif [ -f package.json ]; then STACK=node
  else STACK=static; fi
fi
echo "App: $APP_NAME  (key: $APP_KEY, type: $STACK)"
if [ "$STACK" = static ]; then
  echo "This repository looks like a static website. Static sites need no Northflank variables:"
  echo "add the one script line from PRAMA-DOCKER-CHANGES.md to your HTML instead."
  echo "If this repository has a backend, run again with --stack python or --stack node."
  exit 0
fi

export NF ING APP_KEY APP_NAME PREFIXES ENDPOINT API DRY YES STACK
python3 - <<'PY'
import json, os, sys, urllib.request, urllib.error
api, tok = os.environ['API'], os.environ['NF']
def nf(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api + path, data=data, method=method, headers={'Authorization': 'Bearer ' + tok, **({'Content-Type': 'application/json'} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        sys.exit(f"Northflank said HTTP {e.code} for {method} {path}: {e.read()[:300].decode(errors='replace')}")
key, name, stack, ing = os.environ['APP_KEY'], os.environ['APP_NAME'], os.environ['STACK'], os.environ['ING']
prefixes = os.environ['PREFIXES'].split()
projects = nf('GET', '/projects?per_page=100')['data']['projects']
found, allsvc = [], []
for p in projects:
    for s in nf('GET', f"/projects/{p['id']}/services?per_page=100")['data']['services']:
        sid = str(s['id']).lower(); allsvc.append(f"{p['id']} / {sid}")
        for pre in prefixes:
            if sid == pre or sid.startswith(pre + '-'):
                rest = sid[len(pre):].lstrip('-')
                found.append((p['id'], s['id'], f"{key}-{rest}" if rest else key)); break
if not found:
    print(f"No Northflank service found for {name} (looked for: {', '.join(prefixes)}). Services in your account:")
    for x in allsvc: print('  ' + x)
    sys.exit(1)
for proj, sid, otel in found:
    want = {
        'OTEL_SERVICE_NAME': otel,
        'OTEL_EXPORTER_OTLP_ENDPOINT': os.environ['ENDPOINT'],
        'OTEL_EXPORTER_OTLP_PROTOCOL': 'http/protobuf' if stack == 'python' else 'http/json',
        'OTEL_EXPORTER_OTLP_HEADERS': 'Authorization=Bearer%20' + ing,
        'PRAMA_INGEST_TOKEN': ing,
        'PRAMA_APP_NAME': key,
        # Traces only: Northflank already gives the monitor CPU, memory and logs (keeps within the free plan).
        'OTEL_TRACES_EXPORTER': 'otlp', 'OTEL_METRICS_EXPORTER': 'none', 'OTEL_LOGS_EXPORTER': 'none',
        'OTEL_EXPORTER_OTLP_COMPRESSION': 'gzip',
        # Not "parentbased": Northflank's load balancer adds an unsampled trace header to requests.
        'OTEL_TRACES_SAMPLER': 'traceidratio', 'OTEL_TRACES_SAMPLER_ARG': '1.0',
    }
    if stack == 'node': want['OTEL_NODE_DISABLED_INSTRUMENTATIONS'] = 'fs,dns,net'
    cur = nf('GET', f"/projects/{proj}/services/{sid}/runtime-environment?show=this").get('data', {})
    env = dict(cur.get('runtimeEnvironment') or {})
    if stack == 'node':
        no = env.get('NODE_OPTIONS', '')
        req = '--require @opentelemetry/auto-instrumentations-node/register'
        want['NODE_OPTIONS'] = no if 'auto-instrumentations-node/register' in no else (no + ' ' + req).strip()
    changes = [k for k, v in want.items() if str(env.get(k, '')) != str(v)]
    print(f"\nService {proj} / {sid}  ->  OTEL_SERVICE_NAME={otel}")
    if not changes: print('  Already set. Nothing to change.'); continue
    for k in changes: print(f"  set {k} = {'(hidden)' if ('TOKEN' in k or 'HEADERS' in k) else want[k]}")
    env.update(want)
    print(f"  Other variables kept as they are: {len([k for k in env if k not in want])}")
    if os.environ['DRY'] == '1': print('  Dry run: nothing saved.'); continue
    if os.environ['YES'] == '1': ans = 'y'
    else:
        print('  Save these and restart the service? (y/n) ', end='', flush=True)
        try:
            with open('/dev/tty') as t: ans = t.readline().strip().lower()
        except OSError: ans = ''
    if ans not in ('y', 'yes'): print('  Skipped.'); continue
    body = {'runtimeEnvironment': env}
    if cur.get('runtimeFiles'): body['runtimeFiles'] = cur['runtimeFiles']
    r = nf('POST', f"/projects/{proj}/services/{sid}/runtime-environment", body)
    print(f"  Saved. Restarted: {r.get('data', {}).get('restartSuccessful')}")
print(f"\nDone. Data appears in Prama Monitor > Platforms > {name} within a few minutes of the app handling requests.")
if stack == 'python': print('Python apps also need the small Dockerfile change in PRAMA-DOCKER-CHANGES.md (once) for traces.')
if stack == 'node': print('Node apps also need: npm install @opentelemetry/api @opentelemetry/auto-instrumentations-node (once), then push.')
PY
