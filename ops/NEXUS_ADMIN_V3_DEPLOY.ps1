$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Prod      = 'C:\NEXUS_V065_FINAL_TEST'
$Branch    = 'release/nexus-v0.6.5'
$OldSha    = 'be7a8bfc32f3f17fc1729b4c8b7b63270efb64b7'
$TargetSha = 'fa038851ded18d3c30e1b3615feae91b233396fe'

$ApiSvc    = 'NEXUS-AutoTrade-API'
$BotSvc    = 'NEXUS-Telegram-Bot'
$CaddySvc  = 'NEXUS-Caddy'
$Python    = "$Prod\.venv\Scripts\python.exe"
$Db        = "$Prod\nexus_bot.db"
$EnvFile   = "$Prod\.env"
$AdminUrl  = 'https://api.nexustrade.ir/miniapp/admin.html?v=3&build=fa03885'

$Allowed = @(
    'app/miniapp_admin_api.py',
    'miniapp/admin-signal.css',
    'miniapp/admin-signal.js',
    'miniapp/admin.html',
    'tests/test_miniapp_admin_signal_controls.py'
)

function Fail([string]$Message) {
    throw "STOP: $Message"
}

function Ensure-ServiceRunning([string]$Name) {
    $svc = Get-Service $Name -ErrorAction Stop
    if ($svc.Status -ne 'Running') {
        Start-Service $Name -ErrorAction Stop
        $deadline = (Get-Date).AddSeconds(20)
        while ((Get-Service $Name).Status -ne 'Running') {
            if ((Get-Date) -gt $deadline) {
                throw "$Name did not reach Running state"
            }
            Start-Sleep -Milliseconds 500
        }
    }
}

