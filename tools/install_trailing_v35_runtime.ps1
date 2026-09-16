param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$ReleaseCore = Join-Path $Prod "mt5\NEXUS_AutoTrade_UI65\Core"
$ReleaseEA = Join-Path $ReleaseCore "NEXUS_AutoTrade_Core.mq5"
$ReleaseTrail = Join-Path $ReleaseCore "Include\TrailingEngine.mqh"

foreach ($Path in @($ReleaseEA,$ReleaseTrail)) {
    if (-not (Test-Path $Path)) { throw "V35 source not found: $Path" }
}

$TerminalRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"
if (-not (Test-Path $TerminalRoot)) { throw "MT5 data root not found: $TerminalRoot" }

$Candidates = @(
    Get-ChildItem -Path $TerminalRoot -Filter "NEXUS_AutoTrade_Core.mq5" -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\MQL5\\Experts\\" }
)

Write-Host "=== LIVE NEXUS CORE SOURCE CANDIDATES ===" -ForegroundColor Cyan
$Candidates | ForEach-Object { Write-Host $_.FullName }

if ($Candidates.Count -ne 1) {
    throw "Expected exactly one live NEXUS_AutoTrade_Core.mq5 under MT5 MQL5\Experts; found $($Candidates.Count). No MT5 file changed."
}

$TargetEA = $Candidates[0].FullName
$TargetCore = Split-Path $TargetEA -Parent
$TargetTrail = Join-Path $TargetCore "Include\TrailingEngine.mqh"
$TargetEx5 = [System.IO.Path]::ChangeExtension($TargetEA,".ex5")

if (-not (Test-Path $TargetTrail)) {
    throw "Live TrailingEngine.mqh not found beside detected Core: $TargetTrail"
}

# V35 changes only TrailingEngine.mqh. Abort if the rest of the compile context
# differs from the exact release source; never combine V35 with an unknown Core.
$ContextFiles = @(
    "NEXUS_AutoTrade_Core.mq5",
    "Include\TradeManager.mqh",
    "Include\NexusTypes.mqh",
    "Include\SignalParser.mqh",
    "Include\APIClient.mqh"
)

Write-Host "=== COMPILE CONTEXT VERIFICATION ===" -ForegroundColor Cyan
foreach ($Rel in $ContextFiles) {
    $Expected = Join-Path $ReleaseCore $Rel
    $Actual = Join-Path $TargetCore $Rel
    if (-not (Test-Path $Expected)) { throw "Release context file missing: $Expected" }
    if (-not (Test-Path $Actual)) { throw "Live context file missing: $Actual" }
    $ExpectedHash = (Get-FileHash $Expected -Algorithm SHA256).Hash
    $ActualHash = (Get-FileHash $Actual -Algorithm SHA256).Hash
    Write-Host "$Rel release=$ExpectedHash live=$ActualHash"
    if ($ExpectedHash -ne $ActualHash) {
        throw "Compile context mismatch for $Rel. No V35 file changed."
    }
}

$BackupDir = Join-Path $Prod "_backup\trailing-v35-runtime-$Stamp"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Copy-Item $TargetTrail (Join-Path $BackupDir "TrailingEngine.mqh") -Force
if (Test-Path $TargetEx5) { Copy-Item $TargetEx5 (Join-Path $BackupDir "NEXUS_AutoTrade_Core.ex5") -Force }
Write-Host "Backup:" $BackupDir

$OldTrailHash = (Get-FileHash $TargetTrail -Algorithm SHA256).Hash
$NewTrailHash = (Get-FileHash $ReleaseTrail -Algorithm SHA256).Hash
Write-Host "OLD TRAILING SHA256:" $OldTrailHash
Write-Host "V35 TRAILING SHA256:" $NewTrailHash

Copy-Item $ReleaseTrail $TargetTrail -Force
$InstalledHash = (Get-FileHash $TargetTrail -Algorithm SHA256).Hash
if ($InstalledHash -ne $NewTrailHash) {
    Copy-Item (Join-Path $BackupDir "TrailingEngine.mqh") $TargetTrail -Force
    throw "V35 source copy verification failed; previous TrailingEngine restored."
}
Write-Host "V35 SOURCE UPDATED:" $TargetTrail

$EditorCandidates = @()
foreach ($Base in @("C:\Program Files", "C:\Program Files (x86)")) {
    if (Test-Path $Base) {
        $EditorCandidates += Get-ChildItem -Path $Base -Filter "metaeditor64.exe" -File -Recurse -ErrorAction SilentlyContinue
    }
}
$EditorCandidates = @($EditorCandidates | Sort-Object LastWriteTime -Descending -Unique)

Write-Host "=== METAEDITOR CANDIDATES ===" -ForegroundColor Cyan
$EditorCandidates | ForEach-Object { Write-Host $_.FullName }
if ($EditorCandidates.Count -lt 1) {
    Copy-Item (Join-Path $BackupDir "TrailingEngine.mqh") $TargetTrail -Force
    throw "metaeditor64.exe not found. Previous TrailingEngine restored."
}

$Editor = $EditorCandidates[0].FullName
$Log = Join-Path $BackupDir "metaeditor-v35.log"
Write-Host "COMPILER:" $Editor
Write-Host "COMPILE TARGET:" $TargetEA

if (Test-Path $Log) { Remove-Item $Log -Force }
& $Editor "/compile:$TargetEA" "/log:$Log"

$Deadline = (Get-Date).AddSeconds(180)
$LogText = ""
$SummarySeen = $false
$ErrorCount = $null
$WarningCount = $null

while ((Get-Date) -lt $Deadline) {
    if (Test-Path $Log) {
        try { $LogText = Get-Content $Log -Raw -ErrorAction Stop } catch { $LogText = "" }
        if ($LogText -match '(?im)(\d+)\s+errors?,\s*(\d+)\s+warnings?') {
            $SummarySeen = $true
            $ErrorCount = [int]$Matches[1]
            $WarningCount = [int]$Matches[2]
            break
        }
    }
    Start-Sleep -Seconds 1
}

if (Test-Path $Log) {
    if (-not $LogText) { $LogText = Get-Content $Log -Raw }
    Write-Host $LogText
}

$CompileOk = $SummarySeen -and $ErrorCount -eq 0 -and (Test-Path $TargetEx5)
if (-not $CompileOk) {
    Write-Host "V35 COMPILE FAILED - restoring previous runtime" -ForegroundColor Red
    Copy-Item (Join-Path $BackupDir "TrailingEngine.mqh") $TargetTrail -Force
    $OldEx5 = Join-Path $BackupDir "NEXUS_AutoTrade_Core.ex5"
    if (Test-Path $OldEx5) { Copy-Item $OldEx5 $TargetEx5 -Force }
    if (-not $SummarySeen) { throw "Trailing V35 compile timed out before final compiler summary; previous runtime restored." }
    throw "Trailing V35 compile failed with $ErrorCount errors and $WarningCount warnings; previous runtime restored."
}

$Ex5Hash = (Get-FileHash $TargetEx5 -Algorithm SHA256).Hash
Write-Host "TRAILING V35 COMPILE: PASS" -ForegroundColor Green
Write-Host "COMPILER SUMMARY: $ErrorCount errors, $WarningCount warnings"
Write-Host "TRAILING SOURCE SHA256:" $InstalledHash
Write-Host "EX5:" $TargetEx5
Write-Host "EX5 SHA256:" $Ex5Hash
Write-Host "BACKUP:" $BackupDir
Write-Host "Do not restart the terminal blindly while positions are open. Confirm the attached NEXUS EA reinitialized or reload it during a safe/demo window, then run the V35 E2E test."
