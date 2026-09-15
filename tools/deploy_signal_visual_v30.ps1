param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Prod "_backup\signal-visual-v30-$Stamp"
$Python = Join-Path $Prod ".venv\Scripts\python.exe"

$Files = @(
    "app\autotrade\broker_chart_fallback.py",
    "app\autotrade\unified_signal_visual_runtime.py"
)

foreach ($Rel in $Files) {
    if (-not (Test-Path (Join-Path $SourceRoot $Rel))) { throw "Missing source file: $Rel" }
}
if (-not (Test-Path $Python)) { throw "Production Python not found" }

Write-Host "=== V30 SOURCE CONTRACT ==="
$Renderer = Get-Content (Join-Path $SourceRoot "app\autotrade\broker_chart_fallback.py") -Raw
$Runtime = Get-Content (Join-Path $SourceRoot "app\autotrade\unified_signal_visual_runtime.py") -Raw

foreach ($Marker in @(
    'nexus-clean-signal-v3',
    '_PRICE_TEXT = (255, 209, 102)',
    'for field in ("opened_at", "limit_activated_at", "issued_at", "created_at")',
    'AND bar_time<=?',
    'ENTRY_ANCHOR_BAR_MISSING',
    'line_start = min(width - 300, last_x +',
    'price_font = _font(11, False)'
)) {
    if (-not $Renderer.Contains($Marker)) { throw "Missing renderer marker: $Marker" }
}
if (-not $Runtime.Contains('nexus-clean-signal-v3')) { throw "Runtime V30 style marker missing" }
Write-Host "SOURCE CONTRACT: PASS"

Write-Host "=== V30 STAGING TESTS ==="
Push-Location $SourceRoot
try {
    & $Python -m py_compile `
      "app\autotrade\broker_chart_fallback.py" `
      "app\autotrade\unified_signal_visual_runtime.py" `
      "tools\send_signal_visual_preview_v29.py"
    if ($LASTEXITCODE -ne 0) { throw "Python compile failed" }

    & $Python -m pytest `
      "tests\test_broker_chart_fallback_v26.py" `
      "tests\test_telegram_anchor_guard_v27.py" `
      "tests\test_unified_signal_visual_v28.py" `
      "tests\test_ui_system_v29.py" `
      "tests\test_signal_visual_preview_v29.py" `
      -q
    if ($LASTEXITCODE -ne 0) { throw "V30 staging tests failed" }
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
Write-Host "PRESERVED: app\autotrade\api.py / app\combined_api.py / DB"
Write-Host "PRESERVED: Mini App V29 UI / Telegram lifecycle / Trading EA / T05 / T07 / MarketFeed / ChartAgent"

Push-Location $Prod
try {
    & $Python -c "from app.combined_api import app; from app.autotrade import broker_chart_fallback as r; from app.autotrade import unified_signal_visual_runtime as u; assert r._STYLE_VERSION == 'nexus-clean-signal-v3'; assert r._PRICE_TEXT == (255, 209, 102); assert u._STYLE_VERSION == 'nexus-clean-signal-v3'; assert app.state.nexus_unified_signal_visual_v28 is True; print('PRODUCTION_IMPORT: PASS')"
    if ($LASTEXITCODE -ne 0) { throw "Production import failed" }
} finally {
    Pop-Location
}

Restart-Service -Name "NEXUS-AutoTrade-API" -Force
Start-Sleep -Seconds 2
if ((Get-Service -Name "NEXUS-AutoTrade-API").Status -ne "Running") { throw "Backend service not running" }
Write-Host "SERVICE: RUNNING"

$Ready = $false
for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/openapi.json" -TimeoutSec 3
        if ($Response.StatusCode -eq 200 -and $Response.Content.Length -gt 1000) {
            Write-Host "OPENAPI READY attempt=$Attempt bytes=$($Response.Content.Length)"
            $Ready = $true
            break
        }
    } catch {
        Write-Warning "API readiness $Attempt/30 failed: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 1
}
if (-not $Ready) { throw "API did not become ready" }

Write-Host "SIGNAL VISUAL V30 DEPLOY: PASS"