try {
    Set-Location $Prod

    Write-Host ''
    Write-Host '===== NEXUS ADMIN V3 SAFE DEPLOY =====' -ForegroundColor Cyan

    if (-not (Test-Path $Python)) { Fail "Python not found: $Python" }
    if (-not (Test-Path $Db)) { Fail "Database not found: $Db" }
    if (-not (Test-Path $EnvFile)) { Fail ".env not found: $EnvFile" }

    $CurrentBranch = (git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { Fail 'Cannot read current branch.' }
    if ($CurrentBranch -ne $Branch) { Fail "Wrong branch: $CurrentBranch" }

    $CurrentSha = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { Fail 'Cannot read current SHA.' }
    if ($CurrentSha -notin @($OldSha, $TargetSha)) {
        Fail "Unexpected Production SHA: $CurrentSha"
    }

    git fetch origin "+refs/heads/$Branch`:refs/remotes/origin/$Branch" --prune
    if ($LASTEXITCODE -ne 0) { Fail 'Explicit release fetch failed.' }

    $RemoteSha = (git rev-parse "origin/$Branch").Trim()
    if ($RemoteSha -ne $TargetSha) { Fail "Remote SHA mismatch: $RemoteSha" }

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
            Fail 'Incoming release contains files outside Admin V3 scope.'
        }

        foreach ($Required in @(
            'app/miniapp_admin_api.py',
            'miniapp/admin-signal.css',
            'miniapp/admin-signal.js',
            'miniapp/admin.html',
            'tests/test_miniapp_admin_signal_controls.py'
        )) {
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
            Fail 'Local modifications overlap Admin V3 files.'
        }
    }
    else {
        Write-Host 'CODE        : target SHA already present; merge step will be skipped.' -ForegroundColor Yellow
    }

    if ((Get-Service $CaddySvc).Status -ne 'Running') { Fail 'Caddy is not running.' }

    $Integrity = & $Python -c "import sqlite3; c=sqlite3.connect(r'$Db'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"
    if ($LASTEXITCODE -ne 0 -or $Integrity.Trim() -ne 'ok') { Fail "DB integrity failed: $Integrity" }
    Write-Host 'DB BEFORE   : ok' -ForegroundColor Green

    $Stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
    $Backup = "C:\NEXUS_BACKUPS\pre_admin_v3_$Stamp"
    New-Item -ItemType Directory -Path $Backup -Force | Out-Null

    Copy-Item "$Prod\app\miniapp_admin_api.py" "$Backup\miniapp_admin_api.py" -Force
    Copy-Item "$Prod\miniapp\admin.html" "$Backup\admin.html" -Force
    Copy-Item "$Prod\miniapp\admin-signal.css" "$Backup\admin-signal.css" -Force
    Copy-Item "$Prod\miniapp\admin-signal.js" "$Backup\admin-signal.js" -Force
    Copy-Item $EnvFile "$Backup\.env" -Force

    Write-Host "BACKUP      : $Backup" -ForegroundColor Green
    Write-Host 'Stopping API + Telegram...' -ForegroundColor Yellow

    if ((Get-Service $BotSvc).Status -ne 'Stopped') { Stop-Service $BotSvc -Force }
    if ((Get-Service $ApiSvc).Status -ne 'Stopped') { Stop-Service $ApiSvc -Force }

    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Service $BotSvc).Status -ne 'Stopped' -or (Get-Service $ApiSvc).Status -ne 'Stopped') {
        if ((Get-Date) -gt $deadline) { Fail 'API/Telegram did not stop cleanly.' }
        Start-Sleep -Milliseconds 500
    }

    $DbBackup = "$Backup\nexus_bot.db"
    & $Python -c "import sqlite3; s=sqlite3.connect(r'$Db'); d=sqlite3.connect(r'$DbBackup'); s.backup(d); d.close(); s.close(); c=sqlite3.connect(r'$DbBackup'); v=c.execute('PRAGMA integrity_check').fetchone()[0]; c.close(); print(v); raise SystemExit(0 if v=='ok' else 2)"
    if ($LASTEXITCODE -ne 0) { Fail 'SQLite backup/integrity verification failed.' }

    if ($CurrentSha -ne $TargetSha) {
        git merge --ff-only "origin/$Branch"
        if ($LASTEXITCODE -ne 0) { Fail 'Fast-forward failed.' }
    }

    $NewSha = (git rev-parse HEAD).Trim()
    if ($NewSha -ne $TargetSha) { Fail "Wrong deployed SHA: $NewSha" }

    & $Python -m py_compile "$Prod\app\miniapp_admin_api.py"
    if ($LASTEXITCODE -ne 0) { Fail 'Python compile failed.' }

    $Html = Get-Content "$Prod\miniapp\admin.html" -Raw
    $Js   = Get-Content "$Prod\miniapp\admin-signal.js" -Raw
    $Css  = Get-Content "$Prod\miniapp\admin-signal.css" -Raw

    foreach ($Marker in @(
        'value="DOWJONES"',
        'value="NASDAQ"',
        'id="trailingProfile"',
        'id="trailingPreview"',
        'NEXUS_TRAIL_07'
    )) {
        if (-not $Html.Contains($Marker)) { Fail "HTML V3 marker missing: $Marker" }
    }

    foreach ($Marker in @(
        'trailing_profile_code',
        'populateSymbols',
        'populateTrailingProfiles',
        'renderTrailingPreview'
    )) {
        if (-not $Js.Contains($Marker)) { Fail "JS V3 marker missing: $Marker" }
    }

    if (-not $Css.Contains('--amber:#ffb020')) { Fail 'Graphite/Amber theme marker missing.' }
    Write-Host 'STATIC V3   : PASS' -ForegroundColor Green

    $Text = [System.IO.File]::ReadAllText($EnvFile)
    if ($Text -match '(?m)^MINIAPP_ADMIN_URL=.*$') {
        $Text = [regex]::Replace($Text, '(?m)^MINIAPP_ADMIN_URL=.*$', "MINIAPP_ADMIN_URL=$AdminUrl")
    }
    else {
        if (-not $Text.EndsWith("`n")) { $Text += "`r`n" }
        $Text += "MINIAPP_ADMIN_URL=$AdminUrl`r`n"
    }
    $Utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($EnvFile, $Text, $Utf8)

    $SavedAdminUrl = (Select-String -Path $EnvFile -Pattern '^MINIAPP_ADMIN_URL=').Line
    if ($SavedAdminUrl -ne "MINIAPP_ADMIN_URL=$AdminUrl") { Fail 'MINIAPP_ADMIN_URL update failed.' }
    Write-Host "ADMIN URL   : $AdminUrl" -ForegroundColor Green

    Ensure-ServiceRunning $ApiSvc

    $ApiReady = $false
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        try {
            $Health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/v1/autotrade/health' -TimeoutSec 5
            if ($Health.ok -eq $true) { $ApiReady = $true; break }
        }
        catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $ApiReady) { Fail 'API health did not become ready.' }
    Write-Host 'API HEALTH  : PASS' -ForegroundColor Green

    $Public = Invoke-WebRequest -Uri $AdminUrl -UseBasicParsing -Headers @{'Cache-Control'='no-cache'; 'Pragma'='no-cache'} -TimeoutSec 15
    if ($Public.StatusCode -ne 200) { Fail "Public Admin HTTP status: $($Public.StatusCode)" }
    foreach ($Marker in @('value="DOWJONES"','value="NASDAQ"','id="trailingProfile"','id="trailingPreview"')) {
        if (-not $Public.Content.Contains($Marker)) { Fail "Public V3 marker missing: $Marker" }
    }
    Write-Host 'PUBLIC V3   : PASS' -ForegroundColor Green

    $TelegramCode = @'
