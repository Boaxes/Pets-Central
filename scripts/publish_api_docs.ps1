# Publishes the Pawprint Loyalty API's reference to Cloudflare Pages (https://pawprint-loyalty-docs.pages.dev):
# the OpenAPI spec exported from the FastAPI app, shown by Swagger UI with "Try It Out" on and the public demo key
# filled in. The key is read from the Function App's settings, never printed. Needs Wrangler and the Azure CLI signed in.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$site = Join-Path ([IO.Path]::GetTempPath()) 'pawprint-loyalty-docs'
if (Test-Path $site) { Remove-Item $site -Recurse -Force -Confirm:$false }
New-Item -ItemType Directory $site | Out-Null
Copy-Item (Join-Path $root 'loyalty_api\docs_site\index.html') $site
$env:LOYALTY_DEMO_KEY = az functionapp config appsettings list -g rg-pets-central-vendor -n func-pets-rewards-022e5b87 `
    --query "[?name=='LOYALTY_DEMO_KEY'].value | [0]" -o tsv
if (-not $env:LOYALTY_DEMO_KEY) { throw 'The Function App has no LOYALTY_DEMO_KEY; set the secret and deploy first.' }
Push-Location (Join-Path $root 'loyalty_api')
try {
    uv run python -c @"
import json, os, sys
from pathlib import Path
from loyalty.main import create_app
from loyalty.settings import Settings
key = os.environ['LOYALTY_DEMO_KEY']
spec = create_app(Settings(db_path=Path('unused'), api_keys=frozenset(), demo_key=key)).openapi()
spec['info']['description'] += f'\n\n**Demo key:** {key} (already filled in: open an endpoint and choose Try It Out).'
spec['x-demo-key'] = key
spec['servers'] = [{'url': 'https://func-pets-rewards-022e5b87.azurewebsites.net'}]
Path(sys.argv[1]).write_text(json.dumps(spec, indent=2), encoding='utf-8')
"@ (Join-Path $site 'openapi.json')
} finally { Pop-Location; Remove-Item Env:LOYALTY_DEMO_KEY }
& { $ErrorActionPreference = 'Continue'; npx -y wrangler@4.40.0 pages project create pawprint-loyalty-docs --production-branch main 2>&1 | Out-Null }  # fails harmlessly once it exists
npx -y wrangler@4.40.0 pages deploy $site --project-name pawprint-loyalty-docs --branch main --commit-dirty=true
