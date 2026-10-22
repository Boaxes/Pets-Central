# Prints a `manage` job execution's output from the logs workspace (a minute or two behind), e.g.
#     scripts/manage_job_logs.ps1 -Execution caj-pets-manage-abc1234
param([Parameter(Mandatory)][string]$Execution, [int]$Last = 30)
$env:Path = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;" + $env:Path
$workspace = az resource show -g rg-pets-central-prod -n log-pets-central --resource-type Microsoft.OperationalInsights/workspaces --query properties.customerId -o tsv --only-show-errors
$query = "ContainerAppConsoleLogs_CL | where ContainerGroupName_s startswith '$Execution' | project TimeGenerated, Log_s | order by TimeGenerated asc"
$body = Join-Path $env:TEMP 'la-query.json'
@{ query = $query; timespan = 'P1D' } | ConvertTo-Json | Set-Content -Encoding utf8 $body
$result = az rest --method post --url "https://api.loganalytics.io/v1/workspaces/$workspace/query" --resource https://api.loganalytics.io --body "@$body" --only-show-errors | ConvertFrom-Json
$rows = $result.tables[0].rows
"$($rows.Count) lines"
$rows | Select-Object -Last $Last | ForEach-Object { $_[1] }
