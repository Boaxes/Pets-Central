# Pets Central in production: the store app, Dagster and the `manage` job on Container Apps, PostgreSQL on a
# private network, and Key Vault for every secret. Applied by GitHub Actions on each merge to main; destroyed after
# the screenshots. Sized to the subscription's free services (Postgres B1MS with 32 GB).

terraform {
  required_version = ">= 1.10"
  backend "azurerm" {} # Settings in ../backend.hcl.
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  # On destroy, the Key Vault and Azure OpenAI account are left soft-deleted (empty, free, cleared by Azure later):
  # purging them needs subscription-wide rights the CI identity doesn't have.
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
    cognitive_account {
      purge_soft_delete_on_destroy = false
    }
  }
  subscription_id                 = var.subscription_id
  storage_use_azuread             = true
  resource_provider_registrations = "none"
}

data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "prod" {
  name = "rg-pets-central-prod"
}

# The kept pieces this stack builds on: the shared registry, and the vendor's Rewards API.
data "terraform_remote_state" "bootstrap" {
  backend = "azurerm"
  config  = merge(local.state, { key = "bootstrap.tfstate" })
}

data "terraform_remote_state" "vendor" {
  backend = "azurerm"
  config  = merge(local.state, { key = "vendor.tfstate" })
}

locals {
  state = {
    resource_group_name  = "rg-pets-central-shared"
    storage_account_name = "stpetstf022e5b87"
    container_name       = "tfstate"
    use_azuread_auth     = true
  }
  suffix = substr(replace(var.subscription_id, "-", ""), 0, 8)
  # Compute runs in var.location: this subscription can't create Postgres B1MS in East US 2. Key Vault and the
  # identities and the logs workspace stay in the resource group's region, where they were made; their region
  # doesn't matter.
  location = var.location
  home     = data.azurerm_resource_group.prod.location
  rg       = data.azurerm_resource_group.prod.name
  registry = data.terraform_remote_state.bootstrap.outputs.registry
  vendor   = data.terraform_remote_state.vendor.outputs
}

# Identities: one for the store app and its `manage` job, one for Dagster ----------------------------------------

resource "azurerm_user_assigned_identity" "app" {
  for_each            = toset(["store", "dagster"])
  name                = "id-pets-${each.key}"
  resource_group_name = local.rg
  location            = local.home
}

resource "azurerm_role_assignment" "pull_images" {
  for_each             = azurerm_user_assigned_identity.app
  scope                = data.terraform_remote_state.bootstrap.outputs.registry_id
  role_definition_name = "AcrPull"
  principal_id         = each.value.principal_id
}

# The `manage` job writes the loyalty data file into the vendor's storage after generating the data.
resource "azurerm_role_assignment" "write_loyalty_file" {
  scope                = local.vendor.data_container_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app["store"].principal_id
}

# Secrets -------------------------------------------------------------------------------------------------------

resource "azurerm_key_vault" "pets" {
  name                       = "kv-pets-${local.suffix}"
  resource_group_name        = local.rg
  location                   = local.home
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
}

resource "azurerm_role_assignment" "read_secrets" {
  for_each             = azurerm_user_assigned_identity.app
  scope                = azurerm_key_vault.pets.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = each.value.principal_id
}

resource "random_password" "generated" {
  for_each = toset(["django-secret-key", "postgres-password", "assistant-db-password", "demo-password"])
  length   = 40
  special  = false
}

# Made here and never typed by anyone.
resource "azurerm_key_vault_secret" "generated" {
  for_each     = random_password.generated
  name         = each.key
  value        = each.value.result
  key_vault_id = azurerm_key_vault.pets.id
}

resource "azurerm_key_vault_secret" "loyalty_api_key" {
  name         = "loyalty-api-key"
  value        = local.vendor.api_key # Issued by the vendor's stack.
  key_vault_id = azurerm_key_vault.pets.id
}

