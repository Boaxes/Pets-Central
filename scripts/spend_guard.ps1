# Checks the Azure subscription's spend this month and, over the limit, stops everything that bills by the hour.
#     scripts/spend_guard.ps1               # check, and stop if over $20
#     scripts/spend_guard.ps1 -DryRun       # check, and only say what it would stop
#
# Azure's cost data runs 8 to 24 hours behind, so this sees spend up to about a day ago.
# "Stop" is reversible and keeps every byte of data: running job executions stop, the apps' revisions are
# deactivated, the Postgres server stops (Azure restarts a stopped server after 7 days), and the Rewards API stops.
param([decimal]$Limit = 20, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
$env:Path = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;" + $env:Path
$subscription = '022e5b87-f788-4401-a79a-24e86976ea0b'
$prod = 'rg-pets-central-prod'

$body = Join-Path $env:TEMP 'spend-query.json'
@{
    type = 'ActualCost'; timeframe = 'MonthToDate'
    dataset = @{ granularity = 'None'; aggregation = @{ total = @{ name = 'Cost'; function = 'Sum' } } }
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $body
$result = az rest --method post --body "@$body" --only-show-errors `
    --url "https://management.azure.com/subscriptions/$subscription/providers/Microsoft.CostManagement/query?api-version=2023-11-01" |
    ConvertFrom-Json
# A failed query (Azure rate-limits Cost Management) must not read as $0.
if ($LASTEXITCODE -ne 0 -or -not $result) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm') cost query failed; spend unknown."; exit 1 }
$row = $result.properties.rows | Select-Object -First 1
$spend = if ($row) { [decimal]$row[0] } else { [decimal]0 }
$currency = if ($row) { $row[1] } else { 'USD' }
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
"$stamp spend this month: {0:N2} {1} (limit {2:N2})" -f $spend, $currency, $Limit

if ($spend -le $Limit) { 'Under the limit; nothing stopped.'; exit 0 }

# Deactivating an app's revision stops it (min replicas can't go below a maximum of 1). Jobs stop before the database.
function Stop-App($name) {
    $revision = az containerapp revision list -n $name -g $prod --query "[?properties.active].name | [0]" -o tsv --only-show-errors
    if ($revision) { az containerapp revision deactivate -n $name -g $prod --revision $revision --only-show-errors -o none }
}
$steps = @(
    @{ what = 'Stop running manage job executions'; run = {
        $job = "/subscriptions/$subscription/resourceGroups/$prod/providers/Microsoft.App/jobs/caj-pets-manage"
        (az rest --method get --url "https://management.azure.com$job/executions?api-version=2024-03-01" --only-show-errors | ConvertFrom-Json).value |
            Where-Object { $_.properties.status -eq 'Running' } |
            ForEach-Object { az rest --method post --url "https://management.azure.com$job/executions/$($_.name)/stop?api-version=2024-03-01" --only-show-errors -o none } } },
    @{ what = 'Stop Dagster'; run = { Stop-App 'ca-pets-dagster' } },
    @{ what = 'Stop the store app'; run = { Stop-App 'ca-pets-store' } },
    @{ what = 'Stop the Postgres server'; run = { az postgres flexible-server stop -g $prod -n psql-pets-central-022e5b87 --only-show-errors -o none } },
    @{ what = 'Stop the Rewards API'; run = { az functionapp stop -g rg-pets-central-vendor -n func-pets-rewards-022e5b87 --only-show-errors -o none } }
)
"OVER THE LIMIT. $(if ($DryRun) { 'Dry run: would' } else { 'Stopping:' })"
foreach ($step in $steps) {
    if ($DryRun) { "  would: $($step.what)"; continue }
    try { & $step.run; "  done: $($step.what)" } catch { "  FAILED: $($step.what): $_" }
}
exit 2
