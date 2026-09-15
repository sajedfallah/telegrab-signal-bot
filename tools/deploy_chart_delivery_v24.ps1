param(
    [Parameter(Mandatory=$true)]
    [string]$Commit,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912",
    [string]$TerminalChartAgentDir = ""
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Evidence = "C:\NEXUS_DEPLOY\_stage-evidence\chart-delivery-v24-$Commit.json"
$Backup = Join-Path $Prod "_backup\chart-delivery-v24-$Stamp"

function Assert-File([string]$Path,[string]$Label) {
    if (-not (Test-Path $Path)) { throw "$Label not found: $Path" }
}

function Find-MetaEditor {
    $Candidates = @(
        "$env:ProgramFiles\MetaTrader 5\metaeditor64.exe",
        "$env:ProgramFiles\MetaTrader 5\MetaEditor64.exe",
        "${env:ProgramFiles(x86)}\MetaTrader 5\metaeditor64.exe",
        "${env:ProgramFiles(x86)}\MetaTrader 5\MetaEditor64.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $Candidates) {
        $Candidates = Get-ChildItem "$env:ProgramFiles" -Filter "metaeditor64.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName -First 3
    }
    return ($Candidates | Select-Object -First 1)
}

function Resolve-ChartAgentDir {
    param([string]$Explicit)
    if ($Explicit) {
        Assert-File $Explicit "Terminal ChartAgent directory"
        return (Resolve-Path $Explicit).Path
    }

    $Roots = Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal" -Directory -ErrorAction SilentlyContinue
    $Hits = @()
    foreach ($Root in $Roots) {
        $Experts = Join-Path $Root.FullName "MQL5\Experts"
        if (-not (Test-Path $Experts)) { continue }
        $Files = Get-ChildItem $Experts -Filter "NEXUS_ChartAgent.mq5" -File -Recurse -ErrorAction SilentlyContinue
        foreach ($File in $Files) { $Hits += $File.Directory.FullName }
    }
    $Hits = @($Hits | Sort-Object -Unique)
    if ($Hits.Count -eq 0) {
        throw "No terminal NEXUS_ChartAgent.mq5 was found. Re-run with -TerminalChartAgentDir '<MQL5\Experts\...\NEXUS_ChartAgent folder>'."
    }
    if ($Hits.Count -gt 1) {
        Write-Host "Multiple ChartAgent directories found:" -ForegroundColor Yellow
        $Hits | ForEach-Object { Write-Host " - $_" }
        throw "Ambiguous terminal ChartAgent path. Re-run with -TerminalChartAgentDir explicitly."
    }
    return $Hits[0]
}

Write-Host "=== NEXUS CHART DELIVERY V24 PRODUCTION DEPLOY ==="
Write-Host "Commit :" $Commit
Write-Host "Prod   :" $Prod
Write-Host "Policy : exact staged evidence + targeted copy only"

Assert-File $Prod "Production runtime"
Assert-File $Evidence "Mandatory staging evidence"

Write-Host "`n=== 1. VERIFY STAGING EVIDENCE ==="
$E = Get-Content $Evidence -Raw | ConvertFrom-Json
if ([string]$E.commit -ne $Commit) { throw "Evidence commit mismatch" }
if (-not $E.tests_pass) { throw "Evidence says pytest failed" }
if (-not $E.chartagent_patch_pass) { throw "Evidence says ChartAgent patch failed" }
if (-not $E.mq5_compile_pass) { throw "Evidence says MQ5 compile failed" }
if (-not $E.repair_claim_bridge_pass) { throw "Evidence says post-fallback repair claim bridge failed" }
if ($E.production_changed) { throw "Invalid staging evidence: production_changed must be false" }
$Release = [string]$E.release
$StageEx5 = [string]$E.compiled_ex5
Assert-File $Release "Staged release"
Assert-File $StageEx5 "Staged compiled ChartAgent EX5"

$Required = @(
    "app\autotrade\chart_delivery_guard.py",
    "app\autotrade\chart_repair_claim_runtime.py",
    "app\combined_api.py",
    "miniapp\admin-positions-v24.css",
    "miniapp\vazirmatn.css",
    "tools\diagnose_chart_delivery_v24.ps1",
    "mt5\NEXUS_ChartAgent\NEXUS_ChartAgent.mq5"
)
foreach ($Rel in $Required) {
    Assert-File (Join-Path $Release $Rel) "Staged file $Rel"
}

# Hard safety: never deploy canonical api.py because Production may contain an
# emergency hotfix that is intentionally preserved by the additive V24 guard.
if ($Required -contains "app\autotrade\api.py") {
    throw "SAFETY VIOLATION: app/autotrade/api.py must not be deployed by V24"
}
Write-Host "STAGING EVIDENCE: PASS"

Write-Host "`n=== 2. RESOLVE TERMINAL / METAEDITOR ==="
$AgentDir = Resolve-ChartAgentDir -Explicit $TerminalChartAgentDir
$TerminalMq5 = Join-Path $AgentDir "NEXUS_ChartAgent.mq5"
$TerminalEx5 = Join-Path $AgentDir "NEXUS_ChartAgent.ex5"
$MetaEditor = Find-MetaEditor
if (-not $MetaEditor) { throw "MetaEditor64.exe not found" }
Write-Host "ChartAgent dir:" $AgentDir
Write-Host "MetaEditor    :" $MetaEditor

Write-Host "`n=== 3. BACKUP TARGETED PRODUCTION FILES ==="
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
$ProdTargets = @(
    "app\autotrade\chart_delivery_guard.py",
    "app\autotrade\chart_repair_claim_runtime.py",
    "app\combined_api.py",
    "miniapp\admin-positions-v24.css",
    "miniapp\vazirmatn.css",
    "tools\diagnose_chart_delivery_v24.ps1",
    "mt5\NEXUS_ChartAgent\NEXUS_ChartAgent.mq5"
)
foreach ($Rel in $ProdTargets) {
    $Source = Join-Path $Prod $Rel
    if (Test-Path $Source) {
        $Target = Join-Path $Backup $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
        Copy-Item $Source $Target -Force
    }
}
$TerminalBackup = Join-Path $Backup "terminal-chart-agent"
New-Item -ItemType Directory -Force -Path $TerminalBackup | Out-Null
if (Test-Path $TerminalMq5) { Copy-Item $TerminalMq5 (Join-Path $TerminalBackup "NEXUS_ChartAgent.mq5") -Force }
if (Test-Path $TerminalEx5) { Copy-Item $TerminalEx5 (Join-Path $TerminalBackup "NEXUS_ChartAgent.ex5") -Force }
Write-Host "Backup:" $Backup

Write-Host "`n=== 4. TARGETED BACKEND + UI DEPLOY ==="
foreach ($Rel in @(
    "app\autotrade\chart_delivery_guard.py",
    "app\autotrade\chart_repair_claim_runtime.py",
    "app\combined_api.py",
    "miniapp\admin-positions-v24.css",
    "miniapp\vazirmatn.css",
    "tools\diagnose_chart_delivery_v24.ps1",
    "mt5\NEXUS_ChartAgent\NEXUS_ChartAgent.mq5"
)) {
    $Source = Join-Path $Release $Rel
    $Target = Join-Path $Prod $Rel
    New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
    Copy-Item $Source $Target -Force
    Write-Host "DEPLOYED:" $Rel
}
Write-Host "PRESERVED: app\autotrade\api.py (NOT COPIED)"

Write-Host "`n=== 5. DEPLOY + COMPILE SCREENSHOT-ONLY CHARTAGENT ==="
$PatchedMq5 = Join-Path $Release "mt5\NEXUS_ChartAgent\NEXUS_ChartAgent.mq5"
Copy-Item $PatchedMq5 $TerminalMq5 -Force
$CompileLog = Join-Path $Backup "metaeditor-production-v24.log"
$Psi = New-Object System.Diagnostics.ProcessStartInfo
$Psi.FileName = $MetaEditor
$Psi.Arguments = "/compile:`"$TerminalMq5`" /log:`"$CompileLog`""
$Psi.UseShellExecute = $false
$Process = [System.Diagnostics.Process]::Start($Psi)
if (-not $Process.WaitForExit(120000)) {
    try { $Process.Kill() } catch {}
    throw "Production ChartAgent compile timed out"
}
Start-Sleep -Milliseconds 900
Assert-File $CompileLog "Production MetaEditor log"
$CompileText = Get-Content $CompileLog -Raw
Write-Host $CompileText
if ($CompileText -notmatch '(?i)0\s+errors?') { throw "Production ChartAgent compile did not report 0 errors" }
Assert-File $TerminalEx5 "Production ChartAgent EX5"
$Mq5Text = Get-Content $TerminalMq5 -Raw
foreach ($Marker in @(
    "0.6.5-chart-agent-reliability-v24",
    "SCALE_VISIBLE_RANGE_CONFIRMED",
    "SCALE_FIXED_RANGE_CONFIRMED",
    "PostWithRetry",
    "SCREENSHOT_UPLOAD_CONFIRMED"
)) {
    if (-not $Mq5Text.Contains($Marker)) { throw "Production ChartAgent missing V24 marker: $Marker" }
}
Write-Host "CHARTAGENT COMPILE: PASS"

Write-Host "`n=== 6. RESTART BACKEND ONLY ==="
$Service = Get-Service -Name "NEXUS-AutoTrade-API" -ErrorAction Stop
Restart-Service -Name $Service.Name -Force
$Deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Seconds 1
    $Service = Get-Service -Name "NEXUS-AutoTrade-API"
} until ($Service.Status -eq 'Running' -or (Get-Date) -ge $Deadline)
if ($Service.Status -ne 'Running') { throw "NEXUS-AutoTrade-API did not return to Running" }
Write-Host "SERVICE: RUNNING"
Write-Host "Telegram bot restart: NO"
Write-Host "MT5 terminal restart : NO"
Write-Host "Trading EA/T05/T07   : UNTOUCHED"
Write-Host "MarketFeed           : UNTOUCHED"

