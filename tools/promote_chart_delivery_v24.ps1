param(
    [Parameter(Mandatory=$true)]
    [string]$Commit,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912",
    [string]$TerminalChartAgentDir = ""
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$StageScript = Join-Path $Here "stage_chart_delivery_v24.ps1"
$DeployScript = Join-Path $Here "deploy_chart_delivery_v24.ps1"
$UiDeployScript = Join-Path $Here "deploy_admin_positions_v24.ps1"

foreach ($Path in @($StageScript,$DeployScript,$UiDeployScript)) {
    if (-not (Test-Path $Path)) { throw "Promotion dependency missing: $Path" }
}

Write-Host "============================================================"
Write-Host "NEXUS V24 — STAGING-GATED PROMOTION"
Write-Host "Commit:" $Commit
Write-Host "============================================================"

Write-Host "`n=== PHASE A — ISOLATED STAGING / TEST / MQ5 COMPILE ==="
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StageScript -Commit $Commit -Prod $Prod
if ($LASTEXITCODE -ne 0) { throw "V24 staging gate failed; Production was not changed." }

$Evidence = "C:\NEXUS_DEPLOY\_stage-evidence\chart-delivery-v24-$Commit.json"
if (-not (Test-Path $Evidence)) { throw "Staging evidence was not produced; Production was not changed." }
$E = Get-Content $Evidence -Raw | ConvertFrom-Json
if (-not $E.tests_pass -or -not $E.chartagent_patch_pass -or -not $E.mq5_compile_pass -or -not $E.repair_claim_bridge_pass -or -not $E.admin_positions_cache_bust_pass) {
    throw "Staging evidence is incomplete; Production was not changed."
}
Write-Host "`nPROMOTION GATE: STAGING PASS — Production deployment is now allowed."

Write-Host "`n=== PHASE B — TARGETED CHART DELIVERY PRODUCTION DEPLOY ==="
$DeployArgs = @("-NoProfile","-ExecutionPolicy","Bypass","-File",$DeployScript,"-Commit",$Commit,"-Prod",$Prod)
if ($TerminalChartAgentDir) { $DeployArgs += @("-TerminalChartAgentDir",$TerminalChartAgentDir) }
& powershell.exe @DeployArgs
if ($LASTEXITCODE -ne 0) { throw "Chart delivery Production deploy failed. Inspect the backup printed by the deploy script." }

Write-Host "`n=== PHASE C — TARGETED ADMIN POSITIONS UI DEPLOY ==="
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $UiDeployScript -Commit $Commit -Prod $Prod
if ($LASTEXITCODE -ne 0) { throw "Admin Positions V24 UI deploy failed." }

Write-Host "`n============================================================"
Write-Host "NEXUS V24 PROMOTION: PASS"
Write-Host "Staging evidence: $Evidence"
Write-Host "Production API: deployed / restarted only NEXUS-AutoTrade-API"
Write-Host "Admin Positions UI: deployed without service restart"
Write-Host "Trading EA / T05 / T07 / MarketFeed: untouched"
Write-Host "Telegram Bot: not restarted"
Write-Host "Final E2E acceptance still requires ONE fresh Mini App signal."
Write-Host "============================================================"
