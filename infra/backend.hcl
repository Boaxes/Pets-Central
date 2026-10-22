# Where every stack keeps its Terraform state: the storage account infra/bootstrap creates. Each stack adds its own
# key, e.g. terraform init -backend-config=../backend.hcl -backend-config=key=snowflake.tfstate
resource_group_name  = "rg-pets-central-shared"
storage_account_name = "stpetstf022e5b87"
container_name       = "tfstate"
use_azuread_auth     = true
