param(
    [string]$Commit = "6dde2b48f60fc2e294d5d7f0cc13bc4ba72bb719",
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/sajedfallah/telegrab-signal-bot.git"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Work = "C:\NEXUS_DEPLOY\_stage-text-only-signal-v45-$Stamp"
$Repo = Join-Path $Work "repo"
$Release = Join-Path $Work "release"
$Backup = Join-Path $Prod "_backup\text-only-signal-v45-$Stamp"
$Python = Join-Path $Prod ".venv\Scripts\python.exe"
$HealthUrl = "https://api.nexustrade.ir/miniapp/api/health"

$Files = @(
    "app\autotrade\api.py",
    "app\autotrade\unified_signal_visual_runtime.py",
    "app\autotrade\publication_consistency_runtime.py",
    "app\autotrade\publication_recovery_runtime.py",
    "app\miniapp_admin_api.py",
    "app\main.py",
    "mt5\NEXUS_AutoTrade_UI65\Core\NEXUS_AutoTrade_Core.mq5"
)

function Wait-Health {
    for($i=1; $i -le 30; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-RestMethod $HealthUrl -TimeoutSec 10
            if($r.ok -eq $true) { Write-Host "API HEALTH: PASS"; return }
        } catch {}
    }
    throw "API health failed"
}

if(-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }
if(-not (Test-Path $Python)) { throw "Production Python not found: $Python" }
New-Item -ItemType Directory -Force -Path $Work,$Release,$Backup | Out-Null

Write-Host "=== FETCH EXACT V45 COMMIT ==="
git clone --filter=blob:none --no-checkout $RepoUrl $Repo
if($LASTEXITCODE -ne 0) { throw "git clone failed" }
git -C $Repo fetch origin feature/live-charts-v1
if($LASTEXITCODE -ne 0) { throw "git fetch failed" }
$Resolved = (git -C $Repo rev-parse $Commit).Trim()
if($Resolved -ne $Commit) { throw "Exact commit verification failed" }

git -C $Repo archive $Commit app/autotrade/api.py app/autotrade/unified_signal_visual_runtime.py app/autotrade/publication_consistency_runtime.py app/autotrade/publication_recovery_runtime.py app/miniapp_admin_api.py app/main.py mt5/NEXUS_AutoTrade_UI65/Core/NEXUS_AutoTrade_Core.mq5 tests/test_broker_chart_fallback_v26.py tests/test_unified_signal_visual_v28.py tests/test_market_candles_and_publication_recovery.py | tar -xf - -C $Release
if($LASTEXITCODE -ne 0) { throw "git archive failed" }

Write-Host "=== CONTRACT CHECK ==="
$Api = Get-Content "$Release\app\autotrade\api.py" -Raw
$Unified = Get-Content "$Release\app\autotrade\unified_signal_visual_runtime.py" -Raw
$Recovery = Get-Content "$Release\app\autotrade\publication_recovery_runtime.py" -Raw
$Main = Get-Content "$Release\app\main.py" -Raw
$Core = Get-Content "$Release\mt5\NEXUS_AutoTrade_UI65\Core\NEXUS_AutoTrade_Core.mq5" -Raw
$pubStart = $Api.IndexOf("async def _publish_mt5_admin_signal_async")
$pubEnd = $Api.IndexOf("def _publish_mt5_admin_signal(", $pubStart)
if($pubStart -lt 0 -or $pubEnd -lt 0) { throw "Publisher block not found" }
$Publisher = $Api.Substring($pubStart, $pubEnd - $pubStart)
if(-not $Publisher.Contains("send_message(")) { throw "Text publisher marker missing" }
if($Publisher.Contains("send_photo(")) { throw "Photo publisher still present" }
if($Publisher.Contains("build_publication_signal_image")) { throw "Image renderer still present" }
if(-not $Publisher.Contains('"publication_mode": "TEXT_ONLY"')) { throw "TEXT_ONLY marker missing" }
$mainStart = $Main.IndexOf("async def _publish_one_channel")
$mainEnd = $Main.IndexOf("async def _publish_signal", $mainStart)
$MainPublisher = $Main.Substring($mainStart, $mainEnd - $mainStart)
if(-not $MainPublisher.Contains("send_message(") -or $MainPublisher.Contains("send_photo(")) { throw "Legacy publisher is not text-only" }
if($Unified.Substring($Unified.IndexOf("def install_unified_signal_visual")).Contains("ensure_broker_chart_asset(canonical)")) { throw "Visual wrapper still generates artwork" }
if(-not $Recovery.Contains('"PUBLICATION_TEXT_QUEUED"')) { throw "Text recovery marker missing" }
if(-not $Core.Contains("publication=TEXT_ONLY")) { throw "MT5 text-only marker missing" }
Write-Host "CONTRACT: PASS"

