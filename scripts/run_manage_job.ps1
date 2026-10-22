# Runs one command in production's `manage` job and waits for it, e.g.
#     scripts/run_manage_job.ps1 -Command python,manage.py,index_policies
# It starts the job through Azure's API with the job's own container (settings and secret references), changing only
# the command, so nothing the job needs is lost. Read its output with scripts/manage_job_logs.ps1.
param([Parameter(Mandatory)][string[]]$Command, [int]$TimeoutMinutes = 120)
$ErrorActionPreference = 'Stop'
$env:Path = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;" + $env:Path
$job = "/subscriptions/022e5b87-f788-4401-a79a-24e86976ea0b/resourceGroups/rg-pets-central-prod/providers/Microsoft.App/jobs/caj-pets-manage"
$api = 'api-version=2024-03-01'

$container = (az rest --method get --url "https://management.azure.com$job`?$api" --only-show-errors | ConvertFrom-Json).properties.template.containers[0]
$container.command = $Command
if ($container.PSObject.Properties['args']) { $container.args = @() }
$body = Join-Path $env:TEMP 'manage-start.json'
@{ containers = @($container) } | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 $body

$started = az rest --method post --url "https://management.azure.com$job/start?$api" --body "@$body" --only-show-errors | ConvertFrom-Json
$name = $started.name
"started $name : $($Command -join ' ')"
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
do {
    Start-Sleep -Seconds 20
    $status = (az rest --method get --url "https://management.azure.com$job/executions/$name`?$api" --only-show-errors | ConvertFrom-Json).properties.status
} while ($status -in 'Running', 'Processing', 'Unknown' -and (Get-Date) -lt $deadline)
"finished $name : $status"
