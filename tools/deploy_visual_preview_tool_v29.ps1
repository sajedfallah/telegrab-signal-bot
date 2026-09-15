param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Prod "_backup\visual-preview-tool-v29-$Stamp"
$Python = Join-Path $Prod ".venv\Scripts\python.exe"
$Rel = "tools\send_signal_visual_preview_v29.py"
$Src = Join-Path $SourceRoot $Rel
$Dst = Join-Path $Prod $Rel

if (-not (Test-Path $Src)) { throw "Missing source preview tool" }
if (-not (Test-Path $Python)) { throw "Production Python not found" }

Write-Host "=== V29 PREVIEW TOOL CONTRACT ==="
$Text = Get-Content $Src -Raw
foreach ($Marker in @(
    'NEXUS VISUAL PREVIEW',
    'TEST ONLY • NO TRADE ACTION',
    'production_signal_anchor_untouched',
    '_load_series',
    '_render_chart',
    'if not args.send:'
)) {
    if (-not $Text.Contains($Marker)) { throw "Missing preview marker: $Marker" }
}
foreach ($Forbidden in @(
    'ensure_broker_chart_asset',
    'set_signal_publish_messages',
    'claim_signal_channel',
    '_publish_mt5_admin_signal_async'
)) {
    if ($Text.Contains($Forbidden)) { throw "Unsafe preview marker present: $Forbidden" }
}
Write-Host "SOURCE CONTRACT: PASS"

Write-Host "=== V29 PREVIEW TOOL TESTS ==="
Push-Location $SourceRoot
try {
    & $Python -m py_compile $Rel
    if ($LASTEXITCODE -ne 0) { throw "Preview tool compile failed" }
    & $Python -m pytest "tests\test_signal_visual_preview_v29.py" -q
    if ($LASTEXITCODE -ne 0) { throw "Preview tool tests failed" }
} finally {
    Pop-Location
}
Write-Host "PREVIEW TOOL TESTS: PASS"

Write-Host "=== BACKUP ==="
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
if (Test-Path $Dst) {
    $BackupFile = Join-Path $Backup $Rel
    New-Item -ItemType Directory -Force -Path (Split-Path $BackupFile -Parent) | Out-Null
    Copy-Item $Dst $BackupFile -Force
}
Write-Host "Backup:" $Backup

Write-Host "=== TARGETED COPY ==="
New-Item -ItemType Directory -Force -Path (Split-Path $Dst -Parent) | Out-Null
Copy-Item $Src $Dst -Force
Write-Host "DEPLOYED:" $Rel
Write-Host "PRESERVED: Backend service / app code / DB / Telegram anchors / Trading EA"
Write-Host "NO SERVICE RESTART REQUIRED"
Write-Host "V29 VISUAL PREVIEW TOOL DEPLOY: PASS"