Write-Host "=== STAGING TESTS ==="
Push-Location $Release
try {
    & $Python -m py_compile app\autotrade\api.py app\autotrade\unified_signal_visual_runtime.py app\autotrade\publication_consistency_runtime.py app\autotrade\publication_recovery_runtime.py app\miniapp_admin_api.py app\main.py
    if($LASTEXITCODE -ne 0) { throw "Python compile failed" }
    & $Python -m pytest tests\test_broker_chart_fallback_v26.py tests\test_unified_signal_visual_v28.py tests\test_market_candles_and_publication_recovery.py -q
    if($LASTEXITCODE -ne 0) { throw "V45 tests failed" }
} finally { Pop-Location }
Write-Host "STAGING TESTS: PASS"

foreach($Rel in $Files) {
    $Current = Join-Path $Prod $Rel
    if(Test-Path $Current) {
        $Bak = Join-Path $Backup $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $Bak -Parent) | Out-Null
        Copy-Item $Current $Bak -Force
    }
}

$Copied = $false
try {
    foreach($Rel in $Files) {
        $Src = Join-Path $Release $Rel
        $Dst = Join-Path $Prod $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $Dst -Parent) | Out-Null
        Copy-Item $Src $Dst -Force
        Write-Host "DEPLOYED: $Rel"
    }
    $Copied = $true
    & $Python -m py_compile "$Prod\app\autotrade\api.py" "$Prod\app\autotrade\unified_signal_visual_runtime.py" "$Prod\app\autotrade\publication_consistency_runtime.py" "$Prod\app\autotrade\publication_recovery_runtime.py" "$Prod\app\miniapp_admin_api.py" "$Prod\app\main.py"
    if($LASTEXITCODE -ne 0) { throw "Production Python compile failed" }
    foreach($Service in @("NEXUS-AutoTrade-API","NEXUS-Telegram-Bot")) {
        if(Get-Service -Name $Service -ErrorAction SilentlyContinue) { Restart-Service -Name $Service -Force; Write-Host "RESTARTED: $Service" }
    }
    Wait-Health
} catch {
    if($Copied) {
        foreach($Rel in $Files) {
            $Bak = Join-Path $Backup $Rel
            if(Test-Path $Bak) { Copy-Item $Bak (Join-Path $Prod $Rel) -Force }
        }
        foreach($Service in @("NEXUS-AutoTrade-API","NEXUS-Telegram-Bot")) {
            if(Get-Service -Name $Service -ErrorAction SilentlyContinue) { Restart-Service -Name $Service -Force }
        }
        Write-Warning "BACKEND ROLLBACK COMPLETE"
    }
    throw
}

Write-Host "=== LIVE MT5 AUTOTRADE TEXT-ONLY UPDATE ==="
$TerminalId = "F768FD01673817E50AE451C8D34261DE"
$TerminalRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal\$TerminalId"
$LiveCore = Join-Path $TerminalRoot "MQL5\Experts\NEXUS_AutoTrade_UI65\Core\NEXUS_AutoTrade_Core.mq5"
$LiveEntry = Join-Path $TerminalRoot "MQL5\Experts\NEXUS_AutoTrade_UI65\NEXUS_AutoTrade_UI65.mq5"
$LiveEx5 = [System.IO.Path]::ChangeExtension($LiveEntry, ".ex5")
$LiveLog = [System.IO.Path]::ChangeExtension($LiveEntry, ".log")
$Mt5Backup = Join-Path $Backup "live-mt5"

