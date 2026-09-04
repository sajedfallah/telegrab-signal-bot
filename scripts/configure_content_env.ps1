param(
    [string]$DailyTime = "12:00",
    [switch]$PublishDirectly
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$envPath = Join-Path (Get-Location) ".env"
$examplePath = Join-Path (Get-Location) ".env.example"

if (-not (Test-Path $envPath)) {
    if (-not (Test-Path $examplePath)) {
        throw ".env and .env.example were not found."
    }
    Copy-Item $examplePath $envPath
    Write-Host "[NEXUS] Created .env from .env.example"
}

if ($DailyTime -notmatch '^(?:[01]\d|2[0-3]):[0-5]\d$') {
    throw "DailyTime must be HH:mm, for example 12:00"
}

function Set-EnvValue {
    param(
        [Parameter(Mandatory=$true)][string]$Key,
        [Parameter(Mandatory=$true)][string]$Value
    )

    $lines = [System.IO.File]::ReadAllLines($envPath)
    $pattern = '^' + [regex]::Escape($Key) + '='
    $found = $false

    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = "$Key=$Value"
            $found = $true
            break
        }
    }

    if (-not $found) {
        $lines = @($lines) + "$Key=$Value"
    }

    [System.IO.File]::WriteAllLines(
        $envPath,
        $lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}

$secureKey = Read-Host "Paste Gemini API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $geminiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}

if ([string]::IsNullOrWhiteSpace($geminiKey)) {
    throw "Gemini API key cannot be empty."
}

Set-EnvValue "CONTENT_AGENTS_ENABLED" "true"
Set-EnvValue "CONTENT_DAILY_TIME" $DailyTime
Set-EnvValue "CONTENT_CATCHUP_ENABLED" "true"
Set-EnvValue "CONTENT_APPROVAL_MODE" ($(if ($PublishDirectly) { "false" } else { "true" }))
Set-EnvValue "CONTENT_PROTECT_CONTENT" "false"
Set-EnvValue "CONTENT_AI_PROVIDER" "gemini"
Set-EnvValue "CONTENT_AI_API_KEY" $geminiKey
Set-EnvValue "CONTENT_AI_BASE_URL" "https://generativelanguage.googleapis.com/v1beta/openai/"
Set-EnvValue "CONTENT_TEXT_MODEL" "gemini-3.8-flash"
Set-EnvValue "CONTENT_FONT_PATH" "C:\Windows\Fonts\arial.ttf"
Set-EnvValue "CONTENT_FONT_BOLD_PATH" "C:\Windows\Fonts\arialbd.ttf"

$geminiKey = $null
$secureKey = $null

Write-Host "[NEXUS] Agentic content environment configured."
Write-Host "[NEXUS] Daily time: $DailyTime"
Write-Host "[NEXUS] Approval mode: $(-not $PublishDirectly.IsPresent)"
Write-Host "[NEXUS] API key was written only to local .env and was not committed to GitHub."
