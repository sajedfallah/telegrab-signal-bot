$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Prod      = 'C:\NEXUS_V065_FINAL_TEST'
$Branch    = 'release/nexus-v0.6.5'
$OldSha    = 'f5739dd74a6da20cf56a13181f677c32894adb8f'
$TargetSha = '6d7aca3bf6def26bf0c933caea400d657cfb0537'
$ShortSha  = '6d7aca3'

$ApiSvc    = 'NEXUS-AutoTrade-API'
$BotSvc    = 'NEXUS-Telegram-Bot'
$CaddySvc  = 'NEXUS-Caddy'

$AllowedIncoming = @(
    'miniapp/assets/brand/nexus-landing-minimal-v9.svg',
    'miniapp/index.html',
    'miniapp/user-final-polish-v1.css',
    'miniapp/user-final-polish-v1.js',
    'tests/test_miniapp_landing_v5.py'
)

function Fail([string]$Message) {
    throw "STOP: $Message"
}

function Require-RunningService([string]$Name) {
    $svc = Get-Service $Name -ErrorAction Stop
    if ($svc.Status -ne 'Running') {
        Fail "$Name is not Running. Current status: $($svc.Status)"
    }
}

Set-Location $Prod

Write-Host ''
Write-Host '===== NEXUS USER MINI APP FINAL POLISH DEPLOY =====' -ForegroundColor Cyan

$CurrentBranch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { Fail 'Cannot read current git branch.' }
if ($CurrentBranch -ne $Branch) { Fail "Wrong branch: $CurrentBranch" }

$CurrentSha = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { Fail 'Cannot read current SHA.' }

Write-Host "CURRENT SHA : $CurrentSha"
if ($CurrentSha -ne $OldSha) {
    Fail "Unexpected Production SHA. Expected $OldSha but got $CurrentSha"
}

# Production services must already be healthy. This deploy does not restart them.
Require-RunningService $ApiSvc
Require-RunningService $BotSvc
Require-RunningService $CaddySvc

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/v1/autotrade/health' -TimeoutSec 8
    if ($health.ok -ne $true) { Fail 'API health returned non-OK state before deploy.' }
}
catch {
    Fail "API health check failed before deploy: $($_.Exception.Message)"
}

# Explicit refspec: update the remote-tracking branch, not FETCH_HEAD only.
git fetch origin "+refs/heads/$Branch`:refs/remotes/origin/$Branch" --prune
if ($LASTEXITCODE -ne 0) { Fail 'git fetch failed.' }

$RemoteSha = (git rev-parse "origin/$Branch").Trim()
if ($LASTEXITCODE -ne 0) { Fail 'Cannot resolve remote release SHA.' }

Write-Host "REMOTE SHA  : $RemoteSha"
Write-Host "TARGET SHA  : $TargetSha"

if ($RemoteSha -ne $TargetSha) {
    Fail "Remote Release SHA mismatch. Got $RemoteSha"
}

git merge-base --is-ancestor HEAD "origin/$Branch"
if ($LASTEXITCODE -ne 0) {
    Fail 'Release is not a clean fast-forward from current Production.'
}

$Incoming = @(
    git diff --name-only HEAD "origin/$Branch" |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ }
)

Write-Host ''
Write-Host 'INCOMING FILES:' -ForegroundColor Cyan
$Incoming | ForEach-Object { Write-Host "  $_" }

$Unexpected = @($Incoming | Where-Object { $_ -notin $AllowedIncoming })
if ($Unexpected.Count -gt 0) {
    Write-Host 'UNEXPECTED FILES:' -ForegroundColor Red
    $Unexpected | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Fail 'Incoming release contains files outside the approved final-polish scope.'
}

$MissingExpected = @($AllowedIncoming | Where-Object { $_ -notin $Incoming })
if ($MissingExpected.Count -gt 0) {
    Write-Host 'MISSING EXPECTED FILES:' -ForegroundColor Red
    $MissingExpected | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Fail 'Incoming release does not exactly match the approved final-polish scope.'
}