# From outside services: created as placeholders, then the owner sets each value with
# az keyvault secret set (see infra/README.md). Terraform never sees or changes the real value.
resource "azurerm_key_vault_secret" "owner_provided" {
  for_each     = toset(["anthropic-api-key", "snowflake-loader-key", "snowflake-dbt-key"])
  name         = each.key
  value        = "set-by-the-owner"
  key_vault_id = azurerm_key_vault.pets.id
  lifecycle {
    ignore_changes = [value]
  }
}

locals {
  secret_ids = merge(
    { for name, secret in azurerm_key_vault_secret.generated : name => secret.versionless_id },
    { for name, secret in azurerm_key_vault_secret.owner_provided : name => secret.versionless_id },
    { "loyalty-api-key" = azurerm_key_vault_secret.loyalty_api_key.versionless_id },
  )
}

# Policy search's embedding model: Azure OpenAI, keyless. A fraction of a cent for 55 sections and the questions.

resource "azurerm_cognitive_account" "openai" {
  name                  = "oai-pets-${local.suffix}"
  resource_group_name   = local.rg
  location              = local.home
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "oai-pets-${local.suffix}" # Required for Entra ID sign-in.
  local_auth_enabled    = false                      # No API keys at all; only identities with a role.
}

resource "azurerm_cognitive_deployment" "embeddings" {
  name                 = "text-embedding-3-small"
  cognitive_account_id = azurerm_cognitive_account.openai.id
  model {
    format  = "OpenAI"
    name    = "text-embedding-3-small"
    version = "1"
  }
  sku {
    name     = "Standard"
    capacity = 20 # Thousand tokens a minute; indexing all 55 sections uses about 30.
  }
}

resource "azurerm_role_assignment" "use_embeddings" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.app["store"].principal_id
}

# Network: the database has no public endpoint -------------------------------------------------------------------

resource "azurerm_virtual_network" "pets" {
  name                = "vnet-pets-central"
  resource_group_name = local.rg
  location            = local.location
  address_space       = ["10.40.0.0/16"]
}

