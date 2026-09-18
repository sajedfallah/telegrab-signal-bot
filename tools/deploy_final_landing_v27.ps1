param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"

$Commit = "3f72476e77bf94e7daf72920b37af637bc4960ed"
$RawBase = "https://raw.githubusercontent.com/sajedfallah/telegrab-signal-bot/$Commit"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Prod "_backup\final-landing-v27-$Stamp"
$Stage = Join-Path $env:TEMP "nexus-final-landing-v27-$Stamp"

$Files = @(
    "miniapp\index.html",
    "miniapp\landing-v5.css",
    "miniapp\landing-v5.js"
)

if(-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }

$Poster = Join-Path $Prod "miniapp\assets\brand\nexus-landing-poster-v6.webp"
$Signals = Join-Path $Prod "miniapp\signals-v2.js"
$PnlCss = Join-Path $Prod "miniapp\signal-pnl-motion-v25.css"

if(-not (Test-Path $Poster)) { throw "Final landing poster missing: $Poster" }
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
$CssStage = [System.IO.File]::ReadAllText((Join-Path $Stage "miniapp\landing-v5.css"))
$JsStage = [System.IO.File]::ReadAllText((Join-Path $Stage "miniapp\landing-v5.js"))

foreach($Marker in @(
    "20260919-final-landing-v27",
    "nexus-landing-poster-v6.webp?v=20260919-final-landing-v27",
    "landing-v5.css?v=20260919-final-landing-v27",
    "landing-v5.js?v=20260919-final-landing-v27",
    "signal-pnl-motion-v25.css?v=20260919-final-landing-pnl-v27",
    "signals-v2.js?v=20260919-final-landing-pnl-v27",
    "live-charts.css?v=20260914-livecharts-nav1",
    "live-charts.js?v=20260914-livecharts-nav1"
)) {
    if(-not $IndexStage.Contains($Marker)) { throw "Staged index missing marker: $Marker" }
}

if(-not $CssStage.Contains(".nexus-landing-poster.is-ready")) {
    throw "Final Vercel landing CSS marker missing"
}
if(-not $JsStage.Contains("revealPoster")) {
    throw "Final Vercel landing JS marker missing"
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
if(-not $LiveIndex.Contains("nexus-landing-poster-v6.webp?v=20260919-final-landing-v27")) {
    throw "Production index did not receive final landing poster ref"
}
if(-not $LiveIndex.Contains("signal-pnl-motion-v25.css?v=20260919-final-landing-pnl-v27")) {
    throw "Production index lost PnL CSS ref"
}
if(-not $LiveIndex.Contains("live-charts.js?v=20260914-livecharts-nav1")) {
    throw "Production index lost Live Charts ref"
}

$cb=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$Public = Invoke-WebRequest "https://api.nexustrade.ir/miniapp/?cb=$cb" -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"}

foreach($Marker in @(
    "20260919-final-landing-v27",
    "nexus-landing-poster-v6.webp?v=20260919-final-landing-v27",
    "landing-v5.css?v=20260919-final-landing-v27",
    "landing-v5.js?v=20260919-final-landing-v27",
    "signal-pnl-motion-v25.css?v=20260919-final-landing-pnl-v27"
)) {
    if(-not $Public.Content.Contains($Marker)) {
        throw "Public Mini App missing marker: $Marker"
    }
}

$PosterCheck = Invoke-WebRequest "https://api.nexustrade.ir/miniapp/assets/brand/nexus-landing-poster-v6.webp?cb=$cb" -UseBasicParsing

if($PosterCheck.StatusCode -ne 200 -or $PosterCheck.RawContentLength -lt 100000) {
    throw "Final landing poster public check failed"
}

Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "NEXUS FINAL LANDING V27: PASS"
Write-Host "Source commit:" $Commit
Write-Host "Backup:" $Backup
Write-Host "Poster: nexus-landing-poster-v6.webp"
Write-Host "Signals PnL animation: PRESERVED"
Write-Host "Live Charts: PRESERVED"
Write-Host "No backend / MT5 / Telegram service restart required"
