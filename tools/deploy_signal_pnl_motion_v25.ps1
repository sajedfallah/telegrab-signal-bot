param(
    [string]$Commit = "747ca946d556f79fb8c9a3184f27e9301869b6b2",
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/sajedfallah/telegrab-signal-bot.git"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Work = "C:\NEXUS_DEPLOY\_stage-signal-pnl-motion-v25-$Stamp"
$Repo = Join-Path $Work "repo"
$Release = Join-Path $Work "release"
$Backup = Join-Path $Prod "_backup\signal-pnl-motion-v25-$Stamp"
$HealthUrl = "https://api.nexustrade.ir/miniapp/api/health"
$CssUrl = "https://api.nexustrade.ir/miniapp/signal-pnl-motion-v25.css?v=20260918-pnlmotion1"

$Files = @(
    "miniapp\admin-signal-v13.js",
    "miniapp\admin.html",
    "miniapp\index.html",
    "miniapp\signal-pnl-motion-v25.css",
    "miniapp\signals-v2.js"
)

function Assert-Health {
    param([string]$Stage)
    try {
        $r = Invoke-RestMethod $HealthUrl -TimeoutSec 15
        if($r.ok -ne $true) { throw "health.ok != true" }
        Write-Host "$Stage API HEALTH: PASS"
    } catch {
        throw "$Stage API health failed: $($_.Exception.Message)"
    }
}

function Assert-LiveCss {
    for($i = 1; $i -le 10; $i++) {
        try {
            $response = Invoke-WebRequest $CssUrl -UseBasicParsing -TimeoutSec 15 -Headers @{
                "Cache-Control" = "no-cache"
                "Pragma" = "no-cache"
            }
            if($response.StatusCode -eq 200 -and $response.Content -match "nexusPnlBorderSpinV25") {
                Write-Host "LIVE CSS VERIFY: PASS"
                return
            }
        } catch {}
        Start-Sleep -Seconds 2
    }
    throw "Live CSS verification failed"
}

if(-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }

Write-Host "=== NEXUS SIGNAL PNL MOTION V25 DEPLOY ==="
Write-Host "Production: $Prod"
Write-Host "Commit: $Commit"

Assert-Health -Stage "PRE-DEPLOY"
New-Item -ItemType Directory -Force -Path $Work, $Release, $Backup | Out-Null

Write-Host "=== FETCH EXACT COMMIT ==="
git clone --filter=blob:none --no-checkout $RepoUrl $Repo
if($LASTEXITCODE -ne 0) { throw "git clone failed" }
git -C $Repo fetch origin $Commit
if($LASTEXITCODE -ne 0) { throw "git fetch exact commit failed" }
$Resolved = (git -C $Repo rev-parse $Commit).Trim()
if($Resolved -ne $Commit) { throw "Exact commit verification failed: expected $Commit got $Resolved" }

Write-Host "=== ARCHIVE TARGET FILES ONLY ==="
git -C $Repo archive $Commit miniapp/admin-signal-v13.js miniapp/admin.html miniapp/index.html miniapp/signal-pnl-motion-v25.css miniapp/signals-v2.js | tar -xf - -C $Release
if($LASTEXITCODE -ne 0) { throw "git archive failed" }

foreach($Rel in $Files) {
    $StageFile = Join-Path $Release $Rel
    if(-not (Test-Path $StageFile)) { throw "Staged file missing: $Rel" }
}

Write-Host "=== CONTRACT CHECK ==="
$UserJs = Get-Content (Join-Path $Release "miniapp\signals-v2.js") -Raw
$AdminJs = Get-Content (Join-Path $Release "miniapp\admin-signal-v13.js") -Raw
$IndexHtml = Get-Content (Join-Path $Release "miniapp\index.html") -Raw
$AdminHtml = Get-Content (Join-Path $Release "miniapp\admin.html") -Raw
$Css = Get-Content (Join-Path $Release "miniapp\signal-pnl-motion-v25.css") -Raw

if(-not $UserJs.Contains("if (status !== 'LIVE') return '';")) { throw "User LIVE gate missing" }
if(-not $UserJs.Contains("IN_PROFIT") -or -not $UserJs.Contains("IN_LOSS")) { throw "User PnL state mapping missing" }
if(-not $AdminJs.Contains("function adminSignalPnlClass")) { throw "Admin PnL class mapper missing" }
if(-not $AdminJs.Contains("if (status !== 'LIVE') return '';")) { throw "Admin LIVE gate missing" }
if(-not $IndexHtml.Contains("signal-pnl-motion-v25.css?v=20260918-pnlmotion1")) { throw "User stylesheet link missing" }
if(-not $AdminHtml.Contains("signal-pnl-motion-v25.css?v=20260918-pnlmotion1")) { throw "Admin stylesheet link missing" }
if(-not $Css.Contains("@keyframes nexusPnlBorderSpinV25")) { throw "PnL animation keyframes missing" }
if(-not $Css.Contains(".signal-v2-card.pnl-profit") -or -not $Css.Contains(".signal-v2-card.pnl-loss")) { throw "User PnL selectors missing" }
if(-not $Css.Contains("#signalList .card.pnl-profit") -or -not $Css.Contains("#signalList .card.pnl-loss")) { throw "Admin PnL selectors missing" }
Write-Host "CONTRACT: PASS"

Write-Host "=== BACKUP CURRENT PRODUCTION FILES ==="
$Existing = @{}
foreach($Rel in $Files) {
    $Current = Join-Path $Prod $Rel
    $Existing[$Rel] = Test-Path $Current
    if($Existing[$Rel]) {
        $Bak = Join-Path $Backup $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $Bak -Parent) | Out-Null
        Copy-Item $Current $Bak -Force
        Write-Host "BACKUP: $Rel"
    } else {
        Write-Host "BACKUP: $Rel did not previously exist"
    }
}

