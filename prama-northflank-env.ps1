# Prama Monitor - set observability environment variables on Northflank for iSift
#
# Run from this repository's root folder in PowerShell:
#     .\prama-northflank-env.ps1            (asks before changing anything)
#     .\prama-northflank-env.ps1 -DryRun    (only shows what would change)
#     .\prama-northflank-env.ps1 -Yes       (saves without asking)
#
# It needs two tokens. Set them first in the same PowerShell window (they are not saved anywhere),
# or the script asks for them without showing what you type:
#     $env:NORTHFLANK_API_TOKEN = "..."    (Northflank > Account or Team settings > API > Tokens)
#     $env:PRAMA_INGEST_TOKEN   = "..."    (the monitor's INGEST_TOKEN; Accfino already uses it)
#
# What it does:
#   1. Finds this app's services in your Northflank account (see $Prefixes below).
#   2. Reads each service's current runtime variables.
#   3. Adds or updates only the Prama / OpenTelemetry variables and keeps every other variable as it is.
#   4. Saves them; Northflank restarts the service with the new variables.
param(
  [switch]$DryRun,
  [switch]$Yes,                 # save without asking
  [string]$Stack = "",          # python | node | static  (detected from the repository if empty)
  [string]$Endpoint = "https://monitor.prama-ai.workers.dev/api/otlp"
)
$ErrorActionPreference = "Stop"
$AppKey  = "isift"
$AppName = "iSift"
$Prefixes = @("isift")   # Northflank service names that belong to this app start with one of these
$Api     = "https://api.northflank.com/v1"

function Read-Secret([string]$prompt) {
  $s = Read-Host -Prompt $prompt -AsSecureString
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b).Trim() } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}
$NfToken = "$env:NORTHFLANK_API_TOKEN".Trim()
if (-not $NfToken) { $NfToken = Read-Secret "Northflank API token" }
$Ingest = "$env:PRAMA_INGEST_TOKEN".Trim()
if (-not $Ingest) { $Ingest = Read-Secret "Prama INGEST_TOKEN" }
if (-not $NfToken -or -not $Ingest) { throw "Both tokens are needed." }

# Detect the app type from the files in this folder.
if (-not $Stack) {
  if ((Test-Path requirements.txt) -or (Test-Path pyproject.toml) -or (Test-Path Pipfile)) { $Stack = "python" }
  elseif (Test-Path package.json) { $Stack = "node" }
  else { $Stack = "static" }
}
Write-Host "App: $AppName  (key: $AppKey, type: $Stack)"
if ($Stack -eq "static") {
  Write-Host "This repository looks like a static website (no requirements.txt or package.json)."
  Write-Host "Static sites need no Northflank variables: add the one script line from PRAMA-DOCKER-CHANGES.md to your HTML instead."
  Write-Host "If this repository does have a backend, run again with -Stack python or -Stack node."
  exit 0
}

$Headers = @{ Authorization = "Bearer $NfToken" }
function Nf([string]$method, [string]$path, $body = $null) {
  $req = @{ Method = $method; Uri = "$Api$path"; Headers = $Headers }
  if ($null -ne $body) { $req.ContentType = "application/json"; $req.Body = [Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 10 -Compress)) }
  return Invoke-RestMethod @req
}

# 1. Find the services.
$services = @()
$projects = (Nf GET "/projects?per_page=100").data.projects
foreach ($p in $projects) {
  $list = (Nf GET "/projects/$($p.id)/services?per_page=100").data.services
  foreach ($s in $list) {
    $id = ("" + $s.id).ToLower()
    foreach ($pre in $Prefixes) {
      if ($id -eq $pre -or $id.StartsWith("$pre-")) {
        $rest = $id.Substring($pre.Length).TrimStart('-')
        $services += [pscustomobject]@{ Project = $p.id; Id = $s.id; Name = $s.name; Otel = $(if ($rest) { "$AppKey-$rest" } else { $AppKey }) }
        break
      }
    }
  }
}
if (-not $services.Count) {
  Write-Host "No Northflank service found for $AppName (looked for: $($Prefixes -join ', ')). Services in your account:" -ForegroundColor Yellow
  foreach ($p in $projects) { (Nf GET "/projects/$($p.id)/services?per_page=100").data.services | ForEach-Object { Write-Host "  $($p.id) / $($_.id)" } }
  Write-Host "Check you are using the token of the Northflank account that runs $AppName." ; exit 1
}

