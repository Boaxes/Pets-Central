# Asks for a secret and saves it in .env, replacing any earlier value. Nothing is echoed or logged.
#
#   powershell -ExecutionPolicy Bypass -File scripts\set_env_secret.ps1 ANTHROPIC_API_KEY

param([Parameter(Mandatory = $true)][string]$Name)

$ErrorActionPreference = 'Stop'
$envFile = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'

$secure = Read-Host "Paste $Name (input is hidden)" -AsSecureString
$value = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)).Trim()
if (-not $value) { throw "Nothing was entered; .env is unchanged." }

$lines = @(Get-Content $envFile | Where-Object { $_ -notmatch "^\s*#?\s*$Name\s*=" })
$lines += "$Name=$value"
[IO.File]::WriteAllLines($envFile, $lines)
Write-Host "$Name saved in .env."
