param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912",
    [int]$Minutes = 60
)

$ErrorActionPreference = "Stop"
$Minutes = [Math]::Max(5, [Math]::Min($Minutes, 1440))

Write-Host "=== NEXUS CHART DELIVERY V24 DIAGNOSTICS ==="
Write-Host "Production:" $Prod
Write-Host "Window    :" $Minutes "minutes"
Write-Host "Mode      : READ-ONLY (never calls /chart-capture/next)"

if (-not (Test-Path $Prod)) { throw "Production path not found: $Prod" }
$Python = Join-Path $Prod ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = (Get-Command python -ErrorAction Stop).Source }

Write-Host "`n=== 1. DATABASE / JOB STATE ==="
$env:NEXUS_DIAG_PROD = $Prod
$env:NEXUS_DIAG_MINUTES = [string]$Minutes
@'
import json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

prod = Path(os.environ["NEXUS_DIAG_PROD"])
sys.path.insert(0, str(prod))
from app import db

cutoff = (datetime.now(timezone.utc) - timedelta(minutes=int(os.environ["NEXUS_DIAG_MINUTES"]))).isoformat()
with db.conn() as con:
    rows = con.execute("""
        SELECT j.id AS job_id,j.signal_id,s.code,s.symbol,s.timeframe,j.status,j.attempt_count,
               j.claimed_by_account,j.error_text,j.image_path,j.updated_at,j.expires_at,
               s.publication_stage,s.free_message_id,s.vip_message_id
        FROM signal_chart_capture_jobs j
        JOIN signals s ON s.id=j.signal_id
        WHERE j.updated_at>=?
        ORDER BY j.updated_at DESC,j.id DESC LIMIT 30
    """, (cutoff,)).fetchall()
    events = con.execute("""
        SELECT e.id,e.signal_id,s.code,e.event_type,e.result,e.reason,e.event_time
        FROM signal_events_v060 e
        JOIN signals s ON s.id=e.signal_id
        WHERE e.event_time>=? AND e.event_type IN (
          'CHART_JOB_CREATED','CHART_JOB_CLAIMED','CHART_CAPTURED','CHART_UPLOAD_FAILED',
          'PUBLICATION_FALLBACK_QUEUED','CHART_REPAIR_QUEUED','CHART_REPAIR_APPLIED',
          'CHART_REPAIR_FAILED','TELEGRAM_PUBLISHED','TELEGRAM_PUBLISH_FAILED'
        )
        ORDER BY e.id DESC LIMIT 50
    """, (cutoff,)).fetchall()

print(f"DB_PATH={db.DB_PATH}")
print("\nRECENT JOBS")
for r in rows:
    d=dict(r)
    p=d.get("image_path")
    d["asset_exists"] = bool(p and Path(p).is_file())
    d["asset_bytes"] = Path(p).stat().st_size if d["asset_exists"] else 0
    print(json.dumps(d, ensure_ascii=False, default=str))
print("\nRECENT PIPELINE EVENTS")
for r in events:
    print(json.dumps(dict(r), ensure_ascii=False, default=str))
'@ | & $Python -
if ($LASTEXITCODE -ne 0) { throw "DB diagnostics failed" }

Write-Host "`n=== 2. PUBLIC HEALTH ENDPOINT (AUTH READ FROM .env, NOT PRINTED) ==="
$EnvFile = Join-Path $Prod ".env"
$Token = $null
$Account = $null
if (Test-Path $EnvFile) {
    foreach ($Line in Get-Content $EnvFile) {
        if ($Line -match '^\s*NEXUS_ADMIN_TOKEN\s*=\s*(.+?)\s*$') { $Token = $Matches[1].Trim('"','''') }
        if ($Line -match '^\s*NEXUS_ADMIN_MT5_ACCOUNTS\s*=\s*(.+?)\s*$') { $Account = ($Matches[1].Trim('"','''') -split ',')[0].Trim() }
    }
}
if ($Token -and $Account) {
    try {
        $Headers = @{
            "X-MT5-Account" = $Account
            "X-NEXUS-Admin-Token" = $Token
        }
        $Url = "https://api.nexustrade.ir/api/v1/autotrade/admin/chart-capture/health?minutes=$Minutes"
        $Health = Invoke-RestMethod -Uri $Url -Headers $Headers -Method GET -TimeoutSec 15
        $Health | ConvertTo-Json -Depth 8
    } catch {
        Write-Warning ("Health endpoint unavailable: " + $_.Exception.Message)
    }
} else {
    Write-Warning "NEXUS_ADMIN_TOKEN/account not resolved from .env; HTTP health check skipped."
}

Write-Host "`n=== 3. CHART AGENT LOG MARKERS ==="
$Today = Get-Date -Format "yyyyMMdd"
$Logs = Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal\*\MQL5\Logs\$Today.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
if ($Logs) {
    Select-String -Path $Logs.FullName -Pattern @(
        "NEXUS ChartAgent",
        "POLL_JOB_AVAILABLE",
        "SCALE_VISIBLE_RANGE_CONFIRMED",
        "SCALE_FIXED_RANGE_CONFIRMED",
        "SCALE_AUTOSCALE_FALLBACK",
        "SCREENSHOT_UPLOAD_CONFIRMED",
        "Screenshot uploaded",
        "RANGE_VERIFY_FAILED",
        "HTTP=429",
        "HTTP=502",
        "HTTP=503",
        "HTTP=504"
    ) -ErrorAction SilentlyContinue |
        Select-Object -Last 160 |
        ForEach-Object { $_.Line }
} else {
    Write-Warning "No MT5 log file found for $Today"
}

Write-Host "`n=== 4. STATIC DEPLOY MARKERS ==="
$Guard = Join-Path $Prod "app\autotrade\chart_delivery_guard.py"
$Combined = Join-Path $Prod "app\combined_api.py"
$Agent = Join-Path $Prod "mt5\NEXUS_ChartAgent\NEXUS_ChartAgent.mq5"
foreach ($Path in @($Guard,$Combined,$Agent)) {
    if (Test-Path $Path) { Write-Host "FOUND:" $Path } else { Write-Warning "MISSING: $Path" }
}
if (Test-Path $Guard) {
    Select-String -Path $Guard -Pattern "PUBLISHED_REPAIR_PENDING|CHART_REPAIR_APPLIED|chart-capture/health|account.*limit" -ErrorAction SilentlyContinue
}
if (Test-Path $Agent) {
    Select-String -Path $Agent -Pattern "chart-agent-reliability-v24|SCALE_FIXED_RANGE_CONFIRMED|PostWithRetry|SCREENSHOT_UPLOAD_CONFIRMED" -ErrorAction SilentlyContinue
}

Write-Host "`nDIAGNOSTIC COMPLETE — no job was claimed or mutated."
