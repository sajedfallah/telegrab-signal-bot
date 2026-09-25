param(
    [string]$Root = 'C:\NEXUS_V065_FINAL_TEST'
)

$ErrorActionPreference = 'Stop'

$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Card   = Join-Path $Root 'app\signals\card_generator.py'
$Api    = Join-Path $Root 'app\autotrade\api.py'
$TmpDir = 'C:\NEXUS_TMP'
$BaseScript = Join-Path $TmpDir 'apply_visual_hotfix_v065.base.ps1'
$FixedScript = Join-Path $TmpDir 'apply_visual_hotfix_v065.fixed.ps1'

Write-Host "`n===== NEXUS VISUAL HOTFIX v0.6.5 / FIXED RUNNER =====" -ForegroundColor Cyan

foreach ($Path in @($Python, $Card, $Api)) {
    if (-not (Test-Path $Path)) {
        throw "STOP: required path not found: $Path"
    }
}

# Fail closed: the previous failed attempt must have rolled production back to
# syntactically valid source before another patch attempt is allowed.
Write-Host "`n===== PREFLIGHT CURRENT PRODUCTION =====" -ForegroundColor Yellow
& $Python -m py_compile $Card $Api
if ($LASTEXITCODE -ne 0) {
    throw "STOP: current production Python source is not healthy after prior rollback"
}
Write-Host 'CURRENT SOURCE COMPILE : PASS' -ForegroundColor Green

try {
    $Health = Invoke-WebRequest `
        -Uri 'http://127.0.0.1:8080/api/v1/autotrade/health' `
        -UseBasicParsing `
        -TimeoutSec 5
    if ($Health.StatusCode -ne 200) {
        throw "HTTP $($Health.StatusCode)"
    }
    Write-Host 'CURRENT API HEALTH     : PASS' -ForegroundColor Green
}
catch {
    throw "STOP: API is not healthy before hotfix: $($_.Exception.Message)"
}

New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

# Pin the original deployer so this repair is deterministic. We repair only the
# nested Python replacement quoting bug; production semantics stay unchanged.
$BaseUrl = 'https://raw.githubusercontent.com/sajedfallah/telegrab-signal-bot/8303cf2795befea03f102f53a31c48cf7091e3d6/ops/apply_visual_hotfix_v065.ps1'
Invoke-WebRequest -Uri $BaseUrl -OutFile $BaseScript -UseBasicParsing

$Text = [System.IO.File]::ReadAllText($BaseScript)
$Original = $Text

# The first deployer embedded Python source in a Python triple-quoted replacement
# string. Python interpreted \n before re.sub wrote the replacement, producing
# literal newlines inside quoted source and an unterminated-string SyntaxError.
# Raw replacement text + callable re.sub replacements preserve backslashes.
$Text = $Text.Replace("new_caption = '''", "new_caption = r'''")
$Text = $Text.Replace(
    'card, count = frame_pattern.subn(new_frame.rstrip(), card, count=1)',
    'card, count = frame_pattern.subn(lambda _m: new_frame.rstrip(), card, count=1)'
)
$Text = $Text.Replace(
    'api, count = publish_pattern.subn(new_publish, api, count=1)',
    'api, count = publish_pattern.subn(lambda _m: new_publish, api, count=1)'
)
$Text = $Text.Replace(
    'api, count = caption_pattern.subn(new_caption, api, count=1)',
    'api, count = caption_pattern.subn(lambda _m: new_caption, api, count=1)'
)

if ($Text -eq $Original) {
    throw 'STOP: repair substitutions made no changes'
}

$Required = @(
    "new_caption = r'''",
    'frame_pattern.subn(lambda _m: new_frame.rstrip(), card, count=1)',
    'publish_pattern.subn(lambda _m: new_publish, api, count=1)',
    'caption_pattern.subn(lambda _m: new_caption, api, count=1)'
)
foreach ($Needle in $Required) {
    if (-not $Text.Contains($Needle)) {
        throw "STOP: repaired deployer missing required marker: $Needle"
    }
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($FixedScript, $Text, $Utf8NoBom)

Write-Host "REPAIRED DEPLOYER : $FixedScript"
Write-Host "SHA256            : $((Get-FileHash $FixedScript -Algorithm SHA256).Hash)"
Write-Host 'QUOTE FIX          : PASS' -ForegroundColor Green

# Run the original guarded deploy flow after repairing its quoting. It creates a
# fresh backup, patches only card_generator.py/api.py, compiles, smoke-tests,
# restarts only NEXUS-AutoTrade-API, health-checks, and rolls back on failure.
& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $FixedScript `
    -Root $Root

if ($LASTEXITCODE -ne 0) {
    throw "fixed visual hotfix exited with code $LASTEXITCODE"
}

Write-Host "`nFIXED RUNNER : PASS" -ForegroundColor Green
