param(
    [Parameter(Mandatory=$true)]
    [string]$Commit,
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912"
)

$ErrorActionPreference = "Stop"
$Evidence = "C:\NEXUS_DEPLOY\_stage-evidence\chart-delivery-v24-$Commit.json"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Prod "_backup\admin-positions-v24-$Stamp"

if (-not (Test-Path $Prod)) { throw "Production runtime not found: $Prod" }
if (-not (Test-Path $Evidence)) { throw "Mandatory V24 staging evidence not found: $Evidence" }
$E = Get-Content $Evidence -Raw | ConvertFrom-Json
if ([string]$E.commit -ne $Commit) { throw "Evidence commit mismatch" }
if (-not $E.tests_pass -or -not $E.admin_positions_cache_bust_pass) { throw "Admin Positions V24 staging evidence is not PASS" }
$Release = [string]$E.release
if (-not (Test-Path $Release)) { throw "Staged release not found: $Release" }

$Files = @(
    "miniapp\admin.html",
    "miniapp\admin-positions-v24.css",
    "miniapp\vazirmatn.css"
)
foreach ($Rel in $Files) {
    if (-not (Test-Path (Join-Path $Release $Rel))) { throw "Staged UI file missing: $Rel" }
}

Write-Host "=== BACKUP ADMIN UI ==="
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
foreach ($Rel in $Files) {
    $Source = Join-Path $Prod $Rel
    if (Test-Path $Source) {
        $Target = Join-Path $Backup $Rel
        New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
        Copy-Item $Source $Target -Force
    }
}
Write-Host "Backup:" $Backup

Write-Host "`n=== TARGETED ADMIN POSITIONS V24 DEPLOY ==="
foreach ($Rel in $Files) {
    $Source = Join-Path $Release $Rel
    $Target = Join-Path $Prod $Rel
    Copy-Item $Source $Target -Force
    Write-Host "DEPLOYED:" $Rel
}

$Admin = Get-Content (Join-Path $Prod "miniapp\admin.html") -Raw
if ($Admin -notmatch 'admin-positions-v24\.css\?v=20260915-positions1') { throw "Admin HTML V24 CSS marker missing" }
if ($Admin -notmatch 'vazirmatn\.css\?v=20260915-v24-positions1') { throw "Admin HTML typography cache-bust missing" }
$Css = Get-Content (Join-Path $Prod "miniapp\admin-positions-v24.css") -Raw
foreach ($Marker in @("#positions", ".admin-position-levels b", ".trade-actions button.danger")) {
    if (-not $Css.Contains($Marker)) { throw "Positions CSS marker missing: $Marker" }
}

Write-Host "`n=== PUBLIC STATIC CHECK ==="
foreach ($Url in @(
    "https://api.nexustrade.ir/miniapp/admin.html?v=20260915-v24-positions1",
    "https://api.nexustrade.ir/miniapp/admin-positions-v24.css?v=20260915-positions1",
    "https://api.nexustrade.ir/miniapp/vazirmatn.css?v=20260915-v24-positions1"
)) {
    $R = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 15
    Write-Host "HTTP" $R.StatusCode "|" $R.Headers["Content-Type"] "|" $Url
    if ($R.StatusCode -ne 200) { throw "Public UI check failed: $Url" }
}

Write-Host "`nADMIN POSITIONS V24 DEPLOY: PASS"
Write-Host "No API restart."
Write-Host "No Telegram restart."
Write-Host "No MT5 files changed by this UI deploy."
