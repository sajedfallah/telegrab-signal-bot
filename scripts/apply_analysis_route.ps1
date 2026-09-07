$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

$envPath = Join-Path (Get-Location) '.env'
if (-not (Test-Path $envPath)) { throw ".env not found: $envPath" }

$required = [ordered]@{
  'FREE_SIGNAL_CHAT_ID'       = '-1003982028478'
  'FREE_SIGNAL_TOPIC_ID'      = '6'
  'ANALYSIS_CENTER_ENABLED'   = 'true'
  'ANALYSIS_TARGET_CHAT_ID'   = '-1003982028478'
  'ANALYSIS_TARGET_THREAD_ID' = '6'
}

$lines = [System.Collections.Generic.List[string]]::new()
Get-Content $envPath -Encoding UTF8 | ForEach-Object { [void]$lines.Add($_) }

foreach ($key in $required.Keys) {
  $value = $required[$key]
  $pattern = '^\s*' + [regex]::Escape($key) + '\s*='
  $matched = $false
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match $pattern) {
      $lines[$i] = "$key=$value"
      $matched = $true
    }
  }
  if (-not $matched) { [void]$lines.Add("$key=$value") }
}

Copy-Item $envPath "$envPath.bak.$(Get-Date -Format yyyyMMdd-HHmmss)"
$lines | Set-Content $envPath -Encoding UTF8

Write-Host 'Updated Telegram routes:'
foreach ($key in $required.Keys) { Write-Host "  $key=$($required[$key])" }

if (Test-Path '.\nexus.cmd') {
  & .\nexus.cmd restart
  & .\nexus.cmd status
} else {
  Write-Warning 'nexus.cmd not found; restart NEXUS-Telegram-Bot manually.'
}
