param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912",
    [string]$SourceBackup = "C:\NEXUS_DEPLOY\v066-clean-20260912\_backup\signal-pnl-motion-v25-20260918-123744\miniapp\index.html",
    [string]$PublicBase = "https://api.nexustrade.ir/miniapp/"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$CurrentIndex = Join-Path $Prod "miniapp\index.html"
$PnlCss = Join-Path $Prod "miniapp\signal-pnl-motion-v25.css"
$SignalsJs = Join-Path $Prod "miniapp\signals-v2.js"
$RecoveryBackup = Join-Path $Prod "_backup\landing-recovery-v26-$Stamp\miniapp\index.html"
$BuildTag = "20260919-landing-pnl-v26"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if(-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }
if(-not (Test-Path $SourceBackup)) { throw "Approved pre-PnL landing backup not found: $SourceBackup" }
if(-not (Test-Path $CurrentIndex)) { throw "Current production index not found: $CurrentIndex" }
if(-not (Test-Path $PnlCss)) { throw "PnL motion CSS missing: $PnlCss" }
if(-not (Test-Path $SignalsJs)) { throw "Signals JS missing: $SignalsJs" }

$Source = [System.IO.File]::ReadAllText($SourceBackup)
if([string]::IsNullOrWhiteSpace($Source) -or -not $Source.Contains("<!doctype html>")) {
    throw "Backup index is invalid"
}

$Signals = [System.IO.File]::ReadAllText($SignalsJs)
$Css = [System.IO.File]::ReadAllText($PnlCss)

if(-not $Signals.Contains("if (status !== 'LIVE') return '';")) { throw "LIVE PnL gate missing from signals-v2.js" }
if(-not $Signals.Contains("IN_PROFIT") -or -not $Signals.Contains("IN_LOSS")) { throw "PnL state mapping missing from signals-v2.js" }
if(-not $Css.Contains("nexusPnlBorderSpinV25")) { throw "PnL animation marker missing from CSS" }

New-Item -ItemType Directory -Force -Path (Split-Path $RecoveryBackup -Parent) | Out-Null
Copy-Item $CurrentIndex $RecoveryBackup -Force

$Merged = $Source

$Merged = [regex]::Replace(
    $Merged,
    '(?im)^[ \t]*<link[^>]+signal-pnl-motion-v25\.css[^>]*>\s*\r?\n?',
    ''
)

$Merged = [regex]::Replace(
    $Merged,
    'signals-v2\.js\?v=[^"''<>\s]+',
    "signals-v2.js?v=$BuildTag"
)

if($Merged -notmatch 'signals-v2\.js\?v=') {
    throw "signals-v2.js reference not found in approved landing backup"
}

$PnlLink = '  <link rel="stylesheet" href="./signal-pnl-motion-v25.css?v=' + $BuildTag + '" />'
$HeadClose = $Merged.IndexOf("</head>", [System.StringComparison]::OrdinalIgnoreCase)
if($HeadClose -lt 0) { throw "</head> not found in approved landing backup" }
$Merged = $Merged.Insert($HeadClose, $PnlLink + [Environment]::NewLine)

if($Merged -notmatch 'name=["'']nexus-build["'']') {
    $HeadOpen = $Merged.IndexOf("<head>", [System.StringComparison]::OrdinalIgnoreCase)
    if($HeadOpen -lt 0) { throw "<head> not found" }
    $InsertAt = $HeadOpen + 6
    $Marker = [Environment]::NewLine + '  <meta name="nexus-build" content="' + $BuildTag + '" />'
    $Merged = $Merged.Insert($InsertAt, $Marker)
}

[System.IO.File]::WriteAllText($CurrentIndex, $Merged, $Utf8NoBom)

$Local = [System.IO.File]::ReadAllText($CurrentIndex)
if(-not $Local.Contains("signal-pnl-motion-v25.css?v=$BuildTag")) { throw "Merged CSS reference missing" }
if(-not $Local.Contains("signals-v2.js?v=$BuildTag")) { throw "Merged Signals JS reference missing" }
if(-not $Local.Contains($BuildTag)) { throw "Merged build marker missing" }

$SourceLanding = [regex]::Replace($Source, '(?s)<head>.*?</head>', '<head></head>')
$MergedLanding = [regex]::Replace($Merged, '(?s)<head>.*?</head>', '<head></head>')
$MergedLanding = [regex]::Replace($MergedLanding, 'signals-v2\.js\?v=[^"''<>\s]+', 'signals-v2.js?v=__CACHE__')
$SourceLanding = [regex]::Replace($SourceLanding, 'signals-v2\.js\?v=[^"''<>\s]+', 'signals-v2.js?v=__CACHE__')
if($MergedLanding -ne $SourceLanding) {
    throw "Landing body drift detected; recovery aborted"
}

$cb = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$LiveFile = Join-Path $env:TEMP "nexus-live-index-$Stamp.html"
Invoke-WebRequest ($PublicBase + "?cb=$cb") -UseBasicParsing -Headers @{
    "Cache-Control" = "no-cache"
    "Pragma" = "no-cache"
} -OutFile $LiveFile

$Live = [System.IO.File]::ReadAllText($LiveFile)
Remove-Item $LiveFile -Force -ErrorAction SilentlyContinue

if(-not $Live.Contains("signal-pnl-motion-v25.css?v=$BuildTag")) { throw "Public HTML missing PnL CSS ref" }
if(-not $Live.Contains("signals-v2.js?v=$BuildTag")) { throw "Public HTML missing Signals JS ref" }

Write-Host ""
Write-Host "NEXUS LANDING + PNL RECOVERY V26: PASS"
Write-Host "Landing source: $SourceBackup"
Write-Host "Current-index backup: $RecoveryBackup"
Write-Host "Build tag: $BuildTag"
Write-Host "Landing body: restored from approved pre-PnL production backup"
Write-Host "Signals PnL animation: preserved"
Write-Host "No backend/Telegram/MT5 restart required"
