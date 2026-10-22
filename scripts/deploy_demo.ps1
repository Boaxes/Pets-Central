# Deploys the store app's live demo with the Azure CLI: the image built in the shared registry, a user-assigned
# identity, a small Azure OpenAI account for policy search, and a Container App scaled to zero, reading the Neon
# `demo` branch. Run it again to deploy a new image. Needs `az` and the Neon CLI (`npx neonctl`) signed in, and data/neon.env.
#
# The Anthropic key comes from the local .env, the Neon logins from data/neon.env; none is printed.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$group = 'rg-pets-central-demo'
$location = 'centralus'
$registry = 'crpetscentral022e5b87'
$app = 'pets-store-demo'
$openai = 'oai-pets-central-demo'
$neonProject = 'lingering-cell-84930188'

# Success is the exit code: az writes warnings to stderr, which PowerShell 5.1 would otherwise treat as errors.
function Invoke-Az { $ErrorActionPreference = 'Continue'; az @args; if ($LASTEXITCODE) { throw "az $($args[0..1] -join ' ') failed" } }
function Exists { $ErrorActionPreference = 'Continue'; az @args -o none 2>$null; -not $LASTEXITCODE }

$anthropicKey = ((Get-Content (Join-Path $root '.env')) -match '^ANTHROPIC_API_KEY=' | Select-Object -First 1) -replace '^ANTHROPIC_API_KEY=', ''
if (-not $anthropicKey) { throw 'ANTHROPIC_API_KEY is missing from .env' }
$neon = @{}
foreach ($line in Get-Content (Join-Path $root 'data\neon.env')) {
    if ($line -match '^\s*([A-Z_]+)=(.*)$') { $neon[$matches[1]] = $matches[2] }
}
$url = (npx -y neonctl@8.8.0 connection-string demo --project-id $neonProject --database-name pets_central --role-name pets_app |
        Where-Object { $_ -match '^postgres' } | Select-Object -First 1)
$demoHost = ([uri]$url).Host

$tag = git -C $root rev-parse --short HEAD
if (-not (Exists acr repository show -n $registry --image "pets-store:demo-$tag")) {
    Write-Host 'Building the image in the registry...'
    # --no-wait, then waiting on the run: az acr build's log stream is unreliable on Windows.
    # The committed files only: quick to upload, and nothing untracked (such as a local secrets file) goes along.
    $context = Join-Path ([IO.Path]::GetTempPath()) "pets-store-$tag"
    if (Test-Path $context) { Remove-Item $context -Recurse -Force -Confirm:$false }
    New-Item -ItemType Directory $context | Out-Null
    git -C $root archive -o "$context.tar" HEAD
    tar -xf "$context.tar" -C $context
    Invoke-Az acr build -r $registry -t "pets-store:demo-$tag" --no-wait $context | Out-Null
    $run = Invoke-Az acr task list-runs -r $registry --top 1 --query '[0].runId' -o tsv
    do { Start-Sleep 15; $status = Invoke-Az acr task show-run -r $registry --run-id $run --query status -o tsv }
    while ($status -in 'Queued', 'Started', 'Running')
    if ($status -ne 'Succeeded') { throw "The image build $run ended $status" }
}
Write-Host 'Identity and embedding model...'
$identity = Invoke-Az identity create -g $group -n id-pets-store-demo -l $location | ConvertFrom-Json
$registryId = Invoke-Az acr show -n $registry --query id -o tsv
Invoke-Az role assignment create --assignee-object-id $identity.principalId --assignee-principal-type ServicePrincipal `
    --role AcrPull --scope $registryId | Out-Null
if (-not (Exists cognitiveservices account show -g $group -n $openai)) {
    Invoke-Az cognitiveservices account create -g $group -n $openai -l $location --kind OpenAI --sku S0 `
    --custom-domain $openai --yes | Out-Null
}
$account = Invoke-Az cognitiveservices account show -g $group -n $openai | ConvertFrom-Json
if (-not (Exists cognitiveservices account deployment show -g $group -n $openai --deployment-name text-embedding-3-small)) {
    Invoke-Az cognitiveservices account deployment create -g $group -n $openai --deployment-name text-embedding-3-small `
        --model-name text-embedding-3-small --model-version 1 --model-format OpenAI --sku-name GlobalStandard `
        --sku-capacity 50 | Out-Null
}
# The app calls the model; so does whoever runs this, to build the policy index on the seed branch.
$me = Invoke-Az ad signed-in-user show --query id -o tsv
foreach ($principal in @(@($identity.principalId, 'ServicePrincipal'), @($me, 'User'))) {
    Invoke-Az role assignment create --assignee-object-id $principal[0] --assignee-principal-type $principal[1] `
        --role 'Cognitive Services OpenAI User' --scope $account.id | Out-Null
}

Write-Host 'Container App...'
if (-not (Exists containerapp env show -g $group -n cae-pets-central-demo)) {
    Invoke-Az containerapp env create -g $group -n cae-pets-central-demo -l $location --logs-destination none | Out-Null
}
$domain = Invoke-Az containerapp env show -g $group -n cae-pets-central-demo --query properties.defaultDomain -o tsv
$fqdn = "$app.$domain"
$random = { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object { [char]$_ }) }
$secrets = @("anthropic-api-key=$anthropicKey", "postgres-password=$($neon.POSTGRES_PASSWORD)", "assistant-db-password=$($neon.ASSISTANT_DB_PASSWORD)",
             "django-secret-key=$(& $random)", "demo-password=$(& $random)")
$envVars = @('ANTHROPIC_API_KEY=secretref:anthropic-api-key', "DJANGO_SECRET_KEY=secretref:django-secret-key", "DJANGO_ALLOWED_HOSTS=$fqdn", 'DJANGO_HTTPS=True',
             'DJANGO_DEMO_SIGN_IN=True', 'DJANGO_DEMO_PASSWORD=secretref:demo-password',
             'POSTGRES_DB=pets_central', 'POSTGRES_USER=pets_app', 'POSTGRES_PASSWORD=secretref:postgres-password',
             "POSTGRES_HOST=$demoHost", 'POSTGRES_SSLMODE=require',
             "ASSISTANT_DB_USER=$($neon.ASSISTANT_DB_USER)", 'ASSISTANT_DB_PASSWORD=secretref:assistant-db-password',
             'ASSISTANT_SITE_DAILY_LIMIT=100', "AZURE_OPENAI_ENDPOINT=$($account.properties.endpoint)",
             "AZURE_CLIENT_ID=$($identity.clientId)")
$image = "$registry.azurecr.io/pets-store:demo-$tag"
if (Exists containerapp show -g $group -n $app) {
    Invoke-Az containerapp secret set -g $group -n $app --secrets @secrets | Out-Null
    Invoke-Az containerapp update -g $group -n $app --image $image --set-env-vars @envVars | Out-Null
} else {
    Invoke-Az containerapp create -g $group -n $app --environment cae-pets-central-demo --image $image `
        --user-assigned $identity.id --registry-server "$registry.azurecr.io" --registry-identity $identity.id `
        --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1Gi `
        --secrets @secrets --env-vars @envVars | Out-Null
}
Write-Host "The demo: https://$fqdn/"
