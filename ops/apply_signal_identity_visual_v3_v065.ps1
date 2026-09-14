param(
    [string]$Root = 'C:\NEXUS_V065_FINAL_TEST'
)

$ErrorActionPreference = 'Stop'

$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Api    = Join-Path $Root 'app\autotrade\api.py'
$Card   = Join-Path $Root 'app\signals\card_generator.py'
$DbFile = Join-Path $Root 'nexus_bot.db'
$Svc    = 'NEXUS-AutoTrade-API'
$Stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup = "C:\NEXUS_BACKUPS\SignalIdentityVisualV3_$Stamp"

New-Item -ItemType Directory -Path $Backup -Force | Out-Null

Write-Host "`n===== NEXUS SIGNAL IDENTITY + VISUAL V3 =====" -ForegroundColor Cyan
Write-Host "ROOT   : $Root"
Write-Host "BACKUP : $Backup"

foreach ($Path in @($Python, $Api, $Card, $DbFile)) {
    if (-not (Test-Path $Path)) {
        throw "STOP: required path not found: $Path"
    }
}

Write-Host "`n===== PREFLIGHT =====" -ForegroundColor Yellow
& $Python -m py_compile $Api $Card
if ($LASTEXITCODE -ne 0) {
    throw 'STOP: current Python source does not compile'
}
Write-Host 'CURRENT SOURCE COMPILE : PASS' -ForegroundColor Green