$Copied = $false
try {
    Write-Host "=== TARGETED COPY ==="
    foreach($Rel in $Files) {
        $Src = Join-Path $Release $Rel
        $Dst = Join-Path $Prod $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $Dst -Parent) | Out-Null
        Copy-Item $Src $Dst -Force
        Write-Host "DEPLOYED: $Rel"
    }
    $Copied = $true

    Write-Host "=== LOCAL PRODUCTION VERIFY ==="
    $ProdCss = Get-Content (Join-Path $Prod "miniapp\signal-pnl-motion-v25.css") -Raw
    $ProdIndex = Get-Content (Join-Path $Prod "miniapp\index.html") -Raw
    $ProdAdmin = Get-Content (Join-Path $Prod "miniapp\admin.html") -Raw

    if(-not $ProdCss.Contains("nexusPnlBorderSpinV25")) { throw "Production CSS marker missing" }
    if(-not $ProdIndex.Contains("signal-pnl-motion-v25.css?v=20260918-pnlmotion1")) { throw "Production user HTML stylesheet marker missing" }
    if(-not $ProdAdmin.Contains("signal-pnl-motion-v25.css?v=20260918-pnlmotion1")) { throw "Production admin HTML stylesheet marker missing" }

    Assert-Health -Stage "POST-DEPLOY"
    Assert-LiveCss

    Write-Host ""
    Write-Host "NEXUS SIGNAL PNL MOTION V25: PASS"
    Write-Host "Commit: $Commit"
    Write-Host "Backup: $Backup"
    Write-Host "No git pull/reset/checkout was used on Production."
    Write-Host "No backend/Telegram/MT5 service restart was required."
}
catch {
    Write-Warning "DEPLOY FAILED: $($_.Exception.Message)"
    if($Copied) {
        Write-Host "=== ROLLBACK ==="
        foreach($Rel in $Files) {
            $Dst = Join-Path $Prod $Rel
            if($Existing[$Rel]) {
                $Bak = Join-Path $Backup $Rel
                if(Test-Path $Bak) {
                    Copy-Item $Bak $Dst -Force
                    Write-Host "RESTORED: $Rel"
                }
            } else {
                if(Test-Path $Dst) {
                    Remove-Item $Dst -Force
                    Write-Host "REMOVED NEW FILE: $Rel"
                }
            }
        }
        try { Assert-Health -Stage "ROLLBACK" } catch { Write-Warning $_.Exception.Message }
    }
    throw
}
finally {
    if(Test-Path $Work) { Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue }
}