Write-Host "`n=== 7. PUBLIC / HEALTH VERIFY ==="
$OpenApi = Invoke-WebRequest "https://api.nexustrade.ir/openapi.json" -UseBasicParsing -TimeoutSec 20
if ($OpenApi.StatusCode -ne 200) { throw "OpenAPI health failed" }
Write-Host "OPENAPI HTTP" $OpenApi.StatusCode "bytes=" $OpenApi.RawContentLength

$PositionsCss = Invoke-WebRequest "https://api.nexustrade.ir/miniapp/admin-positions-v24.css?v=20260915-positions1" -UseBasicParsing -TimeoutSec 15
if ($PositionsCss.StatusCode -ne 200) { throw "Admin positions CSS public check failed" }
Write-Host "POSITIONS CSS HTTP" $PositionsCss.StatusCode

$EnvFile = Join-Path $Prod ".env"
$Token = $null
$Account = $null
if (Test-Path $EnvFile) {
    foreach ($Line in Get-Content $EnvFile) {
        if ($Line -match '^\s*NEXUS_ADMIN_TOKEN\s*=\s*(.+?)\s*$') { $Token = $Matches[1].Trim('"','''') }
        if ($Line -match '^\s*NEXUS_ADMIN_MT5_ACCOUNTS\s*=\s*(.+?)\s*$') { $Account = ($Matches[1].Trim('"','''') -split ',')[0].Trim() }
    }
}
if (-not $Token -or -not $Account) { throw "Could not resolve admin token/account internally from Production .env" }
$Headers = @{ "X-MT5-Account"=$Account; "X-NEXUS-Admin-Token"=$Token }
$Health = Invoke-RestMethod "https://api.nexustrade.ir/api/v1/autotrade/admin/chart-capture/health?minutes=30" -Headers $Headers -Method GET -TimeoutSec 20
Write-Host "HEALTH:" ($Health | ConvertTo-Json -Depth 6 -Compress)

Write-Host "`n=== 8. RUNTIME VERSION OBSERVATION ==="
$Today = Get-Date -Format "yyyyMMdd"
$Logs = Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal\*\MQL5\Logs\$Today.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
$VersionSeen = $false
if ($Logs) {
    $VersionMatches = Select-String -Path $Logs.FullName -Pattern "0.6.5-chart-agent-reliability-v24|INIT_BEGIN.*chart-agent-reliability-v24" -ErrorAction SilentlyContinue |
        Select-Object -Last 8
    if ($VersionMatches) {
        $VersionMatches | ForEach-Object { Write-Host $_.Line }
        $VersionSeen = $true
    }
}
if ($VersionSeen) {
    Write-Host "CHARTAGENT RUNTIME VERSION: PASS"
} else {
    Write-Warning "Compiled V24 is installed, but runtime INIT marker was not observed yet. Remove/re-attach ONLY NEXUS_ChartAgent (screenshot-only EA) once; do not restart/change the Trading EA."
}

Write-Host "`nCHART DELIVERY V24 PRODUCTION DEPLOY: PASS"
Write-Host "Backend/UI/ChartAgent files are deployed from staged evidence."
Write-Host "E2E chart publication is NOT certified until one fresh Mini App signal produces a real chart or repairs a fallback."
Write-Host "Run: $Prod\tools\diagnose_chart_delivery_v24.ps1 -Minutes 30"
