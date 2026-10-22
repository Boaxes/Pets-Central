# Creates the Pets Central roles and database in the local Postgres, using the values in .env.
# psql asks for the password of the "postgres" superuser you chose when installing Postgres.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup_local_db.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$envValues = @{}
Get-Content (Join-Path $root '.env') | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $envValues[$Matches[1]] = $Matches[2].Trim() }
}

foreach ($name in 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'ASSISTANT_DB_USER', 'ASSISTANT_DB_PASSWORD') {
    if (-not $envValues[$name]) { throw "$name is missing from .env" }
}

$psqlHost = if ($envValues['POSTGRES_HOST']) { $envValues['POSTGRES_HOST'] } else { 'localhost' }
$psqlPort = if ($envValues['POSTGRES_PORT']) { $envValues['POSTGRES_PORT'] } else { '5432' }

& psql -U postgres -h $psqlHost -p $psqlPort -d postgres -v ON_ERROR_STOP=1 `
    -v "app_user=$($envValues['POSTGRES_USER'])" `
    -v "app_password=$($envValues['POSTGRES_PASSWORD'])" `
    -v "app_db=$($envValues['POSTGRES_DB'])" `
    -v "assistant_user=$($envValues['ASSISTANT_DB_USER'])" `
    -v "assistant_password=$($envValues['ASSISTANT_DB_PASSWORD'])" `
    -f (Join-Path $PSScriptRoot 'setup_local_db.sql')

if ($LASTEXITCODE -ne 0) { throw "psql failed with exit code $LASTEXITCODE" }
Write-Host "Roles '$($envValues['POSTGRES_USER'])' and '$($envValues['ASSISTANT_DB_USER'])' and database '$($envValues['POSTGRES_DB'])' are ready."
