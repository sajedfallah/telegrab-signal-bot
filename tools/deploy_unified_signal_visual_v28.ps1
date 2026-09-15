param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Prod "_backup\unified-visual-v28-$Stamp"
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

$Files = @(
    "app\autotrade\broker_chart_fallback.py",
    "app\autotrade\telegram_anchor_guard.py",
    "app\autotrade\unified_signal_visual_runtime.py",
    "app\combined_api.py"
)

foreach ($Rel in $Files) {
    if (-not (Test-Path (Join-Path $SourceRoot $Rel))) { throw "Missing source file: $Rel" }
}
if (-not (Test-Path $Python)) { throw "Production Python not found" }

Write-Host "=== V28 SOURCE CONTRACT ==="
$Renderer = Get-Content (Join-Path $SourceRoot "app\autotrade\broker_chart_fallback.py") -Raw
$Runtime = Get-Content (Join-Path $SourceRoot "app\autotrade\unified_signal_visual_runtime.py") -Raw
foreach ($Marker in @("nexus-clean-signal-v1","_ENTRY = (33, 150, 243)","_TP = (28, 218, 126)","_SL = (255, 82, 95)","line_end = 1180")) {
    if (-not $Renderer.Contains($Marker)) { throw "Missing renderer marker: $Marker" }
}
foreach ($Marker in @('MT5_ADMIN", "WEB_ADMIN','ensure_broker_chart_asset(canonical)','SIGNAL_VISUAL_CANONICALIZED')) {
    if (-not $Runtime.Contains($Marker)) { throw "Missing runtime marker: $Marker" }
}
Write-Host "SOURCE CONTRACT: PASS"

Write-Host "=== V28 STAGING TESTS ==="
Push-Location $SourceRoot
try {
    & $Python -m py_compile "app\autotrade\broker_chart_fallback.py" "app\autotrade\telegram_anchor_guard.py" "app\autotrade\unified_signal_visual_runtime.py" "app\combined_api.py"
    if ($LASTEXITCODE -ne 0) { throw "Python compile failed" }
    & $Python -m pytest "tests\test_broker_chart_fallback_v26.py" "tests\test_telegram_anchor_guard_v27.py" "tests\test_unified_signal_visual_v28.py" -q
    if ($LASTEXITCODE -ne 0) { throw "V28 staging tests failed" }
} finally {
    Pop-Location
}
Write-Host "STAGING TESTS: PASS"

Write-Host "=== BACKUP ==="
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

Write-Host "=== TARGETED COPY ==="
foreach ($Rel in $Files) {
    $Target = Join-Path $Prod $Rel
    New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
    Copy-Item (Join-Path $SourceRoot $Rel) $Target -Force
    Write-Host "DEPLOYED:" $Rel
}
Write-Host "PRESERVED: app\autotrade\api.py"
Write-Host "PRESERVED: Trading EA / T05 / T07 / MarketFeed / ChartAgent"

Push-Location $Prod
try {
    & $Python -c "from app.combined_api import app; assert app.state.nexus_unified_signal_visual_v28 is True; print('PRODUCTION_IMPORT: PASS')"
    if ($LASTEXITCODE -ne 0) { throw "Production import failed" }
} finally {
    Pop-Location
}

Restart-Service -Name "NEXUS-AutoTrade-API" -Force
$Deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Seconds 1
    $Svc = Get-Service -Name "NEXUS-AutoTrade-API"
} until ($Svc.Status -eq "Running" -or (Get-Date) -ge $Deadline)
if ($Svc.Status -ne "Running") { throw "Backend service not running" }
Write-Host "SERVICE: RUNNING"
Wait-PublicApi
Write-Host "UNIFIED SIGNAL VISUAL V28 DEPLOY: PASS"