resource "azurerm_subnet" "apps" {
  name                 = "snet-apps"
  resource_group_name  = local.rg
  virtual_network_name = azurerm_virtual_network.pets.name
  address_prefixes     = ["10.40.0.0/23"]
  delegation {
    name = "container-apps"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "postgres" {
  name                 = "snet-postgres"
  resource_group_name  = local.rg
  virtual_network_name = azurerm_virtual_network.pets.name
  address_prefixes     = ["10.40.2.0/28"]
  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "postgres" {
  name                = "pets-central.private.postgres.database.azure.com"
  resource_group_name = local.rg
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "postgres"
  resource_group_name   = local.rg
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.pets.id
}

# PostgreSQL: the store app's data, the policies with pgvector, and Dagster's run history ------------------------

resource "azurerm_postgresql_flexible_server" "pets" {
  name                          = "psql-pets-central-${local.suffix}"
  resource_group_name           = local.rg
  location                      = local.location
  version                       = "17"
  sku_name                      = "B_Standard_B1ms" # In the free services: 750 hours a month.
  storage_mb                    = 32768             # Also free: 32 GB.
  backup_retention_days         = 7
  administrator_login           = "pets_admin"
  administrator_password        = random_password.generated["postgres-password"].result
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  public_network_access_enabled = false
  depends_on                    = [azurerm_private_dns_zone_virtual_network_link.postgres]
  lifecycle {
    ignore_changes = [zone] # Azure picks a zone with capacity; pinning zone 1 failed with SkuNotAvailable.
  }
}

resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.pets.id
  value     = "VECTOR"
}

# The free B1MS has 2 GB of memory and a 32 GB disk that does about 1,000 reads a second. One store's three years
# of sales are spread across the tables, so a store's pages took ~45 s from disk on every load with the default
# 256 MB cache. A 768 MB cache keeps a store's working set in memory: the same query then takes 0.3 s.
resource "azurerm_postgresql_flexible_server_configuration" "memory" {
  for_each = {
    shared_buffers           = "98304" # 8 kB pages: 768 MB.
    effective_io_concurrency = "64"    # Read ahead on several pages at once on SSD storage.
  }
  name      = each.key
  server_id = azurerm_postgresql_flexible_server.pets.id
  value     = each.value
}

resource "azurerm_postgresql_flexible_server_database" "db" {
  for_each  = toset(["pets_central", "dagster"])
  name      = each.key
  server_id = azurerm_postgresql_flexible_server.pets.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# Container Apps --------------------------------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "pets" {
  name                = "log-pets-central"
  resource_group_name = local.rg
  location            = local.home # A deleted workspace's name stays reserved in its region for 14 days.
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "pets" {
  name                       = "cae-pets-central"
  resource_group_name        = local.rg
  location                   = local.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.pets.id
  infrastructure_subnet_id   = azurerm_subnet.apps.id
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

locals {
  store_host = "ca-pets-store.${azurerm_container_app_environment.pets.default_domain}"
  database = {
    POSTGRES_HOST    = azurerm_postgresql_flexible_server.pets.fqdn
    POSTGRES_DB      = "pets_central"
    POSTGRES_USER    = "pets_admin"
    POSTGRES_SSLMODE = "require"
  }
  # The store app and the `manage` job: plain settings, and settings that come from Key Vault.
  store_settings = merge(local.database, {
    DJANGO_DEBUG         = "False"
    DJANGO_ALLOWED_HOSTS = local.store_host
    DJANGO_HTTPS         = "True"
    DJANGO_DEMO_SIGN_IN  = "True" # Only the owner's IP address can reach the app.
    ASSISTANT_DB_USER    = "pets_assistant"
    # Policy search's embeddings, signed in with the app's managed identity: no key exists.
    AZURE_OPENAI_ENDPOINT = azurerm_cognitive_account.openai.endpoint
    AZURE_CLIENT_ID       = azurerm_user_assigned_identity.app["store"].client_id
  })
  store_secrets = {
    DJANGO_SECRET_KEY     = "django-secret-key"
    POSTGRES_PASSWORD     = "postgres-password"
    ASSISTANT_DB_PASSWORD = "assistant-db-password"
    DJANGO_DEMO_PASSWORD  = "demo-password"
    ANTHROPIC_API_KEY     = "anthropic-api-key"
  }
  dagster_settings = merge(local.database, {
    DAGSTER_PG_HOST                = azurerm_postgresql_flexible_server.pets.fqdn
    DAGSTER_PG_DB                  = "dagster"
    DAGSTER_PG_USERNAME            = "pets_admin"
    SNOWFLAKE_ACCOUNT              = var.snowflake_account
    SNOWFLAKE_WAREHOUSE            = "PETS_WH"
    SNOWFLAKE_DATABASE             = "PETS_CENTRAL"
    SNOWFLAKE_USER                 = "PETS_LOADER_SVC"
    SNOWFLAKE_ROLE                 = "PETS_LOADER"
    SNOWFLAKE_PRIVATE_KEY_PATH     = "/keys/snowflake-loader-key"
    SNOWFLAKE_DBT_USER             = "PETS_DBT_SVC"
    SNOWFLAKE_DBT_ROLE             = "PETS_TRANSFORMER"
    SNOWFLAKE_DBT_PRIVATE_KEY_PATH = "/keys/snowflake-dbt-key"
    LOYALTY_API_URL                = local.vendor.api_url
    PIPELINE_CRON                  = var.pipeline_cron
  })
  dagster_secrets = {
    POSTGRES_PASSWORD   = "postgres-password"
    DAGSTER_PG_PASSWORD = "postgres-password"
    LOYALTY_API_KEY     = "loyalty-api-key"
  }
}

resource "azurerm_container_app" "store" {
  name                         = "ca-pets-store"
  resource_group_name          = local.rg
  container_app_environment_id = azurerm_container_app_environment.pets.id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app["store"].id]
  }
  registry {
    server   = local.registry
    identity = azurerm_user_assigned_identity.app["store"].id
  }
  dynamic "secret" {
    for_each = toset(values(local.store_secrets))
    content {
      name                = secret.value
      key_vault_secret_id = local.secret_ids[secret.value]
      identity            = azurerm_user_assigned_identity.app["store"].id
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
    ip_security_restriction {
      name             = "owner"
      action           = "Allow"
      ip_address_range = var.owner_ip
    }
  }

  template {
    min_replicas = 0
    max_replicas = 2
    container {
      name   = "store"
      image  = "${local.registry}/pets-store:${var.image_tag}"
      cpu    = 1
      memory = "2Gi"
      dynamic "env" {
        for_each = local.store_settings
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.store_secrets
        content {
          name        = env.key
          secret_name = env.value
        }
      }
    }
  }
  depends_on = [azurerm_role_assignment.pull_images, azurerm_role_assignment.read_secrets]
}

# Migrations, data generation and the policy index. Started with a command, e.g.
#   az containerapp job start -n caj-pets-manage -g rg-pets-central-prod --args "python manage.py migrate"
resource "azurerm_container_app_job" "manage" {
  name                         = "caj-pets-manage"
  resource_group_name          = local.rg
  location                     = local.location
  container_app_environment_id = azurerm_container_app_environment.pets.id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 7200 # Generating the full dataset takes a while on this database.
  replica_retry_limit          = 0

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app["store"].id]
  }
  registry {
    server   = local.registry
    identity = azurerm_user_assigned_identity.app["store"].id
  }
  dynamic "secret" {
    for_each = toset(values(local.store_secrets))
    content {
      name                = secret.value
      key_vault_secret_id = local.secret_ids[secret.value]
      identity            = azurerm_user_assigned_identity.app["store"].id
    }
  }

  template {
    container {
      name    = "manage"
      image   = "${local.registry}/pets-store:${var.image_tag}"
      cpu     = 2
      memory  = "4Gi"
      command = ["python", "manage.py", "migrate"]
      dynamic "env" {
        for_each = merge(local.store_settings, {
          LOYALTY_DATA_BLOB_URL = local.vendor.data_blob_url
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.store_secrets
        content {
          name        = env.key
          secret_name = env.value
        }
      }
    }
  }
  depends_on = [azurerm_role_assignment.pull_images, azurerm_role_assignment.read_secrets]
}

resource "azurerm_container_app" "dagster" {
  name                         = "ca-pets-dagster"
  resource_group_name          = local.rg
  container_app_environment_id = azurerm_container_app_environment.pets.id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app["dagster"].id]
  }
  registry {
    server   = local.registry
    identity = azurerm_user_assigned_identity.app["dagster"].id
  }
  dynamic "secret" {
    for_each = toset(concat(values(local.dagster_secrets), ["snowflake-loader-key", "snowflake-dbt-key"]))
    content {
      name                = secret.value
      key_vault_secret_id = local.secret_ids[secret.value]
      identity            = azurerm_user_assigned_identity.app["dagster"].id
    }
  }

  ingress {
    external_enabled = true
    target_port      = 3000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
    ip_security_restriction {
      name             = "owner"
      action           = "Allow"
      ip_address_range = var.owner_ip
    }
  }

  template {
    # Always one replica: the daemon runs the schedule.
    min_replicas = 1
    max_replicas = 1
    # Every secret as a file under /keys, for the Snowflake key-pair sign-ins.
    volume {
      name         = "keys"
      storage_type = "Secret"
    }
    dynamic "container" {
      for_each = {
        # 1 CPU and 2 GiB in all: it runs only for the screenshot window, so slower runs are fine.
        webserver = { command = [], cpu = 0.25, memory = "0.5Gi" }
        daemon    = { command = ["dagster-daemon", "run", "-m", "orchestration.definitions"], cpu = 0.75, memory = "1.5Gi" }
      }
      content {
        name    = container.key
        image   = "${local.registry}/pets-dagster:${var.image_tag}"
        command = length(container.value.command) > 0 ? container.value.command : null
        cpu     = container.value.cpu
        memory  = container.value.memory
        volume_mounts {
          name = "keys"
          path = "/keys"
        }
        dynamic "env" {
          for_each = local.dagster_settings
          content {
            name  = env.key
            value = env.value
          }
        }
        dynamic "env" {
          for_each = local.dagster_secrets
          content {
            name        = env.key
            secret_name = env.value
          }
        }
      }
    }
  }
  depends_on = [azurerm_role_assignment.pull_images, azurerm_role_assignment.read_secrets]
}
