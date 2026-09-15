param(
    [Parameter(Mandatory=$true)]
    [string]$Commit,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$StageRoot = "C:\NEXUS_DEPLOY\_stage-publication-grace-v25-$Stamp"
$Repo = Join-Path $StageRoot "repo"
$Archive = Join-Path $StageRoot "release.zip"
$Release = Join-Path $StageRoot "release"
$Backup = Join-Path $Prod "_backup\publication-grace-v25-$Stamp"
$Rel = "app\autotrade\publication_recovery_runtime.py"
$TestRel = "tests\test_market_candles_and_publication_recovery.py"

function Wait-PublicApi {
    param([int]$Attempts = 30,[int]$DelaySeconds = 3)
    $Last = $null
    for ($i=1; $i -le $Attempts; $i++) {
        try {
            $R = Invoke-WebRequest "https://api.nexustrade.ir/openapi.json" -UseBasicParsing -TimeoutSec 15
            if ($R.StatusCode -eq 200) {
                Write-Host "OPENAPI READY attempt=$i bytes=$($R.RawContentLength)"
                return $true
            }
            $Last = "HTTP $($R.StatusCode)"
        } catch {
            $Last = $_.Exception.Message
            Write-Warning "API readiness $i/$Attempts failed: $Last"
        }
        if ($i -lt $Attempts) { Start-Sleep -Seconds $DelaySeconds }
    }
    throw "Public API did not become ready: $Last"
}

if (-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }
$Python = Join-Path $Prod ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Production Python not found: $Python" }

New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null

Write-Host "=== 1. FETCH EXACT V25 COMMIT ==="
git clone --filter=blob:none --no-checkout https://github.com/sajedfallah/telegrab-signal-bot.git $Repo
if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
git -C $Repo fetch origin feature/live-charts-v1
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
$Resolved = (git -C $Repo rev-parse $Commit).Trim()
Write-Host "Requested:" $Commit
Write-Host "Resolved :" $Resolved
if ($Resolved -ne $Commit) { throw "Exact commit verification failed" }
git -C $Repo archive --format=zip --output=$Archive $Commit
if ($LASTEXITCODE -ne 0) { throw "git archive failed" }
Expand-Archive -Path $Archive -DestinationPath $Release -Force

$Source = Join-Path $Release $Rel
$Test = Join-Path $Release $TestRel
if (-not (Test-Path $Source)) { throw "Staged publication recovery file missing" }
if (-not (Test-Path $Test)) { throw "Staged regression test missing" }

$Text = Get-Content $Source -Raw
foreach ($Marker in @(
    "_PUBLICATION_CHART_GRACE_SECONDS = 20",
    "CHART_GRACE_TIMEOUT",
    "publishing fallback while capture remains repairable"
)) {
    if (-not $Text.Contains($Marker)) { throw "Missing V25 marker: $Marker" }
}
Write-Host "SOURCE MARKERS: PASS"

Write-Host "`n=== 2. STAGING TEST GATE ==="
Push-Location $Release
try {
    & $Python -m py_compile $Rel
    if ($LASTEXITCODE -ne 0) { throw "Python compile failed" }
    & $Python -m pytest $TestRel -q
    if ($LASTEXITCODE -ne 0) { throw "Publication grace regression tests failed" }
} finally {
    Pop-Location
}
Write-Host "STAGING TESTS: PASS"

Write-Host "`n=== 3. BACKUP PRODUCTION FILE ==="
New-Item -ItemType Directory -Force -Path (Join-Path $Backup "app\autotrade") | Out-Null
$ProdFile = Join-Path $Prod $Rel
if (Test-Path $ProdFile) {
    Copy-Item $ProdFile (Join-Path $Backup $Rel) -Force
}
Write-Host "Backup:" $Backup

Write-Host "`n=== 4. TARGETED DEPLOY ==="
Copy-Item $Source $ProdFile -Force
$ProdText = Get-Content $ProdFile -Raw
if (-not $ProdText.Contains("_PUBLICATION_CHART_GRACE_SECONDS = 20")) {
    throw "Production V25 marker missing after copy"
}
Write-Host "DEPLOYED:" $Rel
Write-Host "PRESERVED: app\autotrade\api.py"
Write-Host "PRESERVED: Telegram bot"
Write-Host "PRESERVED: Trading EA / T05 / T07 / MarketFeed / ChartAgent"

Write-Host "`n=== 5. RESTART BACKEND ONLY ==="
Restart-Service -Name "NEXUS-AutoTrade-API" -Force
$Deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Seconds 1
    $Svc = Get-Service -Name "NEXUS-AutoTrade-API"
} until ($Svc.Status -eq "Running" -or (Get-Date) -ge $Deadline)
if ($Svc.Status -ne "Running") { throw "NEXUS-AutoTrade-API did not return to Running" }
Write-Host "SERVICE: RUNNING"
[void](Wait-PublicApi)

Write-Host "`n=== 6. RECENT WEB_ADMIN PUBLICATION STATE ==="
$DiagPy = Join-Path $StageRoot "recent_web_admin_publication_state.py"
@'
from app import db
import json

query = """
SELECT
    s.id,
    s.code,
    s.status,
    s.publication_stage,
    s.destination,
    s.free_message_id,
    s.vip_message_id,
    j.id AS job_id,
    j.status AS job_status,
    j.requested_at,
    j.error_text
FROM signals s
LEFT JOIN signal_chart_capture_jobs j
  ON j.id = (
      SELECT MAX(j2.id)
      FROM signal_chart_capture_jobs j2
      WHERE j2.signal_id = s.id
  )
WHERE s.issuer_type = 'WEB_ADMIN'
ORDER BY s.id DESC
LIMIT 8
"""

with db.conn() as con:
    rows = con.execute(query).fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
'@ | Set-Content -Path $DiagPy -Encoding UTF8

Push-Location $Prod
try {
    & $Python $DiagPy
    if ($LASTEXITCODE -ne 0) { throw "Recent WEB_ADMIN publication diagnostic failed" }
} finally {
    Pop-Location
}

Write-Host "`nPUBLICATION GRACE V25 DEPLOY: PASS"
Write-Host "Broker-confirmed WEB_ADMIN signals can no longer remain silent for the full chart TTL."
Write-Host "After 20s without a real chart, fallback publishes while the MT5 chart job remains repairable."
