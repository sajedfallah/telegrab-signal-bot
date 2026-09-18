param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Source = Join-Path $Prod "mt5\NEXUS_MarketFeed\NEXUS_MarketFeed.mq5"
$Backup = Join-Path $Prod "_backup\marketfeed-v39-runtime-$Stamp"

if (-not (Test-Path $Source)) { throw "V39 MarketFeed source not found: $Source" }

$TerminalRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"
if (-not (Test-Path $TerminalRoot)) { throw "MT5 data root not found: $TerminalRoot" }

$Targets = @(
    Get-ChildItem -Path $TerminalRoot -Filter "NEXUS_MarketFeed.mq5" -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\MQL5\\Experts\\" }
)
Write-Host "=== LIVE MARKETFEED TARGETS ==="
$Targets | ForEach-Object { Write-Host $_.FullName }
if ($Targets.Count -ne 1) {
    throw "Expected exactly one live NEXUS_MarketFeed.mq5 under MQL5\\Experts; found $($Targets.Count). No live MT5 file changed."
}

$Target = $Targets[0].FullName
$TargetDir = Split-Path $Target -Parent
$Ex5 = [System.IO.Path]::ChangeExtension($Target, ".ex5")
$CompileLog = [System.IO.Path]::ChangeExtension($Target, ".log")

New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Target (Join-Path $Backup "NEXUS_MarketFeed.mq5") -Force
if (Test-Path $Ex5) { Copy-Item $Ex5 (Join-Path $Backup "NEXUS_MarketFeed.ex5") -Force }

Copy-Item $Source $Target -Force
Write-Host "SOURCE UPDATED:" $Target
Write-Host "Backup:" $Backup

$Editors = @()
foreach ($Base in @("C:\Program Files","C:\Program Files (x86)")) {
    if (Test-Path $Base) {
        $Editors += Get-ChildItem -Path $Base -Filter "metaeditor64.exe" -File -Recurse -ErrorAction SilentlyContinue
    }
}
$Editors = @($Editors | Sort-Object LastWriteTime -Descending -Unique)
if ($Editors.Count -lt 1) { throw "metaeditor64.exe not found" }

$Editor = $Editors[0].FullName
Write-Host "COMPILER:" $Editor
if (Test-Path $CompileLog) { Remove-Item $CompileLog -Force }

# MetaEditor /log creates <source>.log beside the MQ5 source. Do not pass a
# custom /log:path here; builds differ in how they handle that form.
& $Editor "/compile:$Target" /log

$Deadline = (Get-Date).AddSeconds(120)
$LogText = ""
$SummarySeen = $false
$Errors = $null
$Warnings = $null

while ((Get-Date) -lt $Deadline) {
    if (Test-Path $CompileLog) {
        try { $LogText = Get-Content $CompileLog -Raw -ErrorAction Stop } catch { $LogText = "" }
        if ($LogText -match '(?im)(\d+)\s+errors?,\s*(\d+)\s+warnings?') {
            $SummarySeen = $true
            $Errors = [int]$Matches[1]
            $Warnings = [int]$Matches[2]
            break
        }
    }
    Start-Sleep -Seconds 1
}

if (-not $SummarySeen) {
    throw "MetaEditor did not produce a final compile summary at $CompileLog"
}
Write-Host $LogText
if ($Errors -ne 0) { throw "MarketFeed compile failed: $Errors errors, $Warnings warnings" }
if (-not (Test-Path $Ex5)) { throw "Compiled EX5 not found: $Ex5" }

Write-Host "MARKETFEED V39 COMPILE: PASS"
Write-Host "SUMMARY: $Errors errors, $Warnings warnings"
Write-Host "EX5:" $Ex5
Write-Warning "Reload/re-attach only the NEXUS_MarketFeed EA in MT5 so the new M30/H4 feed starts."