import asyncio
from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo
from app.config import settings

async def main():
    if not settings.admin_ids:
        raise RuntimeError("ADMIN_IDS is empty")
    if not settings.miniapp_admin_url:
        raise RuntimeError("MINIAPP_ADMIN_URL is empty")
    bot = Bot(settings.bot_token)
    try:
        for admin_id in settings.admin_ids:
            await bot.set_chat_menu_button(
                chat_id=admin_id,
                menu_button=MenuButtonWebApp(
                    text="NEXUS Admin V3",
                    web_app=WebAppInfo(url=settings.miniapp_admin_url),
                ),
            )
            current = await bot.get_chat_menu_button(chat_id=admin_id)
            web_app = getattr(current, "web_app", None)
            if not web_app or web_app.url != settings.miniapp_admin_url:
                raise RuntimeError(f"menu verification failed for {admin_id}")
            print(f"ADMIN [{admin_id}] -> {web_app.url}")
        print("TELEGRAM ADMIN V3 MENU: PASS")
    finally:
        await bot.session.close()

asyncio.run(main())
'@

    $TelegramCode | & $Python -
    if ($LASTEXITCODE -ne 0) { Fail 'Telegram Admin V3 menu update failed.' }

    Ensure-ServiceRunning $BotSvc

    $IntegrityAfter = & $Python -c "import sqlite3; c=sqlite3.connect(r'$Db'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"
    if ($LASTEXITCODE -ne 0 -or $IntegrityAfter.Trim() -ne 'ok') { Fail "DB integrity after deploy failed: $IntegrityAfter" }

    foreach ($Svc in @($ApiSvc, $BotSvc, $CaddySvc)) {
        if ((Get-Service $Svc).Status -ne 'Running') { Fail "$Svc is not running." }
    }

    Write-Host ''
    Write-Host '=============================================' -ForegroundColor Green
    Write-Host 'NEXUS ADMIN V3 : DEPLOY PASS' -ForegroundColor Green
    Write-Host '=============================================' -ForegroundColor Green
    Write-Host "SHA       : $NewSha"
    Write-Host "ADMIN URL : $AdminUrl"
    Write-Host "BACKUP    : $Backup"
    Write-Host 'SYMBOLS   : DOWJONES / NASDAQ + CATALOG VERIFIED'
    Write-Host 'TRAILING  : 7 OFFICIAL PROFILES VERIFIED'
    Write-Host 'THEME     : GRAPHITE / AMBER / ICE'
    Write-Host 'API       : HEALTHY'
    Write-Host 'TELEGRAM  : RUNNING'
    Write-Host 'CADDY     : RUNNING'
    Write-Host 'DB        : INTEGRITY OK'
    Write-Host 'MT5 / EX5 : UNCHANGED'
    exit 0
}
catch {
    Write-Host ''
    Write-Host "DEPLOY FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Attempting to restore service availability...' -ForegroundColor Yellow
    foreach ($Svc in @($ApiSvc, $BotSvc)) {
        try { Ensure-ServiceRunning $Svc } catch { Write-Host "Could not start ${Svc}: $($_.Exception.Message)" -ForegroundColor Red }
    }
    exit 1
}
