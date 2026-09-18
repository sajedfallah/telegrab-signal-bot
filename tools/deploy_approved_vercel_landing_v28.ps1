param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"

$Commit = "13a5d5718478a8d6a1a964b378916a3e710448c8"
$RawBase = "https://raw.githubusercontent.com/sajedfallah/telegrab-signal-bot/$Commit"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Prod "_backup\approved-vercel-landing-v28-$Stamp"
$Stage = Join-Path $env:TEMP "nexus-approved-vercel-landing-v28-$Stamp"

$Files = @(
    "miniapp\index.html",
    "miniapp\landing-v18.css",
    "miniapp\landing-v5.js"
)

if(-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }

$Signals = Join-Path $Prod "miniapp\signals-v2.js"
$PnlCss = Join-Path $Prod "miniapp\signal-pnl-motion-v25.css"

if(-not (Test-Path $Signals)) { throw "Signals JS missing: $Signals" }
if(-not (Test-Path $PnlCss)) { throw "PnL CSS missing: $PnlCss" }

$SignalsText = [System.IO.File]::ReadAllText($Signals)
$PnlText = [System.IO.File]::ReadAllText($PnlCss)

if(-not $SignalsText.Contains("if (status !== 'LIVE') return '';")) {
    throw "Current production Signals JS does not contain LIVE PnL gate"
}
if(-not $PnlText.Contains("nexusPnlBorderSpinV25")) {
    throw "Current production PnL animation CSS marker missing"
}

New-Item -ItemType Directory -Force -Path $Stage | Out-Null

foreach($Rel in $Files) {
    $Url = "$RawBase/" + ($Rel -replace '\\','/')
    $Target = Join-Path $Stage $Rel
    New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
    Invoke-WebRequest $Url -UseBasicParsing -OutFile $Target
}

$IndexStage = [System.IO.File]::ReadAllText((Join-Path $Stage "miniapp\index.html"))
$CssStage = [System.IO.File]::ReadAllText((Join-Path $Stage "miniapp\landing-v18.css"))
$JsStage = [System.IO.File]::ReadAllText((Join-Path $Stage "miniapp\landing-v5.js"))

foreach($Marker in @(
    "20260919-approved-vercel-landing-v28",
    "nexus-landing-stage",
    "nexus-landing-chart",
    "nexus-enter-button",
    "landing-v18.css?v=20260919-approved-vercel-landing-v28",
    "landing-v5.js?v=20260919-approved-vercel-landing-v28",
    "signal-pnl-motion-v25.css?v=20260919-approved-vercel-landing-v28",
    "signals-v2.js?v=20260919-approved-vercel-landing-v28",
    "live-charts.js?v=20260914-livecharts-nav1"
)) {
    if(-not $IndexStage.Contains($Marker)) { throw "Staged index missing marker: $Marker" }
}

if($IndexStage.Contains("nexus-landing-poster-v6.webp")) {
    throw "Staged index still references old poster-v6"
}
if($IndexStage.Contains("nexus-landing-v18.jpg")) {
    throw "Staged index still references old V18 poster"
}
if(-not $CssStage.Contains("approved minimal chart/candlestick composition")) {
    throw "Approved Vercel landing CSS marker missing"
}
if($JsStage.Contains("nexus-landing-poster")) {
    throw "Approved landing lifecycle still contains poster fallback"
}

New-Item -ItemType Directory -Force -Path $Backup | Out-Null

foreach($Rel in $Files) {
    $Existing = Join-Path $Prod $Rel
    if(Test-Path $Existing) {
        $BackupFile = Join-Path $Backup $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $BackupFile -Parent) | Out-Null
        Copy-Item $Existing $BackupFile -Force
    }
}

foreach($Rel in $Files) {
    $Source = Join-Path $Stage $Rel
    $Target = Join-Path $Prod $Rel
    Copy-Item $Source $Target -Force
    Write-Host "DEPLOYED:" $Rel
}

$LiveIndex = [System.IO.File]::ReadAllText((Join-Path $Prod "miniapp\index.html"))

foreach($Marker in @(
    "nexus-landing-stage",
    "nexus-landing-chart",
    "nexus-enter-button",
    "signal-pnl-motion-v25.css?v=20260919-approved-vercel-landing-v28",
    "live-charts.js?v=20260914-livecharts-nav1"
)) {
    if(-not $LiveIndex.Contains($Marker)) { throw "Production index missing marker: $Marker" }
}

if($LiveIndex.Contains("nexus-landing-poster-v6.webp")) { throw "Production still references old poster-v6" }
if($LiveIndex.Contains("nexus-landing-v18.jpg")) { throw "Production still references old V18 poster" }

$cb=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$Public = Invoke-WebRequest "https://api.nexustrade.ir/miniapp/?cb=$cb" -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"}

foreach($Marker in @(
    "20260919-approved-vercel-landing-v28",
    "nexus-landing-stage",
    "nexus-landing-chart",
    "nexus-enter-button",
    "signal-pnl-motion-v25.css?v=20260919-approved-vercel-landing-v28"
)) {
    if(-not $Public.Content.Contains($Marker)) {
        throw "Public Mini App missing marker: $Marker"
    }
}

Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "NEXUS APPROVED POST-VERCEL LANDING V28: PASS"
Write-Host "Source commit:" $Commit
Write-Host "Backup:" $Backup
Write-Host "Landing: approved minimal chart/candlestick composition"
Write-Host "Old poster-v6 ref: REMOVED"
Write-Host "Old V18 image ref: REMOVED"
Write-Host "Signals PnL animation: PRESERVED"
Write-Host "Live Charts: PRESERVED"
Write-Host "No backend / MT5 / Telegram service restart required"