# Protect tracked and untracked local production work from being overwritten.
$LocalTracked = @()
$LocalTracked += @(git diff --name-only)
$LocalTracked += @(git diff --cached --name-only)
$LocalTracked = @(
    $LocalTracked |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ } |
    Select-Object -Unique
)

$LocalUntracked = @(
    git ls-files --others --exclude-standard |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ }
)

$Overlap = @(
    ($LocalTracked + $LocalUntracked) |
    Where-Object { $_ -in $Incoming } |
    Select-Object -Unique
)

if ($Overlap.Count -gt 0) {
    Write-Host 'LOCAL OVERLAP:' -ForegroundColor Red
    $Overlap | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Fail 'Local files overlap the incoming final-polish release.'
}

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup = "C:\NEXUS_BACKUPS\pre_user_final_polish_$Stamp"
New-Item -ItemType Directory -Path $Backup -Force | Out-Null

Copy-Item "$Prod\miniapp\index.html" "$Backup\index.html" -Force
if (Test-Path "$Prod\miniapp\user-theme-option3.css") {
    Copy-Item "$Prod\miniapp\user-theme-option3.css" "$Backup\user-theme-option3.css" -Force
}
if (Test-Path "$Prod\miniapp\assets\brand\nexus-landing-approved-v8.webp") {
    Copy-Item "$Prod\miniapp\assets\brand\nexus-landing-approved-v8.webp" "$Backup\nexus-landing-approved-v8.webp" -Force
}

Write-Host "BACKUP      : $Backup" -ForegroundColor Green

# Static-only fast-forward. No service stop/restart and no DB/MT5 operation.
git merge --ff-only "origin/$Branch"
if ($LASTEXITCODE -ne 0) { Fail 'Fast-forward merge failed.' }

$NewSha = (git rev-parse HEAD).Trim()
if ($NewSha -ne $TargetSha) {
    Fail "Production did not reach the expected SHA. Got $NewSha"
}

$IndexPath = "$Prod\miniapp\index.html"
$CssPath   = "$Prod\miniapp\user-final-polish-v1.css"
$JsPath    = "$Prod\miniapp\user-final-polish-v1.js"
$PosterPath = "$Prod\miniapp\assets\brand\nexus-landing-minimal-v9.svg"

foreach ($Path in @($IndexPath, $CssPath, $JsPath, $PosterPath)) {
    if (-not (Test-Path $Path)) { Fail "Required deployed file missing: $Path" }
}

$Index = Get-Content $IndexPath -Raw
$Css   = Get-Content $CssPath -Raw
$Js    = Get-Content $JsPath -Raw
$Poster = Get-Content $PosterPath -Raw

foreach ($Marker in @(
    'user-final-polish-v1.css?v=20260911-0340',
    'nexus-landing-minimal-v9.svg?v=20260911-0340',
    'user-final-polish-v1.js?v=20260911-0340'
)) {
    if (-not $Index.Contains($Marker)) { Fail "Index marker missing: $Marker" }
}

foreach ($Marker in @(
    'Vazirmatn',
    '[data-open-track-record]',
    '.home-v2-priority .home-attention-card',
    '.home-subscription-card'
)) {
    if (-not $Css.Contains($Marker)) { Fail "Final CSS marker missing: $Marker" }
}

foreach ($Marker in @(
    'placePerformanceAfterToday',
    "insertAdjacentElement('afterend', performance)"
)) {
    if (-not $Js.Contains($Marker)) { Fail "Final JS marker missing: $Marker" }
}

if (-not $Poster.Contains('data:image/webp;base64,')) {
    Fail 'Landing V9 SVG does not contain the embedded WebP artwork.'
}
if ((Get-Item $PosterPath).Length -lt 20000) {
    Fail 'Landing V9 asset is unexpectedly small.'
}

# Syntax-check the presentation JS when Node is available, without adding a new production dependency.
$Node = Get-Command node -ErrorAction SilentlyContinue
if ($Node) {
    & $Node.Source --check $JsPath
    if ($LASTEXITCODE -ne 0) { Fail 'user-final-polish-v1.js syntax check failed.' }
}

Write-Host 'STATIC FINAL : PASS' -ForegroundColor Green

