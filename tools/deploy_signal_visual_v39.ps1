param(
    [string]$Commit = "cf4c7547a3a8cd7c0e0ed36d388cc0021b1fbce8",
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$StageRoot = "C:\NEXUS_DEPLOY\_stage-signal-visual-v39-$Stamp"
$Repo = Join-Path $StageRoot "repo"
$Archive = Join-Path $StageRoot "release.zip"
$Release = Join-Path $StageRoot "release"
$Backup = Join-Path $Prod "_backup\signal-visual-v39-$Stamp"
$Python = Join-Path $Prod ".venv\Scripts\python.exe"
$Service = "NEXUS-AutoTrade-API"
$HealthUrl = "https://api.nexustrade.ir/miniapp/api/health"

$Files = @(
    "app\autotrade\api.py",
    "app\autotrade\broker_chart_fallback.py",
    "app\autotrade\unified_signal_visual_runtime.py",
    "app\market_candles.py",
    "mt5\NEXUS_MarketFeed\NEXUS_MarketFeed.mq5"
)

function Wait-PublicHealth {
    param([int]$Attempts = 30,[int]$DelaySeconds = 2)
    $Last = $null
    for ($i=1; $i -le $Attempts; $i++) {
        try {
            $R = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 10
            if ($R.StatusCode -eq 200 -and $R.Content -match '"ok"\s*:\s*true') {
                Write-Host "PUBLIC HEALTH: PASS attempt=$i"
                return
            }
            $Last = "HTTP $($R.StatusCode)"
        } catch {
            $Last = $_.Exception.Message
            Write-Warning "Health $i/$Attempts failed: $Last"
        }
        if ($i -lt $Attempts) { Start-Sleep -Seconds $DelaySeconds }
    }
    throw "Public API health did not become ready: $Last"
}

function Restore-Backup {
    Write-Warning "ROLLBACK START"
    foreach ($Rel in $Files) {
        $Saved = Join-Path $Backup $Rel
        if (Test-Path $Saved) {
            $Target = Join-Path $Prod $Rel
            New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
            Copy-Item $Saved $Target -Force
            Write-Host "RESTORED: $Rel"
        }
    }
    try {
        Restart-Service -Name $Service -Force
        Start-Sleep -Seconds 3
    } catch {
        Write-Warning "Rollback service restart failed: $($_.Exception.Message)"
    }
    Write-Warning "ROLLBACK COMPLETE"
}

if (-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }
if (-not (Test-Path $Python)) { throw "Production Python not found: $Python" }

New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null

Write-Host "=== 1. FETCH EXACT V39 COMMIT OUTSIDE PRODUCTION ==="
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

foreach ($Rel in $Files) {
    if (-not (Test-Path (Join-Path $Release $Rel))) { throw "Missing staged release file: $Rel" }
}

Write-Host "=== 2. SOURCE CONTRACT ==="
$Renderer = Get-Content (Join-Path $Release "app\autotrade\broker_chart_fallback.py") -Raw
$Runtime = Get-Content (Join-Path $Release "app\autotrade\unified_signal_visual_runtime.py") -Raw
$Api = Get-Content (Join-Path $Release "app\autotrade\api.py") -Raw
$Candles = Get-Content (Join-Path $Release "app\market_candles.py") -Raw
$Feed = Get-Content (Join-Path $Release "mt5\NEXUS_MarketFeed\NEXUS_MarketFeed.mq5") -Raw

foreach ($Marker in @('nexus-signal-minimal-v6','approved minimal NEXUS signal flash card','logo only','level_specs.append(("ENTRY", entry, _ENTRY))','level_specs.append(("SL", sl, _SL))')) {
    if (-not $Renderer.Contains($Marker)) { throw "Missing renderer marker: $Marker" }
}
if ($Renderer.Contains('"TRADE LEVELS"') -or $Renderer.Contains('"BROKER TRUTH"') -or $Renderer.Contains('"NEXUS SIGNAL"')) { throw "Minimal renderer still contains removed presentation panels/text" }
if (-not $Runtime.Contains('nexus-signal-minimal-v6')) { throw "Runtime V39 style marker missing" }
if (-not $Api.Contains('expected_fingerprint = signal_visual_fingerprint(row, expected_targets)')) { throw "Canonical fingerprint binding marker missing" }
if (-not $Api.Contains('DIAGNOSTIC_CHART_RECEIVED')) { throw "Diagnostic-only ChartAgent marker missing" }
foreach ($Marker in @('"M30": "30m"','"H4": "4h"')) { if (-not $Candles.Contains($Marker)) { throw "Market candle timeframe marker missing: $Marker" } }
foreach ($Marker in @('PERIOD_M30','PERIOD_H4','ENUM_TIMEFRAMES tfs[7]')) { if (-not $Feed.Contains($Marker)) { throw "MarketFeed timeframe marker missing: $Marker" } }
Write-Host "SOURCE CONTRACT: PASS"

Write-Host "=== 3. STAGING TEST GATE ==="
Push-Location $Release
try {
    & $Python -m py_compile "app\autotrade\api.py" "app\autotrade\broker_chart_fallback.py" "app\autotrade\unified_signal_visual_runtime.py" "app\market_candles.py"
    if ($LASTEXITCODE -ne 0) { throw "Python compile failed" }
    & $Python -m pytest "tests\test_broker_chart_fallback_v26.py" "tests\test_unified_signal_visual_v28.py" "tests\test_market_candles_and_publication_recovery.py" -q
    if ($LASTEXITCODE -ne 0) { throw "V39 staging tests failed" }
} finally {
    Pop-Location
}
Write-Host "STAGING TESTS: PASS"

Write-Host "=== 4. TARGETED BACKUP ==="
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

$Copied = $false
try {
    Write-Host "=== 5. TARGETED COPY ==="
    foreach ($Rel in $Files) {
        $Target = Join-Path $Prod $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
        Copy-Item (Join-Path $Release $Rel) $Target -Force
        Write-Host "DEPLOYED: $Rel"
    }
    $Copied = $true
    Write-Host "PRESERVED: .env / DB / Telegram bot / AutoTrade EA / T05 / T07 / production-only assets"

    Write-Host "=== 6. PRODUCTION IMPORT CONTRACT ==="
    Push-Location $Prod
    try {
        & $Python -c "from app.combined_api import app; from app.autotrade import broker_chart_fallback as r; from app.autotrade import unified_signal_visual_runtime as u; from app.market_candles import _tf; assert r._STYLE_VERSION == 'nexus-signal-minimal-v6'; assert u._STYLE_VERSION == 'nexus-signal-minimal-v6'; assert _tf('M30') == 'M30'; assert _tf('H4') == 'H4'; assert getattr(app.state,'nexus_unified_signal_visual_v37',False) is True; print('PRODUCTION_IMPORT: PASS')"
        if ($LASTEXITCODE -ne 0) { throw "Production import contract failed" }
    } finally {
        Pop-Location
    }

    Write-Host "=== 7. RESTART BACKEND ONLY ==="
    Restart-Service -Name $Service -Force
    $Deadline = (Get-Date).AddSeconds(45)
    do {
        Start-Sleep -Seconds 1
        $Svc = Get-Service -Name $Service
    } until ($Svc.Status -eq "Running" -or (Get-Date) -ge $Deadline)
    if ($Svc.Status -ne "Running") { throw "$Service did not return to Running" }
    Write-Host "SERVICE: RUNNING"
    Wait-PublicHealth

    Write-Host "=== 8. MARKETFEED STATUS ==="
    Write-Warning "Backend V39 is already healthy. MarketFeed compilation is handled separately by tools\compile_marketfeed_v39_runtime.ps1 so a compiler issue can never roll back a healthy backend deploy."

    Write-Host "NEXUS SIGNAL VISUAL V39 DEPLOY: PASS"
    Write-Host "Commit: $Commit"
    Write-Host "Style : nexus-signal-minimal-v6"
    Write-Host "Backup: $Backup"
} catch {
    Write-Warning ("DEPLOY FAILED: " + $_.Exception.Message)
    if ($Copied) { Restore-Backup }
    throw
}
