param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912",
    [string]$TestAccount = "",
    [string]$TestChannelId = ""
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Prod "_backup\v36-testlab-alert-visual-$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

function Invoke-MetaCompile {
    param([string]$Editor,[string]$Source,[string]$Log,[string]$ExpectedEx5)
    if (Test-Path $Log) { Remove-Item $Log -Force }
    & $Editor "/compile:$Source" "/log:$Log"
    $Deadline=(Get-Date).AddSeconds(180)
    $Text=""; $Seen=$false; $Errors=$null; $Warnings=$null
    while ((Get-Date) -lt $Deadline) {
        if (Test-Path $Log) {
            try { $Text=Get-Content $Log -Raw -ErrorAction Stop } catch { $Text="" }
            if ($Text -match '(?im)(\d+)\s+errors?,\s*(\d+)\s+warnings?') {
                $Seen=$true; $Errors=[int]$Matches[1]; $Warnings=[int]$Matches[2]; break
            }
        }
        Start-Sleep -Seconds 1
    }
    if (Test-Path $Log) { if (-not $Text) { $Text=Get-Content $Log -Raw }; Write-Host $Text }
    if (-not $Seen) { throw "MetaEditor timed out: $Source" }
    if ($Errors -ne 0 -or $Warnings -ne 0) { throw "MetaEditor rejected $Source : $Errors errors, $Warnings warnings" }
    if (-not (Test-Path $ExpectedEx5)) { throw "Compiled EX5 missing: $ExpectedEx5" }
    Write-Host "COMPILE PASS: $Source | 0 errors, 0 warnings" -ForegroundColor Green
}

function Set-EnvValue {
    param([string]$Path,[string]$Name,[string]$Value)
    $Lines=@(Get-Content $Path)
    $Found=$false
    for($i=0;$i -lt $Lines.Count;$i++) {
        if ($Lines[$i] -match ('^\s*'+[regex]::Escape($Name)+'\s*=')) {
            $Lines[$i]="$Name=$Value"; $Found=$true
        }
    }
    if (-not $Found) { $Lines += "$Name=$Value" }
    Set-Content -Path $Path -Value $Lines -Encoding UTF8
}

Write-Host "=== V36 SOURCE CHECK ===" -ForegroundColor Cyan
$Required=@(
    "app\autotrade\chart_alert_dedup_runtime.py",
    "app\autotrade\test_lab_runtime.py",
    "app\combined_api.py",
    "miniapp\admin-test.html",
    "mt5\NEXUS_AutoTrade_UI65\NEXUS_AutoTrade_Demo.mq5",
    "mt5\NEXUS_ChartAgent\NEXUS_ChartAgent.mq5",
    "tools\apply_chart_visual_v36.ps1"
)
foreach($Rel in $Required){$P=Join-Path $Prod $Rel;if(-not(Test-Path $P)){throw "Missing V36 source: $Rel"}}

$Python=Join-Path $Prod ".venv\Scripts\python.exe"
foreach($Rel in @("app\autotrade\chart_alert_dedup_runtime.py","app\autotrade\test_lab_runtime.py","app\combined_api.py")) {
    & $Python -m py_compile (Join-Path $Prod $Rel)
    if($LASTEXITCODE -ne 0){throw "Python compile failed: $Rel"}
}
Write-Host "V36 PYTHON COMPILE: PASS" -ForegroundColor Green

Write-Host "=== CHART VISUAL V36 SOURCE PROMOTION ===" -ForegroundColor Cyan
$ChartSource=Join-Path $Prod "mt5\NEXUS_ChartAgent\NEXUS_ChartAgent.mq5"
Copy-Item $ChartSource (Join-Path $Backup "NEXUS_ChartAgent.repo.before.mq5") -Force
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Prod "tools\apply_chart_visual_v36.ps1") -Path $ChartSource
if($LASTEXITCODE -ne 0){throw "Chart visual V36 patch failed"}

$TerminalRoot=Join-Path $env:APPDATA "MetaQuotes\Terminal"
$LiveChart=@(Get-ChildItem $TerminalRoot -Filter "NEXUS_ChartAgent.mq5" -File -Recurse -ErrorAction SilentlyContinue | Where-Object {$_.FullName -match '\\MQL5\\Experts\\NEXUS_ChartAgent\\'})
if($LiveChart.Count -ne 1){throw "Expected exactly one live NEXUS_ChartAgent.mq5; found $($LiveChart.Count)"}
$LiveChartSource=$LiveChart[0].FullName
$LiveChartDir=Split-Path $LiveChartSource -Parent
$LiveChartEx5=Join-Path $LiveChartDir "NEXUS_ChartAgent.ex5"
Copy-Item $LiveChartSource (Join-Path $Backup "NEXUS_ChartAgent.live.before.mq5") -Force
if(Test-Path $LiveChartEx5){Copy-Item $LiveChartEx5 (Join-Path $Backup "NEXUS_ChartAgent.live.before.ex5") -Force}
Copy-Item $ChartSource $LiveChartSource -Force