$Health = Invoke-WebRequest `
    -Uri 'http://127.0.0.1:8080/api/v1/autotrade/health' `
    -UseBasicParsing `
    -TimeoutSec 5
if ($Health.StatusCode -ne 200) {
    throw "STOP: current API health HTTP $($Health.StatusCode)"
}
Write-Host 'CURRENT API HEALTH     : PASS' -ForegroundColor Green

Copy-Item $Api  (Join-Path $Backup 'api.py') -Force
Copy-Item $Card (Join-Path $Backup 'card_generator.py') -Force

# SQLite-consistent backup, including WAL state.
$DbBackup = Join-Path $Backup 'nexus_bot.db'
$DbBackupPy = @'
import sqlite3
from pathlib import Path
src = Path(r"C:\NEXUS_V065_FINAL_TEST\nexus_bot.db")
dst = Path(r"__DB_BACKUP__")
with sqlite3.connect(src) as source, sqlite3.connect(dst) as target:
    source.backup(target)
print("DB_BACKUP : PASS")
'@.Replace('__DB_BACKUP__', $DbBackup.Replace('\','\\'))
$DbBackupPy | & $Python -
if ($LASTEXITCODE -ne 0) {
    throw 'STOP: SQLite backup failed'
}

$Patch = @'
from pathlib import Path
import re
import ast

root = Path(r"C:\NEXUS_V065_FINAL_TEST")
api_path = root / "app" / "autotrade" / "api.py"
card_path = root / "app" / "signals" / "card_generator.py"

api = api_path.read_text(encoding="utf-8-sig")
card = card_path.read_text(encoding="utf-8-sig")

API_MARKER = "NEXUS_SIGNAL_PUBLIC_CODE_V1"
CARD_MARKER = "NEXUS_VISUAL_V3_LOGO_20260911"
CAPTION_MARKER = "NEXUS_SIGNAL_CAPTION_V3_20260911"

if "NEXUS_VISUAL_V2_20260911" not in api or "NEXUS_VISUAL_V2_20260911" not in card:
    raise RuntimeError("STOP: expected Visual V2 markers are missing")

if "NEXUS_CHART_RATE_BUCKETS_V1" not in api:
    raise RuntimeError("STOP: chart rate-limit fix marker is missing")

# ------------------------------------------------------------------
# 1) Chart frame V3: preserve V2 shell, add real NEXUS logo in a
# compact brand strip. No legacy 260px side panel and no flash card.
# ------------------------------------------------------------------
if CARD_MARKER not in card:
    frame_pattern = re.compile(
        r"def build_chart_frame\(chart_bytes: bytes \| None\) -> bytes:\r?\n.*?(?=\r?\n\r?\ndef _row\()",
        re.S,
    )

    new_frame = r'''def build_chart_frame(chart_bytes: bytes | None) -> bytes:
    """NEXUS Visual V3: real chart + compact corporate logo header."""
    # NEXUS_VISUAL_V2_20260911
    # NEXUS_VISUAL_V3_LOGO_20260911
    has_chart = bool(chart_bytes)
    chart = _load_chart(chart_bytes)

    max_chart_w, max_chart_h = 1280, 900
    scale = min(max_chart_w / chart.width, max_chart_h / chart.height, 1.0)
    if scale != 1.0:
        chart = chart.resize(
            (max(1, int(chart.width * scale)), max(1, int(chart.height * scale))),
            Image.Resampling.LANCZOS,
        )

    pad = 14
    accent_h = 5
    brand_h = 64
    canvas_w = chart.width + pad * 2
    canvas_h = chart.height + pad * 2 + accent_h + brand_h
    canvas = Image.new("RGB", (canvas_w, canvas_h), (4, 9, 15))
    draw = ImageDraw.Draw(canvas)

    # Corporate cyan accent.
    draw.rectangle((0, 0, canvas_w - 1, accent_h - 1), fill=(61, 214, 255))

    # Use the real configured NEXUS logo. The logo lives inside a compact
    # header and never covers the trading chart.
    logo_top = accent_h + 6
    logo_bottom = accent_h + brand_h - 6
    _paste_logo(canvas, (pad, logo_top, pad + 96, logo_bottom))

    # Subtle separator below the brand strip.
    draw.line(
        (pad, accent_h + brand_h - 1, canvas_w - pad - 1, accent_h + brand_h - 1),
        fill=(26, 92, 176),
        width=1,
    )

    chart_x = pad
    chart_y = pad + accent_h + brand_h
    canvas.paste(chart, (chart_x, chart_y))

    draw.rectangle(
        (chart_x - 2, chart_y - 2, chart_x + chart.width + 1, chart_y + chart.height + 1),
        outline=(26, 92, 176),
        width=2,
    )

    if not has_chart:
        _text(draw, (132, 22), "NEXUS", 24, bold=True, fill=(61, 214, 255))
        _text(draw, (132, 48), "CHART UNAVAILABLE", 14, bold=True, fill=(165, 179, 195))

    out = BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()
'''

    card, n = frame_pattern.subn(lambda _m: new_frame.rstrip(), card, count=1)
    if n != 1:
        raise RuntimeError(f"STOP: build_chart_frame replacement count={n}")

# ------------------------------------------------------------------
# 2) Public signal code mapping. Internal DB identity stays NX-27 etc.
# Only user-visible publication code gets a continuous sequence.
# ------------------------------------------------------------------
if API_MARKER not in api:
    publisher_anchor = "async def _publish_mt5_admin_signal_async(row, chart_base64: str | None = None, *, allow_without_chart: bool = False) -> dict:"
    idx = api.find(publisher_anchor)
    if idx < 0:
        raise RuntimeError("STOP: publisher anchor not found")

    helpers = r'''# NEXUS_SIGNAL_PUBLIC_CODE_V1
def _ensure_public_signal_code_schema() -> None:
    with db.conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_public_codes (
                signal_id INTEGER PRIMARY KEY,
                public_no INTEGER NOT NULL UNIQUE,
                public_code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY(signal_id) REFERENCES signals(id) ON DELETE CASCADE
            )
            """
        )


def _public_signal_code(signal_id: int) -> str | None:
    _ensure_public_signal_code_schema()
    with db.conn() as con:
        row = con.execute(
            "SELECT public_code FROM signal_public_codes WHERE signal_id=?",
            (int(signal_id),),
        ).fetchone()
    return str(row[0]) if row and row[0] else None


def _assign_public_signal_code(signal_id: int) -> str:
    """Assign one durable user-visible code without changing internal signal id/code."""
    _ensure_public_signal_code_schema()
    sid = int(signal_id)

    with db.conn() as con:
        con.execute("BEGIN IMMEDIATE")

        existing = con.execute(
            "SELECT public_code FROM signal_public_codes WHERE signal_id=?",
            (sid,),
        ).fetchone()
        if existing:
            return str(existing[0])

        mapped_max = con.execute(
            "SELECT MAX(public_no) FROM signal_public_codes"
        ).fetchone()[0]

        if mapped_max is None:
            # First migration seed: preserve the last number users actually saw
            # before this signal. Rejected/DRAFT/FAILED records are excluded.
            seed = con.execute(
                """
                SELECT MAX(CAST(REPLACE(UPPER(code),'NX-','') AS INTEGER))
                FROM signals
                WHERE id < ?
                  AND (free_message_id IS NOT NULL OR vip_message_id IS NOT NULL)
                  AND UPPER(code) LIKE 'NX-%'
                """,
                (sid,),
            ).fetchone()[0]
            next_no = int(seed or 0) + 1
        else:
            next_no = int(mapped_max) + 1

        public_code = f"NX-{next_no:02d}"
        con.execute(
            "INSERT INTO signal_public_codes(signal_id,public_no,public_code,created_at) VALUES(?,?,?,?)",
            (sid, next_no, public_code, db.now_iso()),
        )
        return public_code


def _build_signal_caption(row, exec_status: str, public_code: str | None = None) -> str:
    # ASCII-only Python source: all UI symbols are Unicode escapes so Windows
    # PowerShell cannot corrupt them into question marks during deployment.
    code = public_code or _public_signal_code(int(row["id"])) or str(row["code"])
    targets = db.get_signal_targets(int(row["id"]))
    target_map = {int(t["target_no"]): float(t["price"]) for t in targets}
    tp_lines = "\n".join(
        f"\U0001F3AF TP{n}: <code>{target_map[n]:g}</code>"
        for n in sorted(target_map)
    ) or "\U0001F3AF TP: --"

    order_type = str(row["order_type"] or "MARKET").upper()
    direction = str(row["direction"] or "").upper()
    direction_icon = "\U0001F535" if direction in {"BUY", "LONG"} else "\U0001F534"
    status_label = "PENDING" if str(exec_status).upper() == "PENDING" else "ACTIVE"
    status_icon = "\U0001F7E0" if status_label == "PENDING" else "\U0001F7E2"
    trailing_label = str(row["trailing_code"] or "OFF")

    return (
        "<b>\u26A1 NEXUS SIGNAL</b>\n"
        f"<code>{code}</code>  \u2022  <b>{order_type}</b>\n\n"
        f"{direction_icon} <b>{str(row['symbol']).upper()} \u00B7 {direction}</b>\n"
        f"\u23F1 <b>{str(row['timeframe'] or 'M5').upper()}</b>\n\n"
        f"\U0001F4CD Entry  <code>{float(row['entry_price']):g}</code>\n"
        f"\U0001F6D1 SL     <code>{float(row['stop_loss']):g}</code>\n"
        f"{tp_lines}\n\n"
        f"\U0001F4CA Risk: <b>{float(row['risk_percent']):g}%</b>\n"
        f"\u2699 Trailing: <b>{trailing_label}</b>\n"
        f"{status_icon} Status: <b>{status_label}</b>"
    )


'''
    api = api[:idx] + helpers + api[idx:]

# Replace only the corrupted Visual-V2 caption block.
caption_pattern = re.compile(
    r'''    # NEXUS_VISUAL_V2_20260911\r?\n    direction = .*?\r?\n    # Preserve already-published destinations''',
    re.S,
)

if CAPTION_MARKER not in api:
    new_caption = r'''    # NEXUS_SIGNAL_CAPTION_V3_20260911
    public_code = _assign_public_signal_code(int(row["id"]))
    caption = _build_signal_caption(row, exec_status, public_code)

    # Preserve already-published destinations'''
    api, n = caption_pattern.subn(lambda _m: new_caption, api, count=1)
    if n != 1:
        raise RuntimeError(f"STOP: caption replacement count={n}")

# Fail closed on known corruption in the active signal caption source.
caption_pos = api.find(CAPTION_MARKER)
if caption_pos < 0:
    raise RuntimeError("STOP: caption V3 marker missing")
caption_window = api[caption_pos:caption_pos + 1200]
if "???" in caption_window:
    raise RuntimeError("STOP: question-mark corruption remains in caption V3 window")

for required in (
    "NEXUS_SIGNAL_PUBLIC_CODE_V1",
    "NEXUS_SIGNAL_CAPTION_V3_20260911",
    "_assign_public_signal_code",
    "_build_signal_caption",
):
    if required not in api:
        raise RuntimeError(f"STOP: missing API marker {required}")

for required in (
    "NEXUS_VISUAL_V3_LOGO_20260911",
    "_paste_logo(canvas",
):
    if required not in card:
        raise RuntimeError(f"STOP: missing card marker {required}")

ast.parse(api)
ast.parse(card)
api_path.write_text(api, encoding="utf-8", newline="\n")
card_path.write_text(card, encoding="utf-8", newline="\n")

print("PATCH STATUS       : APPLIED")
print("PUBLIC CODE        : ENABLED")
print("CAPTION UTF8 SAFE  : ENABLED")
print("REAL LOGO          : ENABLED")
print("RATE LIMIT FIX     : PRESERVED")
'@

try {
    Push-Location $Root
    try {
        $Patch | & $Python -
        if ($LASTEXITCODE -ne 0) {
            throw "patch failed with exit code $LASTEXITCODE"
        }

        Write-Host "`n===== COMPILE CHECK =====" -ForegroundColor Yellow
        & $Python -m py_compile $Api $Card
        if ($LASTEXITCODE -ne 0) {
            throw "py_compile failed with exit code $LASTEXITCODE"
        }
        Write-Host 'PY_COMPILE : PASS' -ForegroundColor Green

        Write-Host "`n===== RENDER SMOKE TEST =====" -ForegroundColor Yellow
        $Smoke = @'
