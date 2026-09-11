$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Prod      = 'C:\NEXUS_V065_FINAL_TEST'
$Branch    = 'release/nexus-v0.6.5'
$OldSha    = '6d7aca3bf6def26bf0c933caea400d657cfb0537'
$TargetSha = '6f55745907768fbd6f07a9e00111c5b0d90f4d4f'

$ApiSvc    = 'NEXUS-AutoTrade-API'
$BotSvc    = 'NEXUS-Telegram-Bot'
$CaddySvc  = 'NEXUS-Caddy'

$PublicUrl = 'https://api.nexustrade.ir/miniapp/index.html?v=landing-v10&build=6f55745'
$CssUrl    = 'https://api.nexustrade.ir/miniapp/landing-v5.css?v=20260911-0415'
$JsUrl     = 'https://api.nexustrade.ir/miniapp/landing-v5.js?v=20260911-0415'
$SvgUrl    = 'https://api.nexustrade.ir/miniapp/assets/brand/nexus-landing-minimal-v9.svg?v=20260911-0415'

$AllowedIncoming = @(
    'miniapp/index.html',
    'miniapp/landing-v5.css',
    'miniapp/landing-v5.js',
    'tests/test_miniapp_landing_v5.py'
)

function Fail([string]$Message) {
    throw "STOP: $Message"
}

function Assert-ServiceRunning([string]$Name) {
    $svc = Get-Service $Name -ErrorAction Stop
    if ($svc.Status -ne 'Running') {
        Fail "$Name is not running."
    }
}

Set-Location $Prod

Write-Host "`n===== NEXUS LANDING V10 ANDROID FIX DEPLOY =====" -ForegroundColor Cyan

$CurrentSha = (git rev-parse HEAD).Trim()

Write-Host "CURRENT SHA : $CurrentSha"
Write-Host "TARGET SHA  : $TargetSha"

if ($CurrentSha -ne $OldSha -and $CurrentSha -ne $TargetSha) {
    Fail "Unexpected Production SHA: $CurrentSha"
}

git fetch origin "+refs/heads/$Branch`:refs/remotes/origin/$Branch" --prune
if ($LASTEXITCODE -ne 0) { Fail 'Release fetch failed.' }

$RemoteSha = (git rev-parse "origin/$Branch").Trim()
Write-Host "REMOTE SHA  : $RemoteSha"

if ($RemoteSha -ne $TargetSha) {
    Fail "Remote release SHA mismatch: $RemoteSha"
}

Assert-ServiceRunning $ApiSvc
Assert-ServiceRunning $BotSvc
Assert-ServiceRunning $CaddySvc

if ($CurrentSha -eq $OldSha) {
    git merge-base --is-ancestor HEAD "origin/$Branch"
    if ($LASTEXITCODE -ne 0) { Fail 'Release is not fast-forward compatible.' }

    $Incoming = @(
        git diff --name-only HEAD "origin/$Branch" |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
    )

    Write-Host "`nINCOMING FILES:" -ForegroundColor Cyan
    $Incoming | ForEach-Object { Write-Host "  $_" }

    $Unexpected = @($Incoming | Where-Object { $_ -notin $AllowedIncoming })
    if ($Unexpected.Count -gt 0) {
        Write-Host "`nUNEXPECTED FILES:" -ForegroundColor Red
        $Unexpected | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        Fail 'Incoming release contains files outside Landing V10 scope.'
    }

    $LocalModified = @(
        @(git diff --name-only) + @(git diff --cached --name-only) |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ } |
        Sort-Object -Unique
    )

    $Overlap = @($LocalModified | Where-Object { $_ -in $Incoming })
    if ($Overlap.Count -gt 0) {
        Write-Host "`nLOCAL OVERLAP:" -ForegroundColor Red
        $Overlap | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        Fail 'Local tracked changes overlap Landing V10 files.'
    }

    $Stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
    $Backup = "C:\NEXUS_BACKUPS\pre_landing_v10_fix_$Stamp"
    New-Item -ItemType Directory -Path $Backup -Force | Out-Null

    Copy-Item "$Prod\miniapp\index.html" "$Backup\index.html" -Force
    Copy-Item "$Prod\miniapp\landing-v5.css" "$Backup\landing-v5.css" -Force
    Copy-Item "$Prod\miniapp\landing-v5.js" "$Backup\landing-v5.js" -Force

    Write-Host "BACKUP      : $Backup"

    git merge --ff-only "origin/$Branch"
    if ($LASTEXITCODE -ne 0) { Fail 'Fast-forward failed.' }
}
else {
    $Backup = '(already deployed; no new backup created)'
    Write-Host 'TARGET ALREADY PRESENT: verification-only run.' -ForegroundColor Yellow
}

