param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"

$Commit = "e167900200d6898ac8bf3432c605891c7592ef2a"
$ArchiveUrl = "https://github.com/sajedfallah/telegrab-signal-bot/archive/$Commit.zip"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$MiniappRoot = Join-Path $Prod "miniapp"
$PreviewRoot = Join-Path $MiniappRoot "preview-v29"
$BackupRoot = Join-Path $Prod "_backup\miniapp-preview-v29-$Stamp"
$Zip = Join-Path $env:TEMP "nexus-preview-v29-$Stamp.zip"
$Extract = Join-Path $env:TEMP "nexus-preview-v29-$Stamp"

if(-not (Test-Path $MiniappRoot)) {
    throw "Production miniapp root not found: $MiniappRoot"
}

Write-Host "=== NEXUS ISOLATED VPS PREVIEW V29 ==="
Write-Host "Production miniapp:" $MiniappRoot
Write-Host "Preview target    :" $PreviewRoot
Write-Host "Source commit     :" $Commit

if(Test-Path $PreviewRoot) {
    New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
    Copy-Item $PreviewRoot (Join-Path $BackupRoot "preview-v29") -Recurse -Force
    Write-Host "Existing preview backup:" $BackupRoot
}

Remove-Item $Zip -Force -ErrorAction SilentlyContinue
Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "=== DOWNLOAD EXACT GITHUB SNAPSHOT ==="
Invoke-WebRequest $ArchiveUrl -UseBasicParsing -OutFile $Zip

New-Item -ItemType Directory -Force -Path $Extract | Out-Null
Expand-Archive -Path $Zip -DestinationPath $Extract -Force

$RepoRoot = Get-ChildItem $Extract -Directory | Select-Object -First 1
if(-not $RepoRoot) { throw "Extracted repository root not found" }

$SourceMiniapp = Join-Path $RepoRoot.FullName "miniapp"
if(-not (Test-Path $SourceMiniapp)) { throw "Source miniapp directory missing in archive" }

$SourceIndex = Join-Path $SourceMiniapp "index.html"
$SourcePreviewJs = Join-Path $SourceMiniapp "preview-fixtures-v29.js"
$SourcePreviewCss = Join-Path $SourceMiniapp "preview-fixtures-v29.css"

foreach($Required in @($SourceIndex,$SourcePreviewJs,$SourcePreviewCss)) {
    if(-not (Test-Path $Required)) { throw "Required preview file missing: $Required" }
}

$IndexText = [System.IO.File]::ReadAllText($SourceIndex)
$PreviewJsText = [System.IO.File]::ReadAllText($SourcePreviewJs)

foreach($Marker in @(
    "20260919-v30-aligned-depth1",
    "preview-fixtures-v29.js?v=20260919-preview-data1",
    "preview-fixtures-v29.css?v=20260919-preview-data1",
    "landing-v18.css?v=20260919-v29-stage1-candles-rg2",
    "signal-pnl-motion-v25.css?v=20260919-approved-vercel-landing-v28",
    "telegram-shell-v29.css?v=20260919-v29-stage1",
    "ui-depth-v30.css?v=20260919-aligned-depth1",
    "home-v2.js?v=20260919-aligned-depth1"
)) {
    if(-not $IndexText.Contains($Marker)) { throw "Source index missing marker: $Marker" }
}

if(-not $PreviewJsText.Contains("host === 'api.nexustrade.ir'")) {
    throw "Preview fixture does not allow isolated VPS preview host"
}
if(-not $PreviewJsText.Contains("location.pathname.startsWith('/miniapp/preview-v29/')")) {
    throw "Preview fixture does not enforce isolated VPS preview path"
}
if(-not $PreviewJsText.Contains("params.get('nexus_preview') === '1'")) {
    throw "Preview fixture does not require explicit nexus_preview=1"
}

Write-Host "=== DEPLOY TO ISOLATED SUBDIRECTORY ONLY ==="
if(Test-Path $PreviewRoot) {
    Remove-Item $PreviewRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PreviewRoot | Out-Null

Get-ChildItem $SourceMiniapp -Force | ForEach-Object {
    Copy-Item $_.FullName $PreviewRoot -Recurse -Force
}

$ProdIndex = Join-Path $MiniappRoot "index.html"
if(-not (Test-Path $ProdIndex)) { throw "Production index unexpectedly missing" }

$PreviewIndex = Join-Path $PreviewRoot "index.html"
if(-not (Test-Path $PreviewIndex)) { throw "Preview index missing after copy" }

$PreviewIndexText = [System.IO.File]::ReadAllText($PreviewIndex)
if(-not $PreviewIndexText.Contains("20260919-v30-aligned-depth1")) {
    throw "Preview index marker missing after deploy"
}

Write-Host "=== PUBLIC VERIFY ==="
$cb=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$PreviewUrl = "https://api.nexustrade.ir/miniapp/preview-v29/?nexus_preview=1&cb=$cb"

$Public = Invoke-WebRequest $PreviewUrl -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"}

if($Public.StatusCode -ne 200) {
    throw "Preview public URL returned status $($Public.StatusCode)"
}
if(-not $Public.Content.Contains("20260919-v30-aligned-depth1")) {
    throw "Public preview is not serving the expected build"
}
if(-not $Public.Content.Contains("preview-fixtures-v29.js?v=20260919-preview-data1")) {
    throw "Public preview fixture reference missing"
}
if(-not $Public.Content.Contains("ui-depth-v30.css?v=20260919-aligned-depth1")) {
    throw "Public preview depth layer missing"
}
if(-not $Public.Content.Contains("home-v2.js?v=20260919-aligned-depth1")) {
    throw "Public preview aligned Home script missing"
}

$FixturePublic = Invoke-WebRequest "https://api.nexustrade.ir/miniapp/preview-v29/preview-fixtures-v29.js?cb=$cb" -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"}

if(-not $FixturePublic.Content.Contains("location.pathname.startsWith('/miniapp/preview-v29/')")) {
    throw "Public preview fixture guard missing"
}

Remove-Item $Zip -Force -ErrorAction SilentlyContinue
Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "NEXUS VPS PREVIEW V29: PASS"
Write-Host "Production /miniapp root: UNCHANGED"
Write-Host "Preview folder:" $PreviewRoot
Write-Host "Preview URL:"
Write-Host "https://api.nexustrade.ir/miniapp/preview-v29/?nexus_preview=1"
Write-Host ""
Write-Host "No backend / Telegram / MT5 / Caddy restart required"
