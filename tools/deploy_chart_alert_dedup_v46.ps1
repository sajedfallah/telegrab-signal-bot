param(
    [Parameter(Mandatory=$true)]
    [string]$Commit,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/sajedfallah/telegrab-signal-bot.git"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Work = "C:\NEXUS_DEPLOY\_stage-chart-alert-dedup-v46-$Stamp"
$Repo = Join-Path $Work "repo"
$Release = Join-Path $Work "release"
$Archive = Join-Path $Work "release.zip"
$Backup = Join-Path $Prod "_backup\chart-alert-dedup-v46-$Stamp"
$HealthUrl = "https://api.nexustrade.ir/miniapp/api/health"

$PythonCandidates = @(
    (Join-Path $Prod ".venv\Scripts\python.exe"),
    (Join-Path $Prod "venv\Scripts\python.exe")
)
$Python = $PythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

$DedupRel = "app\autotrade\chart_alert_dedup_runtime.py"
$CombinedRel = "app\combined_api.py"
$ProdDedup = Join-Path $Prod $DedupRel
$ProdCombined = Join-Path $Prod $CombinedRel

function Wait-Health {
    for($i=1; $i -le 30; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-RestMethod $HealthUrl -TimeoutSec 10
            if($r.ok -eq $true) {
                Write-Host "API HEALTH: PASS"
                return
            }
        } catch {}
    }
    throw "API health failed"
}

function Backup-File([string]$Rel) {
    $Source = Join-Path $Prod $Rel
    if(Test-Path $Source) {
        $Target = Join-Path $Backup $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
        Copy-Item $Source $Target -Force
        Write-Host "BACKUP: $Rel"
    }
}

if(-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }
if(-not $Python) { throw "Production Python not found under .venv or venv" }
if(-not (Test-Path $ProdCombined)) { throw "Production combined_api.py not found" }

Write-Host "=== NEXUS CHART ALERT DEDUP V46 ==="
Write-Host "Commit: $Commit"
Write-Host "Production: $Prod"
Write-Host "Python: $Python"

New-Item -ItemType Directory -Force -Path $Work,$Release,$Backup | Out-Null

