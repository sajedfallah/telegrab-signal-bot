param(
    [Parameter(Mandatory=$true)]
    [string]$Commit,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$StageRoot = "C:\NEXUS_DEPLOY\_stage-broker-chart-v26-$Stamp"
$Repo = Join-Path $StageRoot "repo"
$Archive = Join-Path $StageRoot "release.zip"
$Release = Join-Path $StageRoot "release"
$Backup = Join-Path $Prod "_backup\broker-chart-v26-$Stamp"
$Python = Join-Path $Prod ".venv\Scripts\python.exe"

function Wait-PublicApi {
    param([int]$Attempts = 30,[int]$DelaySeconds = 3)
    $Last = $null
    for ($i=1; $i -le $Attempts; $i++) {
        try {
            $R = Invoke-WebRequest "https://api.nexustrade.ir/openapi.json" -UseBasicParsing -TimeoutSec 15
            if ($R.StatusCode -eq 200) {
                Write-Host "OPENAPI READY attempt=$i bytes=$($R.RawContentLength)"
                return
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
if (-not (Test-Path $Python)) { throw "Production Python not found: $Python" }
New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null

Write-Host "=== 1. FETCH EXACT V26 COMMIT ==="
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

$Files = @(
    "app\autotrade\broker_chart_fallback.py",
    "app\autotrade\publication_recovery_runtime.py",
    "tools\repair_signal_chart_v26.py"
)
foreach ($Rel in $Files) {
    if (-not (Test-Path (Join-Path $Release $Rel))) { throw "Missing staged file: $Rel" }
}

$Recovery = Get-Content (Join-Path $Release "app\autotrade\publication_recovery_runtime.py") -Raw
foreach ($Marker in @(
    "ensure_broker_chart_asset",
    "MT5_MARKET_FEED",
    "publication_broker_chart_signal_ids"
)) {
    if (-not $Recovery.Contains($Marker)) { throw "Missing V26 recovery marker: $Marker" }
}
$Fallback = Get-Content (Join-Path $Release "app\autotrade\broker_chart_fallback.py") -Raw
foreach ($Marker in @(
    "mt5_market_candles",
    "_MAX_FEED_AGE_SECONDS = 90",
    "BROKER_CHART_FALLBACK_GENERATED"
)) {
    if (-not $Fallback.Contains($Marker)) { throw "Missing V26 broker chart marker: $Marker" }
}
Write-Host "SOURCE MARKERS: PASS"

Write-Host "`n=== 2. STAGING TEST GATE ==="
Push-Location $Release
try {
    & $Python -m py_compile "app\autotrade\broker_chart_fallback.py" "app\autotrade\publication_recovery_runtime.py" "tools\repair_signal_chart_v26.py"
    if ($LASTEXITCODE -ne 0) { throw "Python compile failed" }
    & $Python -m pytest "tests\test_broker_chart_fallback_v26.py" "tests\test_market_candles_and_publication_recovery.py" -q
    if ($LASTEXITCODE -ne 0) { throw "V26 staging tests failed" }
} finally {
    Pop-Location
}
Write-Host "STAGING TESTS: PASS"

Write-Host "`n=== 3. BACKUP TARGETED PRODUCTION FILES ==="
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
foreach ($Rel in $Files) {
    $Existing = Join-Path $Prod $Rel
    if (Test-Path $Existing) {
        $Target = Join-Path $Backup $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
        Copy-Item $Existing $Target -Force
    }
}
Write-Host "Backup:" $Backup

Write-Host "`n=== 4. TARGETED DEPLOY ==="
foreach ($Rel in $Files) {
    $Source = Join-Path $Release $Rel
    $Target = Join-Path $Prod $Rel
    New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
    Copy-Item $Source $Target -Force
    Write-Host "DEPLOYED:" $Rel
}
Write-Host "PRESERVED: app\autotrade\api.py"
Write-Host "PRESERVED: Telegram bot"
Write-Host "PRESERVED: Trading EA / T05 / T07 / MarketFeed / ChartAgent"

Write-Host "`n=== 5. PRODUCTION IMPORT CHECK ==="
Push-Location $Prod
try {
    & $Python -c "from app.autotrade.broker_chart_fallback import ensure_broker_chart_asset; from app.autotrade.publication_recovery_runtime import install_publication_recovery; print('PRODUCTION_IMPORT: PASS')"
    if ($LASTEXITCODE -ne 0) { throw "Production import check failed" }
} finally {
    Pop-Location
}

Write-Host "`n=== 6. RESTART BACKEND ONLY ==="
Restart-Service -Name "NEXUS-AutoTrade-API" -Force
$Deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Seconds 1
    $Svc = Get-Service -Name "NEXUS-AutoTrade-API"
} until ($Svc.Status -eq "Running" -or (Get-Date) -ge $Deadline)
if ($Svc.Status -ne "Running") { throw "NEXUS-AutoTrade-API did not return to Running" }
Write-Host "SERVICE: RUNNING"
Wait-PublicApi

Write-Host "`nBROKER CHART FALLBACK V26 DEPLOY: PASS"
Write-Host "Priority is now ChartAgent screenshot -> fresh MT5 MarketFeed chart -> placeholder only as last resort."
Write-Host "No Telegram restart. No MT5 restart. No trading/execution files changed."