$NewSha = (git rev-parse HEAD).Trim()
if ($NewSha -ne $TargetSha) {
    Fail "Wrong deployed SHA: $NewSha"
}

$Index = Get-Content "$Prod\miniapp\index.html" -Raw
$Css   = Get-Content "$Prod\miniapp\landing-v5.css" -Raw
$Js    = Get-Content "$Prod\miniapp\landing-v5.js" -Raw

foreach ($Marker in @(
    'data-direct-webp-source="./assets/brand/nexus-landing-minimal-v9.svg?v=20260911-0415"',
    './landing-v5.css?v=20260911-0415',
    './landing-v5.js?v=20260911-0415'
)) {
    if (-not $Index.Contains($Marker)) {
        Fail "Index marker missing: $Marker"
    }
}

foreach ($Marker in @(
    'object-fit: contain',
    'aspect-ratio: 480 / 852',
    'width: min(100vw, 56.338dvh)',
    'height: min(100dvh, 177.5vw)'
)) {
    if (-not $Css.Contains($Marker)) {
        Fail "Landing CSS marker missing: $Marker"
    }
}

foreach ($Marker in @(
    'extractEmbeddedWebp',
    "new Blob([bytes], { type: 'image/webp' })",
    'URL.createObjectURL(blob)',
    "poster.classList.add('is-ready')",
    "poster.classList.add('is-fallback')"
)) {
    if (-not $Js.Contains($Marker)) {
        Fail "Landing JS marker missing: $Marker"
    }
}

Write-Host 'STATIC FIX   : PASS' -ForegroundColor Green

$Headers = @{
    'Cache-Control' = 'no-cache'
    'Pragma'        = 'no-cache'
}

$Page = Invoke-WebRequest -Uri $PublicUrl -UseBasicParsing -Headers $Headers -TimeoutSec 20
if ($Page.StatusCode -ne 200) { Fail "Public Mini App HTTP $($Page.StatusCode)" }
if (-not $Page.Content.Contains('data-direct-webp-source=')) {
    Fail 'Public index does not expose the direct WebP source marker.'
}

$PublicCss = Invoke-WebRequest -Uri $CssUrl -UseBasicParsing -Headers $Headers -TimeoutSec 20
if (-not $PublicCss.Content.Contains('object-fit: contain')) {
    Fail 'Public Landing CSS is not V10.'
}

$PublicJs = Invoke-WebRequest -Uri $JsUrl -UseBasicParsing -Headers $Headers -TimeoutSec 20
if (-not $PublicJs.Content.Contains('extractEmbeddedWebp')) {
    Fail 'Public Landing JS is not V10.'
}

$PublicSvg = Invoke-WebRequest -Uri $SvgUrl -UseBasicParsing -Headers $Headers -TimeoutSec 20
if (-not $PublicSvg.Content.Contains('data:image/webp;base64,')) {
    Fail 'Approved Landing SVG source does not contain the embedded WebP.'
}

Assert-ServiceRunning $ApiSvc
Assert-ServiceRunning $BotSvc
Assert-ServiceRunning $CaddySvc

Write-Host 'PUBLIC V10   : PASS' -ForegroundColor Green
Write-Host ''
Write-Host '=============================================' -ForegroundColor Green
Write-Host 'NEXUS LANDING V10 ANDROID FIX : DEPLOY PASS' -ForegroundColor Green
Write-Host '=============================================' -ForegroundColor Green
Write-Host "SHA       : $NewSha"
Write-Host "PUBLIC URL: $PublicUrl"
Write-Host "BACKUP    : $Backup"
Write-Host 'RENDER    : DIRECT WEBP BLOB / SVG WRAPPER BYPASSED'
Write-Host 'FIT       : CONTAIN / 480x852 ARTBOARD'
Write-Host 'API       : UNCHANGED / RUNNING'
Write-Host 'TELEGRAM  : UNCHANGED / RUNNING'
Write-Host 'CADDY     : UNCHANGED / RUNNING'
Write-Host 'ADMIN UI  : UNCHANGED'
Write-Host 'DB / MT5  : UNCHANGED'
