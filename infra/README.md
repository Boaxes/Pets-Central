# Infrastructure

Everything Pets Central runs on, as Terraform. Each folder is a stack with its own state, kept in Azure Storage
(settings in `backend.hcl`), because each has its own lifetime:

| Stack | Applied by | Lifetime | What it holds |
|---|---|---|---|
| `bootstrap` | The owner, from their machine | Kept | Terraform's state storage, the identity GitHub Actions signs in as (OIDC, trusted by the repository's permanent ids), the resource groups CI may change, the container registry production and the demo share, the $10 monthly budget alert |
| `snowflake` | GitHub Actions on merge; CI plans it on every pull request | Destroyed after the analytics screenshots | Databases, warehouse, roles, service users, resource monitor |
| `vendor` | GitHub Actions on merge (first applied by the owner) | Kept for the demo | The loyalty vendor's Rewards API: a Flex Consumption Function App and the private blob holding its data |
| `azure` | GitHub Actions on merge, until it was destroyed | Destroyed after the screenshots, with `destroy.yml` | Production: Container Apps (the store app, Dagster, the `manage` job), PostgreSQL on a private network, Key Vault |

## Setting it up from nothing

1. **Snowflake:** run `snowflake/bootstrap.sql` once in a Snowsight worksheet, as ACCOUNTADMIN, with the public key
   of `pets_terraform` filled in. It creates the user Terraform signs in as.
2. **Azure:** `az login`, then apply `bootstrap` with local state, and move its state into the account it created:

   ```powershell
   cd infra/bootstrap
   terraform init
   terraform apply
   # Add `backend "azurerm" {}` to main.tf (already there in this repository), then:
   terraform init -migrate-state "-backend-config=../backend.hcl" "-backend-config=key=bootstrap.tfstate"
   ```

3. **Every other stack:**

   ```powershell
   cd infra/snowflake
   terraform init "-backend-config=../backend.hcl" "-backend-config=key=snowflake.tfstate"
   terraform plan
   ```

4. **GitHub:** the repository's variables hold the IDs CI needs (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
   `AZURE_SUBSCRIPTION_ID`, and the Snowflake organization, account and analyst user). Its secrets hold the private
   keys, entered by the owner: `SNOWFLAKE_DBT_PRIVATE_KEY` and `SNOWFLAKE_TERRAFORM_PRIVATE_KEY`.

Services the stacks use are registered once, by `bootstrap`'s provider settings, outside Terraform's state:
registration is subscription-wide, and removing it would affect everything else in the subscription.

## Destroying a stack

`.github/workflows/destroy.yml` is run by hand from the Actions tab, naming the stack (`azure` or `snowflake`) and
typing it again to confirm. Take the stack out of `deploy.yml` and `ci.yml` first, or the next merge re-creates it.

## The first production deploy (before production was destroyed)

Merging to `main` ran `.github/workflows/deploy.yml`: images, `terraform apply` for `snowflake`, `vendor` and
`azure`, the Rewards API's code, and `migrate`. The first time, a few one-time steps followed.

1. **The owner sets the outside secrets** in Key Vault (Terraform created them as placeholders and never changes
   their values). The Snowflake keys come from files; the Anthropic key is read from the local `.env`. Policy
   search's embeddings need no key: the app signs in to Azure OpenAI with its managed identity.

   ```powershell
   $vault = 'kv-pets-022e5b87'
   az keyvault secret set --vault-name $vault --name snowflake-loader-key --file "$HOME\.snowflake\keys\pets_loader.p8"
   az keyvault secret set --vault-name $vault --name snowflake-dbt-key --file "$HOME\.snowflake\keys\pets_dbt.p8"
   $value = (Select-String -Path .env -Pattern '^ANTHROPIC_API_KEY=(.+)$').Matches[0].Groups[1].Value
   az keyvault secret set --vault-name $vault --name anthropic-api-key --value $value --output none
   ```

2. **The `manage` job prepares the database.** The database is private, so these run inside Azure. Each command
   waits for the last (the data generation takes the longest):

   ```powershell
   scripts/run_manage_job.ps1 -Command python,manage.py,create_assistant_login
   scripts/run_manage_job.ps1 -Command sh,-c,"python manage.py load_policies && python manage.py index_policies"
   scripts/run_manage_job.ps1 -Command sh,-c,"python manage.py generate_data --size full --seed 42 && python manage.py publish_loyalty_data --size full"
   ```

3. **Dagster picks up the Snowflake keys** on its next revision:
   `az containerapp revision restart -n ca-pets-dagster -g rg-pets-central-prod --revision <latest>`.
