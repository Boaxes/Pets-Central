# Runs a manage.py command against the demo's Neon seed branch, with the settings in data/neon.env (git-ignored)
# taking the place of the local database's. Nothing is printed from that file.
#
#   powershell -ExecutionPolicy Bypass -File scripts\neon_manage.ps1 migrate
#   powershell -ExecutionPolicy Bypass -File scripts\neon_manage.ps1 generate_data --size small

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
foreach ($line in Get-Content (Join-Path $root 'data\neon.env')) {
    if ($line -match '^\s*([A-Z_]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
Push-Location $root
try { uv run python manage.py @args; if ($LASTEXITCODE) { exit $LASTEXITCODE } } finally { Pop-Location }
