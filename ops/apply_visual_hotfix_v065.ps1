param(
    [string]$Root = 'C:\NEXUS_V065_FINAL_TEST'
)

$ErrorActionPreference = 'Stop'

$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Card   = Join-Path $Root 'app\signals\card_generator.py'
$Api    = Join-Path $Root 'app\autotrade\api.py'
$Svc    = 'NEXUS-AutoTrade-API'
$Stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup = "C:\NEXUS_BACKUPS\VisualHotfix_$Stamp"

New-Item -ItemType Directory -Path $Backup -Force | Out-Null

Write-Host "`n===== NEXUS VISUAL HOTFIX v0.6.5 =====" -ForegroundColor Cyan
Write-Host "ROOT   : $Root"
Write-Host "BACKUP : $Backup"

foreach ($Path in @($Python, $Card, $Api)) {
    if (-not (Test-Path $Path)) {
        throw "STOP: required path not found: $Path"
    }
}

Copy-Item $Card (Join-Path $Backup 'card_generator.py') -Force
Copy-Item $Api  (Join-Path $Backup 'api.py') -Force

$Patch = @'
from pathlib import Path
import re
import sys

root = Path(r"C:\NEXUS_V065_FINAL_TEST")
card_path = root / "app" / "signals" / "card_generator.py"
api_path = root / "app" / "autotrade" / "api.py"

card = card_path.read_text(encoding="utf-8-sig")
api = api_path.read_text(encoding="utf-8-sig")

MARKER = "NEXUS_VISUAL_V2_20260911"

if MARKER in card and MARKER in api:
    print("PATCH STATUS : ALREADY APPLIED")
    raise SystemExit(0)

frame_pattern = re.compile(
    r"def build_chart_frame\(chart_bytes: bytes \| None\) -> bytes:\r?\n.*?(?=\r?\n\r?\ndef _row\()",
    re.S,
)

new_frame = '''def build_chart_frame(chart_bytes: bytes | None) -> bytes:
    """NEXUS Visual V2: minimal Carbon/Cobalt/Cyan chart-only frame.

    Signal details belong in the Telegram caption, not inside the image.
    The MT5 chart remains the visual authority and is never cropped.
    """
    # NEXUS_VISUAL_V2_20260911
    has_chart = bool(chart_bytes)
    chart = _load_chart(chart_bytes)

    max_chart_w, max_chart_h = 1280, 900
    scale = min(max_chart_w / chart.width, max_chart_h / chart.height, 1.0)
    if scale != 1.0:
        chart = chart.resize(
            (max(1, int(chart.width * scale)), max(1, int(chart.height * scale))),
            Image.Resampling.LANCZOS,
        )

    # Carbon shell + compact cobalt/cyan edge. No legacy side panel and no
    # signal-data flash card inside the image.
    pad = 14
    accent_h = 5
    canvas_w = chart.width + pad * 2
    canvas_h = chart.height + pad * 2 + accent_h
    canvas = Image.new("RGB", (canvas_w, canvas_h), (4, 9, 15))
    draw = ImageDraw.Draw(canvas)

    chart_x = pad
    chart_y = pad + accent_h
    canvas.paste(chart, (chart_x, chart_y))

    # Cobalt border and cyan top accent match the approved NEXUS visual system.
    draw.rectangle(
        (chart_x - 2, chart_y - 2, chart_x + chart.width + 1, chart_y + chart.height + 1),
        outline=(26, 92, 176),
        width=2,
    )
    draw.rectangle((0, 0, canvas_w - 1, accent_h - 1), fill=(61, 214, 255))

    # Fail-visible fallback only when MT5 supplied no usable chart. This is not
    # a signal card; all trade data remains in the Telegram caption.
    if not has_chart:
        _text(draw, (34, 34), "NEXUS", 30, bold=True, fill=(61, 214, 255))
        _text(draw, (34, 74), "CHART UNAVAILABLE", 20, bold=True, fill=(165, 179, 195))

    out = BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()
'''

card, count = frame_pattern.subn(new_frame.rstrip(), card, count=1)
if count != 1:
    raise RuntimeError(f"STOP: build_chart_frame replacement count={count}")

publish_pattern = re.compile(
    r'''    try:\r?\n        if raw:.*?        chart_frame = b""''',
    re.S,
)

new_publish = '''    # NEXUS_VISUAL_V2_20260911
    # Always publish the real MT5 chart frame. If the chart is unavailable,
    # build_chart_frame(None) creates a neutral branded fallback; the legacy
    # signal-card image is intentionally not used in this publication path.
    try:
        chart_frame = await asyncio.to_thread(build_chart_frame, raw if raw else None)
    except Exception as exc:
        errors.append(f"CHART_RENDER: {exc}")
        chart_frame = b""'''

api, count = publish_pattern.subn(new_publish, api, count=1)
if count != 1:
    raise RuntimeError(f"STOP: publisher visual replacement count={count}")

caption_pattern = re.compile(
    r'''    caption = \(\r?\n.*?\r?\n    \)\r?\n\r?\n    # Preserve already-published destinations''',
    re.S,
)

