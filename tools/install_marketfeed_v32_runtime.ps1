param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Source = Join-Path $Prod "mt5\NEXUS_MarketFeed\NEXUS_MarketFeed.mq5"
if (-not (Test-Path $Source)) { throw "V32 MarketFeed source not found: $Source" }

$TerminalRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"
if (-not (Test-Path $TerminalRoot)) { throw "MT5 data root not found: $TerminalRoot" }

$Candidates = @(
    Get-ChildItem -Path $TerminalRoot -Filter "NEXUS_MarketFeed.mq5" -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\MQL5\\Experts\\" }
)

Write-Host "=== LIVE MARKETFEED SOURCE CANDIDATES ==="
$Candidates | ForEach-Object { Write-Host $_.FullName }
if ($Candidates.Count -ne 1) {
    throw "Expected exactly one live NEXUS_MarketFeed.mq5 under MT5 MQL5\Experts; found $($Candidates.Count). No MT5 file changed."
}

$Target = $Candidates[0].FullName
$TargetDir = Split-Path $Target -Parent
$Ex5 = Join-Path $TargetDir "NEXUS_MarketFeed.ex5"
$BackupDir = Join-Path $Prod "_backup\marketfeed-v32-runtime-$Stamp"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Copy-Item $Target (Join-Path $BackupDir "NEXUS_MarketFeed.mq5") -Force
if (Test-Path $Ex5) { Copy-Item $Ex5 (Join-Path $BackupDir "NEXUS_MarketFeed.ex5") -Force }
Write-Host "Backup:" $BackupDir

Copy-Item $Source $Target -Force
Write-Host "SOURCE UPDATED:" $Target

$EditorCandidates = @()
foreach ($Base in @("C:\Program Files", "C:\Program Files (x86)")) {
    if (Test-Path $Base) {
        $EditorCandidates += Get-ChildItem -Path $Base -Filter "metaeditor64.exe" -File -Recurse -ErrorAction SilentlyContinue
    }
}
$EditorCandidates = @($EditorCandidates | Sort-Object LastWriteTime -Descending -Unique)
Write-Host "=== METAEDITOR CANDIDATES ==="
$EditorCandidates | ForEach-Object { Write-Host $_.FullName }
if ($EditorCandidates.Count -lt 1) {
    throw "metaeditor64.exe not found. Source is updated but EX5 was not compiled."
}

$Editor = $EditorCandidates[0].FullName
$Log = Join-Path $BackupDir "metaeditor-v32.log"
Write-Host "COMPILER:" $Editor

& $Editor "/compile:$Target" "/log:$Log"
Start-Sleep -Seconds 2

if (-not (Test-Path $Log)) { throw "MetaEditor compile log not found: $Log" }
$LogText = Get-Content $Log -Raw
Write-Host $LogText
if ($LogText -notmatch "0 errors") { throw "MarketFeed compile did not report 0 errors" }
if (-not (Test-Path $Ex5)) { throw "Compiled EX5 not found: $Ex5" }

Write-Host "MARKETFEED V32 COMPILE: PASS"
Write-Host "EX5:" $Ex5
Write-Host "Wait 10 seconds, then run tools\check_market_quote_v32.py. If no fresh tick appears, reload only the NEXUS_MarketFeed EA on its chart and check again."