try {
    Write-Host "=== FETCH EXACT COMMIT ==="
    git clone --filter=blob:none --no-checkout $RepoUrl $Repo
    if($LASTEXITCODE -ne 0) { throw "git clone failed" }

    git -C $Repo fetch origin $Commit
    if($LASTEXITCODE -ne 0) { throw "git fetch failed" }

    $Resolved = (git -C $Repo rev-parse $Commit).Trim()
    if($Resolved -ne $Commit) { throw "Exact commit verification failed" }

    Write-Host "=== ARCHIVE TARGET FILE ==="
    git -C $Repo archive --format=zip --output=$Archive $Commit app/autotrade/chart_alert_dedup_runtime.py
    if($LASTEXITCODE -ne 0 -or -not (Test-Path $Archive)) { throw "git archive failed" }

    Expand-Archive -Path $Archive -DestinationPath $Release -Force

    $StageDedup = Join-Path $Release $DedupRel
    $DedupText = Get-Content $StageDedup -Raw
    if(-not $DedupText.Contains('_DEDUP_VERSION = "v46"')) { throw "V46 marker missing" }
    if(-not $DedupText.Contains("INSERT OR IGNORE INTO chart_delivery_alert_incidents")) { throw "Durable incident claim missing" }
    if(-not $DedupText.Contains("guard._alert_due = durable_alert_due")) { throw "Alert gate replacement missing" }

    & $Python -m py_compile $StageDedup
    if($LASTEXITCODE -ne 0) { throw "Staged Python compile failed" }

    Write-Host "CONTRACT: PASS"

    Write-Host "=== BACKUP ==="
    Backup-File $DedupRel
    Backup-File $CombinedRel

    $Copied = $false
    try {
        Write-Host "=== TARGETED BACKEND PATCH ==="
        New-Item -ItemType Directory -Force -Path (Split-Path $ProdDedup -Parent) | Out-Null
        Copy-Item $StageDedup $ProdDedup -Force
        Write-Host "DEPLOYED: $DedupRel"

        $Combined = Get-Content $ProdCombined -Raw
        $Hook = "install_chart_alert_dedup_runtime(app)"
        if(-not $Combined.Contains($Hook)) {
            $Anchor = "install_chart_delivery_guard(app)"
            $AnchorIndex = $Combined.IndexOf($Anchor)
            if($AnchorIndex -lt 0) { throw "Chart delivery guard install anchor not found in Production combined_api.py" }

            $LineEnd = $Combined.IndexOf([char]10, $AnchorIndex)
            if($LineEnd -lt 0) { $LineEnd = $Combined.Length - 1 }

            $Patch = @"

# V46: durable incident-based Chart Delivery alert dedup.
from .autotrade.chart_alert_dedup_runtime import install_chart_alert_dedup_runtime
install_chart_alert_dedup_runtime(app)
"@
            $Combined = $Combined.Insert($LineEnd + 1, $Patch)
            [System.IO.File]::WriteAllText($ProdCombined, $Combined, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "PATCHED: $CombinedRel"
        } else {
            Write-Host "PRESERVED: existing dedup install hook in $CombinedRel"
        }

        $Copied = $true

        & $Python -m py_compile $ProdDedup $ProdCombined
        if($LASTEXITCODE -ne 0) { throw "Production Python compile failed" }

        Write-Host "=== RESTART API ONLY ==="
        Restart-Service -Name "NEXUS-AutoTrade-API" -Force
        Wait-Health

        $VerifyDedup = Get-Content $ProdDedup -Raw
        $VerifyCombined = Get-Content $ProdCombined -Raw
        if(-not $VerifyDedup.Contains('_DEDUP_VERSION = "v46"')) { throw "Production V46 marker missing" }
        if(-not $VerifyCombined.Contains($Hook)) { throw "Production dedup hook missing" }

        $SchemaScript = Join-Path $Work "verify_schema.py"
        @'
from app import db
with db.conn() as con:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chart_delivery_alert_incidents'"
    ).fetchone()
print("PASS" if row else "FAIL")
'@ | Set-Content -Path $SchemaScript -Encoding UTF8

        Push-Location $Prod
        try {
            $SchemaResult = (& $Python $SchemaScript | Out-String).Trim()
        } finally {
            Pop-Location
        }
        if($SchemaResult -ne "PASS") { throw "Dedup incident table was not created" }
        Write-Host "DEDUP SCHEMA: PASS"

        Write-Host ""
        Write-Host "CHART ALERT DEDUP V46: PASS"
        Write-Host "Backup: $Backup"
        Write-Host "Telegram Bot: UNTOUCHED"
        Write-Host "Trading EA/T05/T07: UNTOUCHED"
        Write-Host "MT5/MarketFeed: UNTOUCHED"
        Write-Warning "The existing incident may emit one final alert when V46 first claims it; unchanged repeats should then stop."
    }
    catch {
        if($Copied) {
            Write-Warning "DEPLOY FAILED - ROLLING BACK"
            $BakDedup = Join-Path $Backup $DedupRel
            $BakCombined = Join-Path $Backup $CombinedRel

            if(Test-Path $BakDedup) {
                Copy-Item $BakDedup $ProdDedup -Force
                Write-Host "RESTORED: $DedupRel"
            } elseif(Test-Path $ProdDedup) {
                Remove-Item $ProdDedup -Force
                Write-Host "REMOVED NEW: $DedupRel"
            }

            if(Test-Path $BakCombined) {
                Copy-Item $BakCombined $ProdCombined -Force
                Write-Host "RESTORED: $CombinedRel"
            }

            Restart-Service -Name "NEXUS-AutoTrade-API" -Force
            try { Wait-Health } catch {}
        }
        throw
    }
}
finally {
    if(Test-Path $Work) { Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue }
}