$Editors=@()
foreach($Base in @("C:\Program Files","C:\Program Files (x86)")){if(Test-Path $Base){$Editors+=Get-ChildItem $Base -Filter "metaeditor64.exe" -File -Recurse -ErrorAction SilentlyContinue}}
$Editors=@($Editors|Sort-Object LastWriteTime -Descending -Unique)
if($Editors.Count -lt 1){throw "metaeditor64.exe not found"}
$Editor=$Editors[0].FullName
Invoke-MetaCompile -Editor $Editor -Source $LiveChartSource -Log (Join-Path $Backup "chartagent-v36.log") -ExpectedEx5 $LiveChartEx5

Write-Host "=== DEMO EXPERT V36 ===" -ForegroundColor Cyan
$CoreCandidates=@(Get-ChildItem $TerminalRoot -Filter "NEXUS_AutoTrade_Core.mq5" -File -Recurse -ErrorAction SilentlyContinue | Where-Object {$_.FullName -match '\\MQL5\\Experts\\NEXUS_AutoTrade_UI65\\Core\\'})
if($CoreCandidates.Count -ne 1){throw "Expected exactly one live NEXUS_AutoTrade_Core.mq5; found $($CoreCandidates.Count)"}
$LiveCoreDir=Split-Path $CoreCandidates[0].FullName -Parent
$LiveEaRoot=Split-Path $LiveCoreDir -Parent
$DemoSource=Join-Path $LiveEaRoot "NEXUS_AutoTrade_Demo.mq5"
$DemoEx5=Join-Path $LiveEaRoot "NEXUS_AutoTrade_Demo.ex5"
if(Test-Path $DemoSource){Copy-Item $DemoSource (Join-Path $Backup "NEXUS_AutoTrade_Demo.before.mq5") -Force}
if(Test-Path $DemoEx5){Copy-Item $DemoEx5 (Join-Path $Backup "NEXUS_AutoTrade_Demo.before.ex5") -Force}
Copy-Item (Join-Path $Prod "mt5\NEXUS_AutoTrade_UI65\NEXUS_AutoTrade_Demo.mq5") $DemoSource -Force
Invoke-MetaCompile -Editor $Editor -Source $DemoSource -Log (Join-Path $Backup "autotrade-demo-v36.log") -ExpectedEx5 $DemoEx5

if($TestAccount -or $TestChannelId) {
    if(-not $TestAccount -or -not $TestChannelId){throw "Provide both -TestAccount and -TestChannelId, or neither"}
    if($TestAccount -notmatch '^\d{4,20}$'){throw "Invalid TestAccount"}
    if($TestChannelId -notmatch '^-?\d+$' -and $TestChannelId -notmatch '^@'){throw "Invalid TestChannelId"}
    $EnvFile=Join-Path $Prod ".env"
    if(-not(Test-Path $EnvFile)){throw ".env not found; Test Lab settings were not changed"}
    Copy-Item $EnvFile (Join-Path $Backup ".env.before") -Force
    Set-EnvValue $EnvFile "NEXUS_TEST_MT5_ACCOUNT" $TestAccount
    Set-EnvValue $EnvFile "NEXUS_TEST_CHANNEL_ID" $TestChannelId
    $Current=(Select-String -Path $EnvFile -Pattern '^\s*NEXUS_ADMIN_MT5_ACCOUNTS\s*=' | Select-Object -Last 1).Line
    $Accounts=@()
    if($Current){$Accounts=(($Current -split '=',2)[1] -split ',')|ForEach-Object{$_.Trim()}|Where-Object{$_}}
    if($Accounts -notcontains $TestAccount){$Accounts+= $TestAccount}
    Set-EnvValue $EnvFile "NEXUS_ADMIN_MT5_ACCOUNTS" (($Accounts|Select-Object -Unique) -join ',')
    Write-Host "TEST LAB ENV: CONFIGURED" -ForegroundColor Green
} else {
    Write-Host "TEST LAB ENV: NOT CHANGED (supply -TestAccount and -TestChannelId when ready)" -ForegroundColor Yellow
}

Restart-Service "NEXUS-AutoTrade-API" -Force
Start-Sleep -Seconds 3
$Svc=Get-Service "NEXUS-AutoTrade-API"
if($Svc.Status -ne "Running"){throw "NEXUS-AutoTrade-API not running"}

Write-Host "V36 RUNTIME INSTALL: PASS" -ForegroundColor Green
Write-Host "API SERVICE:" $Svc.Status
Write-Host "DEMO EX5:" $DemoEx5
Write-Host "CHARTAGENT EX5:" $LiveChartEx5
Write-Host "BACKUP:" $Backup
Write-Host "Test Mini App path: /miniapp/admin-test.html"
Write-Host "Re-attach only NEXUS_ChartAgent if its currently attached instance did not reload after compile."
