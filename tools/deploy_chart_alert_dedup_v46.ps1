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
$Python = Join-Path $Prod ".venv\Scripts\python.exe"
$HealthUrl = "https://api.nexustrade.ir/miniapp/api/health"

$Files = @(
    "app\autotrade\chart_alert_dedup_runtime.py",
    "app\combined_api.py"
)

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

if(-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }
if(-not (Test-Path $Python)) { throw "Production Python not found: $Python" }

Write-Host "=== NEXUS CHART ALERT DEDUP V46 ==="
Write-Host "Commit: $Commit"
Write-Host "Production: $Prod"

New-Item -ItemType Directory -Force -Path $Work,$Release,$Backup | Out-Null

try {
    git clone --filter=blob:none --no-checkout $RepoUrl $Repo
    if($LASTEXITCODE -ne 0) { throw "git clone failed" }

    git -C $Repo fetch origin $Commit
    if($LASTEXITCODE -ne 0) { throw "git fetch failed" }

    $Resolved = (git -C $Repo rev-parse $Commit).Trim()
    if($Resolved -ne $Commit) { throw "Exact commit verification failed" }

    git -C $Repo archive --format=zip --output=$Archive $Commit app/autotrade/chart_alert_dedup_runtime.py app/combined_api.py tests/test_chart_alert_dedup_v46.py
    if($LASTEXITCODE -ne 0 -or -not (Test-Path $Archive)) { throw "git archive failed" }

    Expand-Archive -Path $Archive -DestinationPath $Release -Force

    $Dedup = Get-Content (Join-Path $Release "app\autotrade\chart_alert_dedup_runtime.py") -Raw
    $Combined = Get-Content (Join-Path $Release "app\combined_api.py") -Raw

    if(-not $Dedup.Contains('_DEDUP_VERSION = "v46"')) { throw "V46 marker missing" }
    if(-not $Dedup.Contains("INSERT OR IGNORE INTO chart_delivery_alert_incidents")) { throw "Durable incident claim missing" }
    if(-not $Dedup.Contains("guard._alert_due = durable_alert_due")) { throw "Alert gate replacement missing" }
    if(-not $Combined.Contains("install_chart_alert_dedup_runtime(app)")) { throw "Dedup install missing" }
    if($Combined.IndexOf("install_chart_delivery_guard(app)") -gt $Combined.IndexOf("install_chart_alert_dedup_runtime(app)")) { throw "Dedup install order invalid" }

    Write-Host "CONTRACT: PASS"

    Push-Location $Release
    try {
        & $Python -m py_compile app\autotrade\chart_alert_dedup_runtime.py app\combined_api.py
        if($LASTEXITCODE -ne 0) { throw "Python compile failed" }

        & $Python -m pytest tests\test_chart_alert_dedup_v46.py -q
        if($LASTEXITCODE -ne 0) { throw "V46 tests failed" }
    } finally {
        Pop-Location
    }

    Write-Host "STAGING TESTS: PASS"

    foreach($Rel in $Files) {
        $Current = Join-Path $Prod $Rel
        if(Test-Path $Current) {
            $Bak = Join-Path $Backup $Rel
            New-Item -ItemType Directory -Force -Path (Split-Path $Bak -Parent) | Out-Null
            Copy-Item $Current $Bak -Force
            Write-Host "BACKUP: $Rel"
        }
    }

    $Copied = $false
    try {
        foreach($Rel in $Files) {
            $Src = Join-Path $Release $Rel
            $Dst = Join-Path $Prod $Rel
            New-Item -ItemType Directory -Force -Path (Split-Path $Dst -Parent) | Out-Null
            Copy-Item $Src $Dst -Force
            Write-Host "DEPLOYED: $Rel"
        }
        $Copied = $true

        & $Python -m py_compile (Join-Path $Prod "app\autotrade\chart_alert_dedup_runtime.py") (Join-Path $Prod "app\combined_api.py")
        if($LASTEXITCODE -ne 0) { throw "Production Python compile failed" }

        Write-Host "=== RESTART API ONLY ==="
        Restart-Service -Name "NEXUS-AutoTrade-API" -Force
        Wait-Health

        $ProdDedup = Get-Content (Join-Path $Prod "app\autotrade\chart_alert_dedup_runtime.py") -Raw
        if(-not $ProdDedup.Contains('_DEDUP_VERSION = "v46"')) { throw "Production V46 marker missing" }

        Write-Host ""
        Write-Host "CHART ALERT DEDUP V46: PASS"
        Write-Host "Backup: $Backup"
        Write-Host "Telegram Bot: UNTOUCHED"
        Write-Host "Trading EA/T05/T07: UNTOUCHED"
        Write-Host "MT5/MarketFeed: UNTOUCHED"
        Write-Warning "The existing incident may emit one final alert when V46 first claims it; unchanged repeats should then stop."
    } catch {
        if($Copied) {
            Write-Warning "DEPLOY FAILED - ROLLING BACK"
            foreach($Rel in $Files) {
                $Bak = Join-Path $Backup $Rel
                if(Test-Path $Bak) {
                    Copy-Item $Bak (Join-Path $Prod $Rel) -Force
                    Write-Host "RESTORED: $Rel"
                }
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
