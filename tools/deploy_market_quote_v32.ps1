param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Prod "_backup\market-quote-v32-$Stamp"
$Python = Join-Path $Prod ".venv\Scripts\python.exe"

$Files = @(
    "app\market_candles.py",
    "app\autotrade\market_quote_runtime.py",
    "app\combined_api.py",
    "mt5\NEXUS_MarketFeed\NEXUS_MarketFeed.mq5",
    "tools\check_market_quote_v32.py",
    "tools\install_marketfeed_v32_runtime.ps1"
)

foreach ($Rel in $Files) {
    if (-not (Test-Path (Join-Path $SourceRoot $Rel))) { throw "Missing source file: $Rel" }
}
if (-not (Test-Path $Python)) { throw "Production Python not found" }

Write-Host "=== V32 SOURCE CONTRACT ==="
$Market = Get-Content (Join-Path $SourceRoot "app\market_candles.py") -Raw
$Runtime = Get-Content (Join-Path $SourceRoot "app\autotrade\market_quote_runtime.py") -Raw
$Combined = Get-Content (Join-Path $SourceRoot "app\combined_api.py") -Raw
$Feed = Get-Content (Join-Path $SourceRoot "mt5\NEXUS_MarketFeed\NEXUS_MarketFeed.mq5") -Raw

foreach ($Marker in @("mt5_market_quotes", "quote_time_ms", "MarketQuote")) {
    if (-not $Market.Contains($Marker)) { throw "Missing V32 market schema marker: $Marker" }
}
foreach ($Marker in @("MT5_MARKET_FEED_TICK", "mini.market_quote = market_quote", "FROM mt5_market_quotes")) {
    if (-not $Runtime.Contains($Marker)) { throw "Missing V32 runtime marker: $Marker" }
}
foreach ($Marker in @("SymbolInfoTick(broker_symbol,tick)", "tick.bid", "tick.ask", "tick.time_msc", "NEXUS-MARKET-FEED-1.1")) {
    if (-not $Feed.Contains($Marker)) { throw "Missing V32 MT5 feed marker: $Marker" }
}
if (-not $Combined.Contains("install_market_quote_runtime(app)")) { throw "V32 runtime not installed" }
if ($Combined.IndexOf("install_market_quote_runtime(app)") -gt $Combined.IndexOf("install_web_admin_market_entry_guard(app)")) {
    throw "V32 market quote runtime must install before V31 entry guard"
}
Write-Host "SOURCE CONTRACT: PASS"

Write-Host "=== V32 STAGING TESTS ==="
Push-Location $SourceRoot
try {
    & $Python -m py_compile `
      "app\market_candles.py" `
      "app\autotrade\market_quote_runtime.py" `
      "app\combined_api.py" `
      "tools\check_market_quote_v32.py"
    if ($LASTEXITCODE -ne 0) { throw "Python compile failed" }

    & $Python -m pytest `
      "tests\test_market_quote_runtime_v32.py" `
      "tests\test_web_admin_market_entry_truth_v31.py" `
      "tests\test_market_order_entry_deviation_policy.py" `
      -q
    if ($LASTEXITCODE -ne 0) { throw "V32 staging tests failed" }
} finally {
    Pop-Location
}
Write-Host "STAGING TESTS: PASS"

Write-Host "=== V32 FINAL ROUTE REGRESSION ==="
Push-Location $SourceRoot
try {
    & $Python -m pytest "tests\test_web_admin_market_entry_truth_v31_integration.py" -q
    if ($LASTEXITCODE -ne 0) { throw "V31/V32 final-route regression failed" }
} finally {
    Pop-Location
}
Write-Host "FINAL ROUTE REGRESSION: PASS"

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
Write-Host "PRESERVED: Trading Core EA / T05 / T07 / Telegram lifecycle / renderer / ChartAgent"

Push-Location $Prod
try {
    & $Python -c "from app.combined_api import app; assert app.state.nexus_market_quote_runtime_v32 is True; assert app.state.nexus_web_admin_market_entry_guard_v31 is True; print('PRODUCTION_IMPORT: PASS')"
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

Write-Host "V32 BACKEND + MARKETFEED SOURCE DEPLOY: PASS"
Write-Host "IMPORTANT: MT5 MarketFeed 1.1 source is staged only. Run tools\install_marketfeed_v32_runtime.ps1, then validate with tools\check_market_quote_v32.py."