# Public static verification with cache-busting.
$Base = 'https://api.nexustrade.ir/miniapp'
$IndexUrl  = "$Base/index.html?v=final-polish&build=$ShortSha"
$CssUrl    = "$Base/user-final-polish-v1.css?v=$ShortSha"
$JsUrl     = "$Base/user-final-polish-v1.js?v=$ShortSha"
$PosterUrl = "$Base/assets/brand/nexus-landing-minimal-v9.svg?v=$ShortSha"
$NoCacheHeaders = @{ 'Cache-Control'='no-cache'; 'Pragma'='no-cache' }

try {
    $PublicIndex = Invoke-WebRequest -Uri $IndexUrl -UseBasicParsing -Headers $NoCacheHeaders -TimeoutSec 20
    $PublicCss   = Invoke-WebRequest -Uri $CssUrl -UseBasicParsing -Headers $NoCacheHeaders -TimeoutSec 20
    $PublicJs    = Invoke-WebRequest -Uri $JsUrl -UseBasicParsing -Headers $NoCacheHeaders -TimeoutSec 20
    $PublicPoster = Invoke-WebRequest -Uri $PosterUrl -UseBasicParsing -Headers $NoCacheHeaders -TimeoutSec 20
}
catch {
    Fail "Public static verification request failed: $($_.Exception.Message)"
}

foreach ($Response in @($PublicIndex, $PublicCss, $PublicJs, $PublicPoster)) {
    if ($Response.StatusCode -ne 200) { Fail "Public static verification returned HTTP $($Response.StatusCode)" }
}

foreach ($Marker in @(
    'user-final-polish-v1.css?v=20260911-0340',
    'nexus-landing-minimal-v9.svg?v=20260911-0340',
    'user-final-polish-v1.js?v=20260911-0340'
)) {
    if (-not $PublicIndex.Content.Contains($Marker)) { Fail "Public index marker missing: $Marker" }
}

if (-not $PublicCss.Content.Contains('Vazirmatn')) { Fail 'Public final CSS is stale or missing.' }
if (-not $PublicCss.Content.Contains('[data-open-track-record]')) { Fail 'Public Performance CTA styling is missing.' }
if (-not $PublicJs.Content.Contains('placePerformanceAfterToday')) { Fail 'Public Home reorder JS is stale or missing.' }
if (-not $PublicPoster.Content.Contains('data:image/webp;base64,')) { Fail 'Public Landing V9 asset is stale or invalid.' }

Write-Host 'PUBLIC FINAL : PASS' -ForegroundColor Green

# Runtime services must remain untouched and healthy after the static deploy.
Require-RunningService $ApiSvc
Require-RunningService $BotSvc
Require-RunningService $CaddySvc

try {
    $healthAfter = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/v1/autotrade/health' -TimeoutSec 8
    if ($healthAfter.ok -ne $true) { Fail 'API health returned non-OK state after deploy.' }
}
catch {
    Fail "API health check failed after deploy: $($_.Exception.Message)"
}

Write-Host ''
Write-Host '==================================================' -ForegroundColor Green
Write-Host 'NEXUS USER MINI APP FINAL POLISH : DEPLOY PASS' -ForegroundColor Green
Write-Host '==================================================' -ForegroundColor Green
Write-Host "SHA       : $NewSha"
Write-Host "PUBLIC URL: $IndexUrl"
Write-Host "BACKUP    : $Backup"
Write-Host 'LANDING   : MINIMAL V9 VERIFIED'
Write-Host 'FONT      : VAZIRMATN UI OVERRIDE VERIFIED'
Write-Host 'SIGNALS   : PERFORMANCE CTA VERIFIED'
Write-Host 'HOME      : INNER RADII + ORDER VERIFIED'
Write-Host 'API       : UNCHANGED / HEALTHY'
Write-Host 'TELEGRAM  : UNCHANGED / RUNNING'
Write-Host 'CADDY     : UNCHANGED / RUNNING'
Write-Host 'ADMIN UI  : UNCHANGED'
Write-Host 'DB / MT5  : UNCHANGED'