if(-not (Test-Path $LiveCore)) {
    $Candidates = @(Get-ChildItem -Path (Join-Path $env:APPDATA "MetaQuotes\Terminal") -Filter "NEXUS_AutoTrade_Core.mq5" -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match "\\MQL5\\Experts\\NEXUS_AutoTrade_UI65\\Core\\NEXUS_AutoTrade_Core\.mq5$" })
    if($Candidates.Count -eq 1) {
        $LiveCore = $Candidates[0].FullName
        $LiveRoot = Split-Path (Split-Path $LiveCore -Parent) -Parent
        $LiveEntry = Join-Path $LiveRoot "NEXUS_AutoTrade_UI65.mq5"
        $LiveEx5 = [System.IO.Path]::ChangeExtension($LiveEntry, ".ex5")
        $LiveLog = [System.IO.Path]::ChangeExtension($LiveEntry, ".log")
    } else {
        throw "Expected exactly one live NEXUS_AutoTrade_Core.mq5; found $($Candidates.Count)"
    }
}
if(-not (Test-Path $LiveEntry)) { throw "Live NEXUS_AutoTrade_UI65.mq5 not found: $LiveEntry" }

New-Item -ItemType Directory -Force -Path $Mt5Backup | Out-Null
Copy-Item $LiveCore (Join-Path $Mt5Backup "NEXUS_AutoTrade_Core.mq5") -Force
if(Test-Path $LiveEx5) { Copy-Item $LiveEx5 (Join-Path $Mt5Backup "NEXUS_AutoTrade_UI65.ex5") -Force }
Copy-Item "$Prod\mt5\NEXUS_AutoTrade_UI65\Core\NEXUS_AutoTrade_Core.mq5" $LiveCore -Force
if(-not (Select-String -Path $LiveCore -Pattern "publication=TEXT_ONLY" -Quiet)) { throw "Live MT5 core text-only marker missing after copy" }

$Editors = @()
foreach($Base in @("C:\Program Files","C:\Program Files (x86)")) {
    if(Test-Path $Base) { $Editors += Get-ChildItem -Path $Base -Filter "metaeditor64.exe" -File -Recurse -ErrorAction SilentlyContinue }
}
$Editor = @($Editors | Sort-Object LastWriteTime -Descending -Unique | Select-Object -First 1)
if($Editor.Count -ne 1) { throw "MetaEditor64.exe not found" }
if(Test-Path $LiveLog) { Remove-Item $LiveLog -Force }
& $Editor[0].FullName "/compile:$LiveEntry" /log
$Deadline = (Get-Date).AddSeconds(120)
$SummarySeen = $false
$Errors = $null
$Warnings = $null
while((Get-Date) -lt $Deadline) {
    if(Test-Path $LiveLog) {
        $CompileText = Get-Content $LiveLog -Raw -ErrorAction SilentlyContinue
        if($CompileText -match "(?im)(\d+)\s+errors?,\s*(\d+)\s+warnings?") {
            $SummarySeen = $true
            $Errors = [int]$Matches[1]
            $Warnings = [int]$Matches[2]
            break
        }
    }
    Start-Sleep -Seconds 1
}
if(-not $SummarySeen -or $Errors -ne 0 -or -not (Test-Path $LiveEx5)) {
    Copy-Item (Join-Path $Mt5Backup "NEXUS_AutoTrade_Core.mq5") $LiveCore -Force
    if(Test-Path (Join-Path $Mt5Backup "NEXUS_AutoTrade_UI65.ex5")) { Copy-Item (Join-Path $Mt5Backup "NEXUS_AutoTrade_UI65.ex5") $LiveEx5 -Force }
    throw "MT5 AutoTrade V45 compile failed; live MT5 files restored"
}
Write-Host "MT5 AUTOTRADE COMPILE: PASS ($Errors errors, $Warnings warnings)"
Write-Warning "Reload/re-attach NEXUS_AutoTrade_UI65 once so the running EA stops local signal screenshot capture."

Write-Host ""
Write-Host "NEXUS TEXT-ONLY SIGNAL V45: PASS"
Write-Host "Commit: $Commit"
Write-Host "Telegram publication: TEXT_ONLY"
Write-Host "Backup: $Backup"