# 2-4. For each service: read, merge, save.
foreach ($svc in $services) {
  $otelName = $svc.Otel
  $want = [ordered]@{
    OTEL_SERVICE_NAME            = $otelName
    OTEL_EXPORTER_OTLP_ENDPOINT  = $Endpoint
    OTEL_EXPORTER_OTLP_PROTOCOL  = $(if ($Stack -eq "python") { "http/protobuf" } else { "http/json" })
    OTEL_EXPORTER_OTLP_HEADERS   = "Authorization=Bearer%20$Ingest"
    PRAMA_INGEST_TOKEN           = $Ingest
    PRAMA_APP_NAME               = $AppKey
    # Traces only: Northflank already gives the monitor CPU, memory and logs (keeps within the free plan).
    OTEL_TRACES_EXPORTER         = "otlp"
    OTEL_METRICS_EXPORTER        = "none"
    OTEL_LOGS_EXPORTER           = "none"
    OTEL_EXPORTER_OTLP_COMPRESSION = "gzip"
    # Not "parentbased": Northflank's load balancer adds an unsampled trace header to requests.
    OTEL_TRACES_SAMPLER          = "traceidratio"
    OTEL_TRACES_SAMPLER_ARG      = "1.0"
  }
  if ($Stack -eq "node") { $want.OTEL_NODE_DISABLED_INSTRUMENTATIONS = "fs,dns,net" }

  $cur = (Nf GET "/projects/$($svc.Project)/services/$($svc.Id)/runtime-environment?show=this").data
  $env0 = [ordered]@{}
  if ($cur.runtimeEnvironment) { $cur.runtimeEnvironment.PSObject.Properties | ForEach-Object { $env0[$_.Name] = $_.Value } }
  if ($Stack -eq "node") {
    $req = "--require @opentelemetry/auto-instrumentations-node/register"
    $no = "" + $env0["NODE_OPTIONS"]
    $want.NODE_OPTIONS = $(if ($no -like "*auto-instrumentations-node/register*") { $no } else { ("$no $req").Trim() })
  }
  $changes = @()
  foreach ($k in $want.Keys) {
    if (("" + $env0[$k]) -ne ("" + $want[$k])) { $changes += $k; $env0[$k] = $want[$k] }
  }
  Write-Host ""
  Write-Host "Service $($svc.Project) / $($svc.Id)  ->  OTEL_SERVICE_NAME=$otelName" -ForegroundColor Cyan
  if (-not $changes.Count) { Write-Host "  Already set. Nothing to change."; continue }
  foreach ($k in $changes) {
    $shown = $(if ($k -match 'TOKEN|HEADERS') { "(hidden)" } else { $want[$k] })
    Write-Host "  set $k = $shown"
  }
  Write-Host "  Other variables kept as they are: $(($env0.Keys | Where-Object { $want.Keys -notcontains $_ }).Count)"
  if ($DryRun) { Write-Host "  Dry run: nothing saved."; continue }
  $ok = $(if ($Yes) { "y" } else { Read-Host "  Save these and restart the service? (y/n)" })
  if ($ok -notmatch '^(y|yes)$') { Write-Host "  Skipped."; continue }
  $body = @{ runtimeEnvironment = $env0 }
  if ($cur.runtimeFiles -and $cur.runtimeFiles.PSObject.Properties.Count) { $body.runtimeFiles = $cur.runtimeFiles }
  $r = Nf POST "/projects/$($svc.Project)/services/$($svc.Id)/runtime-environment" $body
  Write-Host "  Saved. Restarted: $($r.data.restartSuccessful)" -ForegroundColor Green
}
Write-Host ""
Write-Host "Done. Data appears in Prama Monitor > Platforms > $AppName within a few minutes of the app handling requests."
if ($Stack -eq "python") { Write-Host "Python apps also need the small Dockerfile change in PRAMA-DOCKER-CHANGES.md (once) for traces." }
if ($Stack -eq "node")   { Write-Host "Node apps also need: npm install @opentelemetry/api @opentelemetry/auto-instrumentations-node (once), then push." }
