param(
    [string]$MetaEditor,
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$source = Join-Path $Root "mt5\NEXUS_AutoTrade_UI65\NEXUS_AutoTrade_UI65.mq5"
if (-not (Test-Path $source)) {
    throw "UI65 source not found: $source"
}

if (-not $MetaEditor) {
    $candidates = @(
        "$env:ProgramFiles\MetaTrader 5\metaeditor64.exe",
        "$env:ProgramFiles\MetaTrader 5\MetaEditor64.exe",
        "${env:ProgramFiles(x86)}\MetaTrader 5\metaeditor64.exe",
        "${env:ProgramFiles(x86)}\MetaTrader 5\MetaEditor64.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($candidates.Count -gt 0) {
        $MetaEditor = $candidates[0]
    }
}

if (-not $MetaEditor -or -not (Test-Path $MetaEditor)) {
    throw "MetaEditor64.exe was not found. Re-run with -MetaEditor 'C:\path\to\metaeditor64.exe'."
}

$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$log = Join-Path $logDir "metaeditor_ui65_compile.log"
if (Test-Path $log) { Remove-Item $log -Force }

Write-Host "=== NEXUS UI65 METAEDITOR COMPILE ==="
Write-Host "MetaEditor : $MetaEditor"
Write-Host "Source     : $source"
Write-Host "Log        : $log"

$arguments = @(
    "/compile:$source",
    "/log:$log"
)

$process = Start-Process -FilePath $MetaEditor -ArgumentList $arguments -Wait -PassThru
Start-Sleep -Milliseconds 500

if (-not (Test-Path $log)) {
    throw "MetaEditor finished but compile log was not created. ExitCode=$($process.ExitCode)"
}

$logText = Get-Content $log -Raw -ErrorAction Stop
Write-Host ""
Write-Host $logText

if ($logText -notmatch '(?im)\b0\s+errors?\b') {
    throw "UI65 compile did not report 0 errors. Review: $log"
}

$ex5 = [System.IO.Path]::ChangeExtension($source, ".ex5")
if (-not (Test-Path $ex5)) {
    throw "Compile log reports success but EX5 was not found: $ex5"
}

Write-Host ""
Write-Host "UI65 COMPILE: PASS"
Write-Host "EX5: $ex5"
Write-Host "Production EX5 was NOT replaced automatically."
