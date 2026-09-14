param(
    [string]$Prod = "C:\NEXUS_DEPLOY\v066-clean-20260912",
    [int]$Limit = 5
)

$ErrorActionPreference = "Continue"
Set-Location $Prod

Write-Host "=== NEXUS CHART PIPELINE DIAGNOSTICS ==="
Write-Host "Runtime: $Prod"
Write-Host "Time   : $(Get-Date -Format o)"

Write-Host "`n=== 1. LATEST WEB_ADMIN SIGNAL / RECEIPT / CHART JOB / ASSET ==="

$env:NEXUS_DIAG_LIMIT = [string]$Limit

@'
import os
from pathlib import Path
from app import db

limit = max(1, min(int(os.environ.get("NEXUS_DIAG_LIMIT", "5")), 20))

with db.conn() as con:
    signals = con.execute("""
        SELECT id,code,symbol,timeframe,issuer_type,issuer_account,status,
               publication_stage,destination,free_message_id,vip_message_id,
               created_by,created_at
        FROM signals
        WHERE UPPER(COALESCE(issuer_type,''))='WEB_ADMIN'
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()

for signal in signals:
    sid = int(signal["id"])
    print("\n--- SIGNAL", signal["code"], "id=", sid, "---")
    print(dict(signal))

    with db.conn() as con:
        receipt = con.execute("""
            SELECT status,ticket,error_text,first_seen_at,executed_at
            FROM autotrade_signal_receipts
            WHERE signal_id=? AND platform='MT5'
            ORDER BY COALESCE(executed_at,first_seen_at) DESC
            LIMIT 1
        """, (sid,)).fetchone()

        job = con.execute("""
            SELECT id,status,requested_by,requested_at,attempt_count,
                   claimed_by_account,claimed_at,next_attempt_at,expires_at,
                   completed_at,failed_at,error_text,image_path,image_sha256,updated_at
            FROM signal_chart_capture_jobs
            WHERE signal_id=?
            ORDER BY id DESC
            LIMIT 1
        """, (sid,)).fetchone()

        events = con.execute("""
            SELECT event_type,result,reason,request_id,created_at,payload_json
            FROM signal_events
            WHERE signal_id=?
            ORDER BY id DESC
            LIMIT 30
        """, (sid,)).fetchall()

    print("RECEIPT:", dict(receipt) if receipt else None)
    print("CHART_JOB:", dict(job) if job else None)

    asset = db.get_mt5_signal_publication_asset(sid)
    if asset:
        p = Path(asset)
        print("PUBLICATION_ASSET:", asset)
        print("ASSET_EXISTS:", p.is_file())
        if p.is_file():
            print("ASSET_BYTES:", p.stat().st_size)
    else:
        print("PUBLICATION_ASSET: None")

    if job and job["image_path"]:
        p = Path(str(job["image_path"]))
        print("JOB_IMAGE_EXISTS:", p.is_file())
        if p.is_file():
            print("JOB_IMAGE_BYTES:", p.stat().st_size)

    print("EVENTS:")
    for event in events:
        print(dict(event))
'@ | .\.venv\Scripts\python.exe -

Write-Host "`n=== 2. API LOGS: CHART / PUBLICATION / HTTP ERRORS ==="
$apiLogs = @(
    "C:\NEXUS_API_stdout.log",
    "C:\NEXUS_API_stderr.log"
)
foreach ($path in $apiLogs) {
    if (Test-Path $path) {
        Write-Host "`n--- $path ---"
        Select-String -Path $path -Pattern "chart-capture|CHART_|PUBLICATION_|signal_charts|HTTP 4|HTTP 5|Traceback|ERROR" -ErrorAction SilentlyContinue |
            Select-Object -Last 120 |
            ForEach-Object { $_.Line }
    } else {
        Write-Host "Missing log: $path"
    }
}

Write-Host "`n=== 3. CHART AGENT COMMON DIAGNOSTIC LOG ==="
$diag = Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files\NEXUS_ChartAgent_diag3.log"
Write-Host "Diag: $diag"
if (Test-Path $diag) {
    Get-Content $diag -Tail 180
} else {
    Write-Host "ChartAgent diag log not found."
}

Write-Host "`n=== 4. MT5 EXPERT LOGS: CHART AGENT / SCREENSHOT / UPLOAD ==="
$today = Get-Date -Format "yyyyMMdd"
$mt5Logs = Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal\*\MQL5\Logs\$today.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending

foreach ($log in $mt5Logs) {
    Write-Host "`n--- $($log.FullName) ---"
    Select-String -Path $log.FullName -Pattern "NEXUS_ChartAgent|NEXUS ChartAgent|POLL_|Screenshot uploaded|Upload rejected|Upload transport failed|Job .* failed|CHART_|SCREENSHOT|TEMPLATE|WebRequest failed" -ErrorAction SilentlyContinue |
        Select-Object -Last 160 |
        ForEach-Object { $_.Line }
}

Write-Host "`n=== 5. CONFIGURED TIMEOUTS / CONTRACT ==="
Write-Host "ChartAgent poll          : 2s (default)"
Write-Host "ChartAgent HTTP timeout  : 8s (default)"
Write-Host "Chart load timeout       : 5s (default)"
Write-Host "Chart job TTL            : 300s (default)"
Write-Host "Chart claim stale lease  : 15s (current DB implementation)"
Write-Host "Backend PNG raw limit    : 5,000,000 bytes"
Write-Host "Result payload base64    : <= 7,000,000 chars"

Write-Host "`n=== IMPORTANT ==="
Write-Host "This script is read-only. It never calls /chart-capture/next, because that endpoint CLAIMS a job."
Write-Host "The current pipeline stores chart files locally under artifacts\signal_charts; there is no CDN/public image URL in the Telegram publication path."
