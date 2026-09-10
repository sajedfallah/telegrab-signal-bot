$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Prod      = 'C:\NEXUS_V065_FINAL_TEST'
$Branch    = 'release/nexus-v0.6.5'
$OldSha    = 'fa038851ded18d3c30e1b3615feae91b233396fe'
$TargetSha = 'f5739dd74a6da20cf56a13181f677c32894adb8f'
$ApiSvc    = 'NEXUS-AutoTrade-API'
$BotSvc    = 'NEXUS-Telegram-Bot'
$CaddySvc  = 'NEXUS-Caddy'

$Allowed = @(
    'miniapp/index.html',
    'miniapp/user-theme-option3.css'
)

function Fail([string]$Message) {
    throw "STOP: $Message"
}

try {
    Set-Location $Prod
    Write-Host ''
    Write-Host '===== NEXUS USER OPTION 3 THEME DEPLOY =====' -ForegroundColor Cyan

    $CurrentBranch = (git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { Fail 'Cannot read current branch.' }
    if ($CurrentBranch -ne $Branch) { Fail "Wrong branch: $CurrentBranch" }

    $CurrentSha = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { Fail 'Cannot read current SHA.' }
    if ($CurrentSha -notin @($OldSha, $TargetSha)) { Fail "Unexpected current SHA: $CurrentSha" }

    git fetch origin "+refs/heads/$Branch`:refs/remotes/origin/$Branch" --prune
    if ($LASTEXITCODE -ne 0) { Fail 'Explicit release fetch failed.' }

    $RemoteSha = (git rev-parse "origin/$Branch").Trim()
    if ($RemoteSha -ne $TargetSha) { Fail "Remote Release SHA mismatch: $RemoteSha" }

    Write-Host "CURRENT SHA : $CurrentSha"
    Write-Host "REMOTE SHA  : $RemoteSha"
    Write-Host "TARGET SHA  : $TargetSha"

    if ($CurrentSha -ne $TargetSha) {
        git merge-base --is-ancestor HEAD "origin/$Branch"
        if ($LASTEXITCODE -ne 0) { Fail 'Release is not a clean fast-forward.' }

        $Incoming = @(
            git diff --name-only HEAD "origin/$Branch" |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
        )

        Write-Host ''
        Write-Host 'INCOMING FILES:' -ForegroundColor Cyan
        $Incoming | ForEach-Object { Write-Host "  $_" }

        $Unexpected = @($Incoming | Where-Object { $_ -notin $Allowed })
        if ($Unexpected.Count -gt 0) {
            $Unexpected | ForEach-Object { Write-Host "UNEXPECTED: $_" -ForegroundColor Red }
            Fail 'Incoming release contains files outside the User Theme scope.'
        }

        foreach ($Required in $Allowed) {
            if ($Required -notin $Incoming) { Fail "Required incoming file missing: $Required" }
        }

        $LocalModified = @(
            git diff --name-only |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
        )
        $Overlap = @($LocalModified | Where-Object { $_ -in $Incoming })
        if ($Overlap.Count -gt 0) {
            $Overlap | ForEach-Object { Write-Host "LOCAL CONFLICT: $_" -ForegroundColor Red }
            Fail 'Local modifications overlap User Theme files.'
        }
    }
    else {
        Write-Host 'CODE        : target SHA already present; merge step skipped.' -ForegroundColor Yellow
    }

    foreach ($Svc in @($ApiSvc,$BotSvc,$CaddySvc)) {
        if ((Get-Service $Svc -ErrorAction Stop).Status -ne 'Running') {
            Fail "$Svc is not running before theme deploy."
        }
    }

    $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $Backup = "C:\NEXUS_BACKUPS\pre_user_option3_theme_$Stamp"
    New-Item -ItemType Directory -Path $Backup -Force | Out-Null
    Copy-Item "$Prod\miniapp\index.html" "$Backup\index.html" -Force
    if (Test-Path "$Prod\miniapp\user-theme-option3.css") {
        Copy-Item "$Prod\miniapp\user-theme-option3.css" "$Backup\user-theme-option3.css" -Force
    }
    Write-Host "BACKUP      : $Backup" -ForegroundColor Green

    if ($CurrentSha -ne $TargetSha) {
        git merge --ff-only "origin/$Branch"
        if ($LASTEXITCODE -ne 0) { Fail 'Fast-forward failed.' }
    }

    $NewSha = (git rev-parse HEAD).Trim()
    if ($NewSha -ne $TargetSha) { Fail "Wrong deployed SHA: $NewSha" }

    $Index = Get-Content "$Prod\miniapp\index.html" -Raw
    $Theme = Get-Content "$Prod\miniapp\user-theme-option3.css" -Raw

    if (-not $Index.Contains('./user-theme-option3.css?v=20260911-0303')) {
        Fail 'User Mini App index does not load Option 3 theme.'
    }

    foreach ($Marker in @(
        '--bg:#080c12',
        '--accent:#06b6d4',
        '--accent2:#2563eb',
        '#f59e0b',
        'Carbon + Cobalt + Cyan + Amber'
    )) {
        if (-not $Theme.Contains($Marker)) { Fail "Theme marker missing: $Marker" }
    }

    $PublicIndexUrl = 'https://api.nexustrade.ir/miniapp/index.html?theme=option3&build=f5739dd'
    $PublicThemeUrl = 'https://api.nexustrade.ir/miniapp/user-theme-option3.css?v=20260911-0303'

    $PublicIndex = Invoke-WebRequest -Uri $PublicIndexUrl -UseBasicParsing -Headers @{'Cache-Control'='no-cache';'Pragma'='no-cache'} -TimeoutSec 15
    if ($PublicIndex.StatusCode -ne 200 -or -not $PublicIndex.Content.Contains('user-theme-option3.css?v=20260911-0303')) {
        Fail 'Public User Mini App is not serving Option 3 index.'
    }

    $PublicTheme = Invoke-WebRequest -Uri $PublicThemeUrl -UseBasicParsing -Headers @{'Cache-Control'='no-cache';'Pragma'='no-cache'} -TimeoutSec 15
    if ($PublicTheme.StatusCode -ne 200 -or -not $PublicTheme.Content.Contains('--accent2:#2563eb')) {
        Fail 'Public Option 3 theme CSS verification failed.'
    }

    foreach ($Svc in @($ApiSvc,$BotSvc,$CaddySvc)) {
        if ((Get-Service $Svc -ErrorAction Stop).Status -ne 'Running') {
            Fail "$Svc changed state during theme deploy."
        }
    }

    Write-Host ''
    Write-Host '=============================================' -ForegroundColor Green
    Write-Host 'NEXUS USER OPTION 3 THEME : DEPLOY PASS' -ForegroundColor Green
    Write-Host '=============================================' -ForegroundColor Green
    Write-Host "SHA       : $NewSha"
    Write-Host "BACKUP    : $Backup"
    Write-Host 'SCOPE     : index.html + user-theme-option3.css ONLY'
    Write-Host 'THEME     : CARBON / COBALT / CYAN / AMBER'
    Write-Host 'PUBLIC UI : VERIFIED'
    Write-Host 'API       : UNCHANGED / RUNNING'
    Write-Host 'TELEGRAM  : UNCHANGED / RUNNING'
    Write-Host 'CADDY     : UNCHANGED / RUNNING'
    Write-Host 'ADMIN UI  : UNCHANGED'
    Write-Host 'DB / MT5  : UNCHANGED'
    exit 0
}
catch {
    Write-Host ''
    Write-Host "DEPLOY FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'No service stop/restart was performed by this theme deploy.' -ForegroundColor Yellow
    exit 1
}
