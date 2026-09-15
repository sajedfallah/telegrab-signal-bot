param(
    [Parameter(Mandatory=$true)]
    [string]$Commit,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$StageRoot = "C:\NEXUS_DEPLOY\_stage-chart-delivery-v24-$Stamp"
$Repo = Join-Path $StageRoot "repo"
$Archive = Join-Path $StageRoot "release.zip"
$Release = Join-Path $StageRoot "release"
$EvidenceDir = "C:\NEXUS_DEPLOY\_stage-evidence"
$Evidence = Join-Path $EvidenceDir ("chart-delivery-v24-" + $Commit + ".json")

if (-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }
$Python = Join-Path $Prod ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Production Python venv not found: $Python" }

New-Item -ItemType Directory -Force -Path $StageRoot,$EvidenceDir | Out-Null

Write-Host "=== 1. FETCH EXACT COMMIT INTO ISOLATED STAGING ==="
git clone --filter=blob:none --no-checkout https://github.com/sajedfallah/telegrab-signal-bot.git $Repo
if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
git -C $Repo fetch origin feature/live-charts-v1
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
$Resolved = (git -C $Repo rev-parse $Commit).Trim()
Write-Host "Requested:" $Commit
Write-Host "Resolved :" $Resolved
if ($Resolved -ne $Commit) { throw "Commit verification failed" }
git -C $Repo archive --format=zip --output=$Archive $Commit
if ($LASTEXITCODE -ne 0) { throw "git archive failed" }
Expand-Archive -Path $Archive -DestinationPath $Release -Force

Write-Host "`n=== 2. REQUIRED SOURCE VERIFY ==="
$Required = @(
    "app\autotrade\chart_delivery_guard.py",
    "app\autotrade\chart_repair_claim_runtime.py",
    "app\combined_api.py",
    "tools\apply_chart_agent_reliability_v24.ps1",
    "tools\diagnose_chart_delivery_v24.ps1",
    "tests\test_chart_delivery_reliability_v24.py",
    "tests\test_admin_positions_v24.py",
    "miniapp\admin.html",
    "miniapp\admin-positions-v24.css",
    "miniapp\vazirmatn.css",
    "mt5\NEXUS_ChartAgent\NEXUS_ChartAgent.mq5"
)
foreach ($Rel in $Required) {
    if (-not (Test-Path (Join-Path $Release $Rel))) { throw "Missing staged file: $Rel" }
    Write-Host "FOUND:" $Rel
}

Write-Host "`n=== 3. PYTHON SYNTAX + V24 SCENARIO PYTEST GATE ==="
Push-Location $Release
try {
    & $Python -m py_compile app\autotrade\chart_delivery_guard.py app\autotrade\chart_repair_claim_runtime.py app\combined_api.py
    if ($LASTEXITCODE -ne 0) { throw "Python syntax check failed" }

    & $Python -m pytest tests\test_chart_delivery_reliability_v24.py tests\test_admin_positions_v24.py -q
    if ($LASTEXITCODE -ne 0) { throw "V24 staging pytest failed" }
} finally {
    Pop-Location
}
Write-Host "PYTEST/STAGING CONTRACT: PASS"

Write-Host "`n=== 4. APPLY CHARTAGENT V24 PATCH TO STAGED SOURCE ONLY ==="
$StageAgent = Join-Path $Release "mt5\NEXUS_ChartAgent\NEXUS_ChartAgent.mq5"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Release "tools\apply_chart_agent_reliability_v24.ps1") -SourcePath $StageAgent
if ($LASTEXITCODE -ne 0) { throw "ChartAgent V24 patch failed" }
$AgentText = Get-Content $StageAgent -Raw
foreach ($Marker in @(
    "0.6.5-chart-agent-reliability-v24",
    "SCALE_VISIBLE_RANGE_CONFIRMED",
    "SCALE_FIXED_RANGE_CONFIRMED",
    "PostWithRetry",
    "SCREENSHOT_UPLOAD_CONFIRMED"
)) {
    if (-not $AgentText.Contains($Marker)) { throw "Patched ChartAgent missing marker: $Marker" }
}
Write-Host "CHARTAGENT PATCH: PASS"

Write-Host "`n=== 5. METAEDITOR COMPILE GATE ==="
$MetaCandidates = @(
    "$env:ProgramFiles\MetaTrader 5\metaeditor64.exe",
    "$env:ProgramFiles\MetaTrader 5\MetaEditor64.exe",
    "${env:ProgramFiles(x86)}\MetaTrader 5\metaeditor64.exe",
    "${env:ProgramFiles(x86)}\MetaTrader 5\MetaEditor64.exe"
) | Where-Object { $_ -and (Test-Path $_) }
if (-not $MetaCandidates) {
    $MetaCandidates = Get-ChildItem "$env:ProgramFiles" -Filter "metaeditor64.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName -First 3
}
$MetaEditor = $MetaCandidates | Select-Object -First 1
if (-not $MetaEditor) {
    throw "MetaEditor64.exe not found. Staging cannot be certified without MQ5 compile."
}
Write-Host "MetaEditor:" $MetaEditor
$CompileLog = Join-Path $StageRoot "metaeditor-v24.log"
$Psi = New-Object System.Diagnostics.ProcessStartInfo
$Psi.FileName = $MetaEditor
$Psi.Arguments = "/compile:`"$StageAgent`" /log:`"$CompileLog`""
$Psi.UseShellExecute = $false
$Process = [System.Diagnostics.Process]::Start($Psi)
if (-not $Process.WaitForExit(120000)) {
    try { $Process.Kill() } catch {}
    throw "MetaEditor compile timed out"
}
Start-Sleep -Milliseconds 700
if (-not (Test-Path $CompileLog)) { throw "MetaEditor compile log was not created" }
$CompileText = Get-Content $CompileLog -Raw -ErrorAction Stop
Write-Host $CompileText
if ($CompileText -notmatch '(?i)0\s+errors?') { throw "MQ5 compile did not report 0 errors" }
$StageEx5 = [System.IO.Path]::ChangeExtension($StageAgent, ".ex5")
if (-not (Test-Path $StageEx5)) { throw "Compiled staged EX5 not found: $StageEx5" }
Write-Host "MQ5 COMPILE: PASS"

Write-Host "`n=== 6. WRITE STAGING EVIDENCE ==="
$EvidenceObject = [ordered]@{
    commit = $Commit
    created_at = (Get-Date).ToString("o")
    stage_root = $StageRoot
    release = $Release
    tests_pass = $true
    chartagent_patch_pass = $true
    mq5_compile_pass = $true
    repair_claim_bridge_pass = $true
    admin_positions_cache_bust_pass = $true
    compiled_ex5 = $StageEx5
    production_changed = $false
}
$EvidenceObject | ConvertTo-Json -Depth 4 | Set-Content -Path $Evidence -Encoding UTF8
Write-Host "Evidence:" $Evidence
Write-Host "`nCHART DELIVERY V24 STAGING: PASS"
Write-Host "Production changed: NO"
Write-Host "Next step: production deploy may use only this exact commit/evidence."
