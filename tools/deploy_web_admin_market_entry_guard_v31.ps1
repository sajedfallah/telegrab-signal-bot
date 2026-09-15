param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Prod "_backup\web-admin-market-entry-v31-$Stamp"
$Python = Join-Path $Prod ".venv\Scripts\python.exe"

$Files = @(
    "app\autotrade\web_admin_market_entry_guard.py",
    "app\combined_api.py"
)

foreach ($Rel in $Files) {
    if (-not (Test-Path (Join-Path $SourceRoot $Rel))) { throw "Missing source file: $Rel" }
}
if (-not (Test-Path $Python)) { throw "Production Python not found" }

Write-Host "=== V31 SOURCE CONTRACT ==="
$Guard = Get-Content (Join-Path $SourceRoot "app\autotrade\web_admin_market_entry_guard.py") -Raw
$Combined = Get-Content (Join-Path $SourceRoot "app\combined_api.py") -Raw
foreach ($Marker in @(
    '/miniapp/api/admin/signals',
    'market_quote',
    'spread * 3.0',
    'DEFERRED_NO_FRESH_QUOTE',
    'Refresh Market Price and publish again',
    'target_route.dependant.call = guarded_create_signal'
)) {
    if (-not $Guard.Contains($Marker)) { throw "Missing V31 guard marker: $Marker" }
}
if (-not $Combined.Contains('install_web_admin_market_entry_guard(app)')) {
    throw "V31 guard is not installed in combined_api"
}
if ($Combined.IndexOf('install_web_admin_market_entry_guard(app)') -lt $Combined.IndexOf('install_miniapp_execution_gate(app)')) {
    throw "V31 guard must wrap the final route AFTER Mini App execution bridge"
}
Write-Host "SOURCE CONTRACT: PASS"

Write-Host "=== V31 STAGING TESTS: STATIC + QUOTE CONTRACT ==="
Push-Location $SourceRoot
try {
    & $Python -m py_compile `
      "app\autotrade\web_admin_market_entry_guard.py" `
      "app\combined_api.py"
    if ($LASTEXITCODE -ne 0) { throw "Python compile failed" }

    # Keep this stage narrowly scoped to V31 and its direct quote/deviation dependencies.
    # The wider Mini App V14 suite includes unrelated historical asset cache-bust assertions
    # (for example landing-v5.css) that are intentionally obsolete after later UI releases.
    & $Python -m pytest `
      "tests\test_web_admin_market_entry_truth_v31.py" `
      "tests\test_miniapp_admin_v14.py::test_market_quote_fails_closed_without_bid_ask" `
      "tests\test_miniapp_admin_v14.py::test_market_quote_uses_fresh_authenticated_admin_bid_ask_only" `
      "tests\test_market_order_entry_deviation_policy.py" `
      -q
    if ($LASTEXITCODE -ne 0) { throw "V31 static/quote staging tests failed" }
} finally {
    Pop-Location
}
Write-Host "STATIC/QUOTE TESTS: PASS"

# Run the final-route integration suite in a fresh Python process. Importing
# combined_api intentionally mutates the shared FastAPI route stack; mixing it
# into legacy chart-first tests creates false failures because the current
# Production architecture is execution-first (chart job after MT5 receipt).
Write-Host "=== V31 STAGING TESTS: FINAL ROUTE INTEGRATION ==="
Push-Location $SourceRoot
try {
    & $Python -m pytest `
      "tests\test_web_admin_market_entry_truth_v31_integration.py" `
      -q
    if ($LASTEXITCODE -ne 0) { throw "V31 final-route integration tests failed" }
} finally {
    Pop-Location
}
Write-Host "FINAL ROUTE INTEGRATION: PASS"

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
Write-Host "PRESERVED: app\miniapp_admin_api.py"
Write-Host "PRESERVED: app\autotrade\api.py"
Write-Host "PRESERVED: app\autotrade\miniapp_execution_runtime.py"
Write-Host "PRESERVED: DB / Telegram lifecycle / renderer / Trading EA / T05 / T07 / MarketFeed / ChartAgent"

Push-Location $Prod
try {
    & $Python -c "from app.combined_api import app; assert app.state.nexus_web_admin_market_entry_guard_v31 is True; route=next(r for r in app.routes if getattr(r,'path',None)=='/miniapp/api/admin/signals' and 'POST' in (getattr(r,'methods',set()) or set())); assert route.dependant.call.__name__=='guarded_create_signal'; print('PRODUCTION_IMPORT: PASS')"
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

Write-Host "WEB_ADMIN MARKET ENTRY TRUTH V31 DEPLOY: PASS"