new_caption = '''    # NEXUS_VISUAL_V2_20260911
    direction = str(row["direction"] or "").upper()
    direction_icon = "🔵" if direction in {"BUY", "LONG"} else "🔴"
    status_label = "PENDING" if exec_status == "PENDING" else "ACTIVE"
    status_icon = "🟠" if status_label == "PENDING" else "🟢"
    trailing_label = str(row["trailing_code"] or "OFF")

    caption = (
        "<b>⚡ NEXUS SIGNAL</b>\n"
        f"<code>{row['code']}</code>  •  <b>{order_type}</b>\n\n"
        f"{direction_icon} <b>{str(row['symbol']).upper()} · {direction}</b>\n"
        f"⏱ <b>{str(row['timeframe'] or 'M5').upper()}</b>\n\n"
        f"📍 Entry  <code>{float(row['entry_price']):g}</code>\n"
        f"🛑 SL     <code>{float(row['stop_loss']):g}</code>\n"
        f"{tp_lines}\n\n"
        f"📊 Risk: <b>{float(row['risk_percent']):g}%</b>\n"
        f"⚙️ Trailing: <b>{trailing_label}</b>\n"
        f"{status_icon} Status: <b>{status_label}</b>"
    )

    # Preserve already-published destinations'''

api, count = caption_pattern.subn(new_caption, api, count=1)
if count != 1:
    raise RuntimeError(f"STOP: caption replacement count={count}")

card_path.write_text(card, encoding="utf-8", newline="\n")
api_path.write_text(api, encoding="utf-8", newline="\n")

print("PATCH STATUS : APPLIED")
print("CARD MARKER  :", MARKER in card)
print("API MARKER   :", MARKER in api)
'@

try {
    Push-Location $Root
    try {
        $Patch | & $Python -
        if ($LASTEXITCODE -ne 0) {
            throw "Python patch step failed with exit code $LASTEXITCODE"
        }

        Write-Host "`n===== PYTHON COMPILE CHECK =====" -ForegroundColor Yellow
        & $Python -m py_compile $Card $Api
        if ($LASTEXITCODE -ne 0) {
            throw "py_compile failed with exit code $LASTEXITCODE"
        }
        Write-Host 'PY_COMPILE : PASS' -ForegroundColor Green

        Write-Host "`n===== RENDER SMOKE TEST =====" -ForegroundColor Yellow
        $Smoke = @'
from io import BytesIO
from pathlib import Path
from PIL import Image
from app.signals.card_generator import build_chart_frame

source = Image.new("RGB", (1280, 720), (18, 24, 32))
b = BytesIO()
source.save(b, format="PNG")
out = build_chart_frame(b.getvalue())
img = Image.open(BytesIO(out))

if img.width > 1340:
    raise RuntimeError(f"legacy side panel appears present: width={img.width}")
if img.height > 780:
    raise RuntimeError(f"unexpected framed height={img.height}")
if len(out) < 1000:
    raise RuntimeError("rendered PNG is unexpectedly small")

print(f"RENDER_SIZE  : {img.width}x{img.height}")
print(f"RENDER_BYTES : {len(out)}")
print("LEGACY_SIDE_PANEL : ABSENT")
'@
        $Smoke | & $Python -
        if ($LASTEXITCODE -ne 0) {
            throw "render smoke test failed with exit code $LASTEXITCODE"
        }

        Write-Host "`n===== SOURCE MARKERS =====" -ForegroundColor Yellow
        Select-String -Path $Card,$Api -Pattern 'NEXUS_VISUAL_V2_20260911' |
            Select-Object Path,LineNumber,Line |
            Format-Table -AutoSize

        Write-Host "`n===== RESTART API ONLY =====" -ForegroundColor Yellow
        Restart-Service $Svc

        $Deadline = (Get-Date).AddSeconds(45)
        $Healthy = $false
        $LastHealthError = $null

        while ((Get-Date) -lt $Deadline) {
            Start-Sleep -Seconds 2
            try {
                $Health = Invoke-WebRequest `
                    -Uri 'http://127.0.0.1:8080/api/v1/autotrade/health' `
                    -UseBasicParsing `
                    -TimeoutSec 5
                if ($Health.StatusCode -eq 200) {
                    $Healthy = $true
                    break
                }
            }
            catch {
                $LastHealthError = $_.Exception.Message
            }
        }

        if (-not $Healthy) {
            throw "API health failed after restart: $LastHealthError"
        }

        Write-Host 'API HEALTH : PASS' -ForegroundColor Green
        Write-Host "`n=============================================" -ForegroundColor Green
        Write-Host 'NEXUS VISUAL HOTFIX : PASS' -ForegroundColor Green
        Write-Host '=============================================' -ForegroundColor Green
        Write-Host 'Changed        : chart frame + Telegram signal caption only'
        Write-Host 'AutoTrade EA   : UNCHANGED'
        Write-Host 'ChartAgent     : UNCHANGED'
        Write-Host 'Trailing       : UNCHANGED'
        Write-Host 'Open trades    : UNCHANGED'
        Write-Host 'Database       : UNCHANGED'
        Write-Host "Backup         : $Backup"
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Host "`nHOTFIX FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Rolling back the two visual source files...' -ForegroundColor Yellow

    Copy-Item (Join-Path $Backup 'card_generator.py') $Card -Force
    Copy-Item (Join-Path $Backup 'api.py') $Api -Force

    try {
        Restart-Service $Svc
        Start-Sleep -Seconds 3
    }
    catch {
        Write-Host "Rollback restart warning: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    throw
}
