// A small Windows PowerShell helper, generated with this site's address filled in.
// It finds .ics calendar files on the person's own computer, asks before doing anything,
// then adds them to THEIR iSift account. It never runs by itself: the person starts it.
const SCRIPT = String.raw`# iSift calendar helper for Windows
# Finds .ics calendar files on this computer (including the new Outlook's saved invitations)
# and, only if you say yes, adds them to YOUR iSift calendar. Nothing leaves this computer
# except the calendar entries, sent to your own iSift account over HTTPS.
param([switch]$Force)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Site = '__SITE__'
$Api  = $Site.TrimEnd('/') + '/api/v1'
$Dir  = Join-Path $env:LOCALAPPDATA 'iSift'
$Marker = Join-Path $Dir 'calendar-helper.done'
function Pause-Close { Read-Host 'Press Enter to close' | Out-Null }

if ((Test-Path $Marker) -and -not $Force) {
  Write-Host 'This helper has already been run on this computer.'
  Write-Host 'To run it again, start it with:  powershell -File isift-calendar-helper.ps1 -Force'
  Pause-Close; exit
}

Write-Host ''
Write-Host 'iSift calendar helper' -ForegroundColor Cyan
Write-Host ('Looking for .ics files under ' + $env:USERPROFILE + ' (this can take a minute)...')
$found = Get-ChildItem -Path $env:USERPROFILE -Recurse -Filter *.ics -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Length -gt 0 -and $_.Length -lt 20MB -and $_.FullName -notmatch '\\(Temp|node_modules|\.git)\\' }

$events = @{}; $zones = @{}; $used = 0
foreach ($f in $found) {
  try { $t = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 } catch { continue }
  if ($t -notmatch 'BEGIN:VCALENDAR') { continue }
  $n = 0
  foreach ($m in [regex]::Matches($t, '(?s)BEGIN:VTIMEZONE.*?END:VTIMEZONE')) {
    $tz = [regex]::Match($m.Value, '(?m)^TZID:(.+?)\r?$').Groups[1].Value
    if ($tz -and -not $zones.ContainsKey($tz)) { $zones[$tz] = $m.Value }
  }
  foreach ($m in [regex]::Matches($t, '(?s)BEGIN:VEVENT.*?END:VEVENT')) {
    $uid = [regex]::Match($m.Value, '(?m)^UID[^:]*:(.+?)\r?$').Groups[1].Value
    $rid = [regex]::Match($m.Value, '(?m)^RECURRENCE-ID[^:]*:(.+?)\r?$').Groups[1].Value
    $key = if ($uid) { $uid + '|' + $rid } else { [guid]::NewGuid().ToString() }
    if (-not $events.ContainsKey($key)) { $events[$key] = $m.Value; $n++ }
  }
  if ($n -gt 0) { $used++; Write-Host ('  ' + $f.FullName + '  (' + $n + ' event' + $(if ($n -ne 1) {'s'}) + ')') }
}

if ($events.Count -eq 0) {
  Write-Host 'No calendar events were found in any .ics file on this computer.' -ForegroundColor Yellow
  Write-Host 'You can add your calendar by link instead: iSift > Connections.'
  Pause-Close; exit
}

Write-Host ''
Write-Host ('Found ' + $events.Count + ' event(s) in ' + $used + ' file(s).')
$ok = Read-Host 'Add them to your iSift calendar? (Y/N)'
if ($ok -notmatch '^[Yy]') { Write-Host 'Nothing was sent.'; Pause-Close; exit }

$lines = @('BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//iSift//calendar helper//EN') + $zones.Values + $events.Values + @('END:VCALENDAR')
$crlf = [string][char]13 + [string][char]10
$merged = ($lines -join $crlf)
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$copy = Join-Path $Dir 'computer-calendar.ics'
[IO.File]::WriteAllText($copy, $merged, (New-Object Text.UTF8Encoding($false)))

$user = Read-Host 'Your iSift user ID or email'
$sec  = Read-Host 'Your iSift password' -AsSecureString
$pw   = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
try {
  $login = Invoke-RestMethod -Method Post -Uri ($Api + '/auth/local-login') -ContentType 'application/json' -Body (@{ username = $user; password = $pw } | ConvertTo-Json)
} catch {
  Write-Host 'Sign-in failed. Check your user ID and password.' -ForegroundColor Red
  Pause-Close; exit
}
$pw = $null

Add-Type -AssemblyName System.Net.Http
$client = New-Object System.Net.Http.HttpClient
$client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $login.access_token)
$mp = New-Object System.Net.Http.MultipartFormDataContent
$bytes = [Text.Encoding]::UTF8.GetBytes($merged)
$part = New-Object System.Net.Http.ByteArrayContent(,$bytes)
$part.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('text/calendar')
$mp.Add($part, 'file', 'computer-calendar.ics')
$resp = $client.PostAsync($Api + '/calendar/upload', $mp).Result
$body = $resp.Content.ReadAsStringAsync().Result
if ($resp.IsSuccessStatusCode) {
  try { Write-Host (($body | ConvertFrom-Json).message) -ForegroundColor Green } catch { Write-Host 'Done.' -ForegroundColor Green }
  New-Item -ItemType File -Force -Path $Marker | Out-Null
  Write-Host ('A copy of what was sent is saved at ' + $copy)
} else {
  Write-Host ('iSift did not accept the file (' + [int]$resp.StatusCode + '). ' + $body) -ForegroundColor Red
}
Pause-Close
`;
export function downloadWindowsHelper(origin: string) {
  const text = SCRIPT.replace('__SITE__', origin.replace(/'/g, ''));
  const blob = new Blob(['\ufeff' + text.replace(/\r?\n/g, '\r\n')], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'isift-calendar-helper.ps1';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