from io import BytesIO
from pathlib import Path
from PIL import Image
from app.signals.card_generator import build_chart_frame, LOGO_PATH

if not Path(LOGO_PATH).exists():
    raise RuntimeError(f"logo missing: {LOGO_PATH}")

src = Image.new("RGB", (1280, 720), (18, 24, 32))
b = BytesIO(); src.save(b, format="PNG")
out = build_chart_frame(b.getvalue())
img = Image.open(BytesIO(out))

if img.width != 1308:
    raise RuntimeError(f"unexpected width={img.width}")
if img.height < 800 or img.height > 850:
    raise RuntimeError(f"unexpected height={img.height}")
if len(out) < 1500:
    raise RuntimeError("render output unexpectedly small")

print("RENDER_SIZE :", f"{img.width}x{img.height}")
print("LOGO_PATH   :", LOGO_PATH)
print("LOGO_EXISTS :", Path(LOGO_PATH).exists())
print("RENDER      : PASS")
'@
        $Smoke | & $Python -
        if ($LASTEXITCODE -ne 0) {
            throw "render smoke test failed with exit code $LASTEXITCODE"
        }

        Write-Host "`n===== RESTART API ONLY =====" -ForegroundColor Yellow
        Restart-Service $Svc

        $Deadline = (Get-Date).AddSeconds(45)
        $Healthy = $false
        $LastHealthError = ''
        while ((Get-Date) -lt $Deadline) {
            Start-Sleep -Seconds 2
            try {
                $Response = Invoke-WebRequest `
                    -Uri 'http://127.0.0.1:8080/api/v1/autotrade/health' `
                    -UseBasicParsing `
                    -TimeoutSec 5
                if ($Response.StatusCode -eq 200) {
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

        Write-Host "`n===== PUBLIC CODE MIGRATION / NX-27 =====" -ForegroundColor Yellow
        $Migrate = @'
from app import db
from app.autotrade.api import _assign_public_signal_code, _build_signal_caption

row = db.get_signal(27)
if not row:
    raise RuntimeError("NX-27 signal row not found")
if str(row["code"]).upper() != "NX-27":
    raise RuntimeError(f"signal 27 code mismatch: {row['code']}")
if not (row["free_message_id"] or row["vip_message_id"]):
    raise RuntimeError("NX-27 is not published; refusing public-code migration")

public_code = _assign_public_signal_code(27)
if public_code != "NX-22":
    raise RuntimeError(f"expected NX-22 for signal 27, got {public_code}")

print("INTERNAL CODE :", row["code"])
print("PUBLIC CODE   :", public_code)
print("MAPPING       : PASS")
'@
        $Migrate | & $Python -
        if ($LASTEXITCODE -ne 0) {
            throw "public-code migration failed with exit code $LASTEXITCODE"
        }

        Write-Host "`n===== EDIT NX-27 EXISTING TELEGRAM CAPTIONS =====" -ForegroundColor Yellow
        $EditCaption = @'
import asyncio
from aiogram import Bot
from aiogram.enums import ParseMode
from app import db
from app.config import settings
from app.autotrade.api import _public_signal_code, _build_signal_caption

async def main():
    row = db.get_signal(27)
    code = _public_signal_code(27)
    if not row or code != "NX-22":
        raise RuntimeError("NX-27 public-code mapping is not ready")

    receipt = db.mt5_signal_live_state(27) or {}
    exec_status = str(receipt.get("receipt_status") or "EXECUTED").upper()
    caption = _build_signal_caption(row, exec_status, code)

    results = []
    async with Bot(settings.bot_token) as bot:
        if row["free_message_id"]:
            try:
                await bot.edit_message_caption(
                    chat_id=settings.free_channel_target,
                    message_id=int(row["free_message_id"]),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
                results.append("FREE:PASS")
            except Exception as exc:
                results.append(f"FREE:WARN:{exc}")

        if row["vip_message_id"]:
            try:
                await bot.edit_message_caption(
                    chat_id=settings.vip_channel_id,
                    message_id=int(row["vip_message_id"]),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
                results.append("VIP:PASS")
            except Exception as exc:
                results.append(f"VIP:WARN:{exc}")

    for item in results:
        print(item)

asyncio.run(main())
'@
        $EditCaption | & $Python -
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'CAPTION EDIT : WARNING (source fix remains valid)' -ForegroundColor Yellow
        }

        Write-Host "`n===== FINAL VERIFY =====" -ForegroundColor Yellow
        $Verify = @'
from pathlib import Path
import inspect
from app import db
from app.signals import card_generator
from app.autotrade import api

api_text = Path(api.__file__).read_text(encoding="utf-8-sig")
card_text = Path(card_generator.__file__).read_text(encoding="utf-8-sig")

checks = {
    "PUBLIC_CODE_MARKER": "NEXUS_SIGNAL_PUBLIC_CODE_V1" in api_text,
    "CAPTION_V3_MARKER": "NEXUS_SIGNAL_CAPTION_V3_20260911" in api_text,
    "LOGO_V3_MARKER": "NEXUS_VISUAL_V3_LOGO_20260911" in card_text,
    "RATE_FIX_MARKER": "NEXUS_CHART_RATE_BUCKETS_V1" in api_text,
    "LOGO_CALL": "_paste_logo(canvas" in inspect.getsource(card_generator.build_chart_frame),
    "PUBLIC_NX27_IS_NX22": api._public_signal_code(27) == "NX-22",
}

for name, ok in checks.items():
    print(f"{name:22}: {'PASS' if ok else 'FAIL'}")
    if not ok:
        raise RuntimeError(name)

print("FINAL VERIFY : PASS")
'@
        $Verify | & $Python -
        if ($LASTEXITCODE -ne 0) {
            throw "final verification failed with exit code $LASTEXITCODE"
        }

        Write-Host "`n=================================================" -ForegroundColor Green
        Write-Host 'NEXUS SIGNAL IDENTITY + VISUAL V3 : PASS' -ForegroundColor Green
        Write-Host '=================================================' -ForegroundColor Green
        Write-Host 'Internal NX-27     : PRESERVED'
        Write-Host 'Public NX-27 label : NX-22'
        Write-Host 'Future public seq  : NX-23, NX-24, ...'
        Write-Host 'Caption ???        : FIXED FOR NEW/EDITED CAPTIONS'
        Write-Host 'Main NEXUS logo    : ENABLED FOR NEW IMAGES'
        Write-Host 'Legacy side panel  : REMAINS REMOVED'
        Write-Host 'Rate-limit fix     : PRESERVED'
        Write-Host 'AutoTrade EA       : UNCHANGED'
        Write-Host 'ChartAgent EX5     : UNCHANGED'
        Write-Host 'Trailing           : UNCHANGED'
        Write-Host "Backup             : $Backup"
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Host "`nHOTFIX FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Rolling back Python source files...' -ForegroundColor Yellow

    Copy-Item (Join-Path $Backup 'api.py') $Api -Force
    Copy-Item (Join-Path $Backup 'card_generator.py') $Card -Force

    try {
        Restart-Service $Svc
        Start-Sleep -Seconds 3
    }
    catch {
        Write-Host "Rollback restart warning: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    Write-Host "DB backup retained at: $DbBackup" -ForegroundColor Yellow
    throw
}
