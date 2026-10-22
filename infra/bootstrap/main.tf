# What has to exist before GitHub Actions can run Terraform: somewhere to keep state, an identity for CI, the
# resource groups CI may change, and the budget. Applied once from the owner's machine, signed in with `az login`;
# its state then moves into the storage account it creates (see infra/README.md).

terraform {
  required_version = ">= 1.10"
  backend "azurerm" {} # Settings in ../backend.hcl.
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  storage_use_azuread             = true # The state account allows no shared keys.
  resource_provider_registrations = "none"
  # Registers the services the other stacks use, once, without Terraform owning them: registration is
  # subscription-wide, and CI's identity isn't allowed to do it.
  resource_providers_to_register = [
    "Microsoft.App", "Microsoft.CognitiveServices", "Microsoft.ContainerRegistry", "Microsoft.Consumption",
    "Microsoft.DBforPostgreSQL",
    "Microsoft.KeyVault", "Microsoft.ManagedIdentity", "Microsoft.Network", "Microsoft.OperationalInsights",
    "Microsoft.Storage", "Microsoft.Web", "microsoft.insights",
  ]
}

data "azurerm_client_config" "current" {}

locals {
  # Storage account names are global and lowercase; the subscription id makes this one unique.
  state_account = "stpetstf${substr(replace(var.subscription_id, "-", ""), 0, 8)}"
}

# Resource groups -------------------------------------------------------------------------------------------------
# Created here so CI's identity can be given rights to exactly these and nothing else in the subscription.

resource "azurerm_resource_group" "shared" {
  name     = "rg-pets-central-shared"
  location = var.location
  tags     = { purpose = "Terraform state and CI identity; kept" }
}

resource "azurerm_resource_group" "stack" {
  for_each = {
    prod   = "Pets Central production; destroyed after the screenshots"
    vendor = "The loyalty vendor's Rewards API, a separate company in the story; kept for the demo"
    demo   = "The cheap stand-in demo; kept"
  }
  name     = "rg-pets-central-${each.key}"
  location = var.location
  tags     = { purpose = each.value }
}

# Terraform state -------------------------------------------------------------------------------------------------

resource "azurerm_storage_account" "state" {
  name                            = local.state_account
  resource_group_name             = azurerm_resource_group.shared.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  blob_properties {
    versioning_enabled = true # Every earlier state stays recoverable.
  }
}

resource "azurerm_storage_container" "state" {
  name               = "tfstate"
  storage_account_id = azurerm_storage_account.state.id
  depends_on         = [azurerm_role_assignment.owner_state]
}

resource "azurerm_role_assignment" "owner_state" {
  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# The identity GitHub Actions signs in as, with OIDC: no password or secret exists to leak --------------------------

resource "azurerm_user_assigned_identity" "github" {
  name                = "id-pets-central-github"
  resource_group_name = azurerm_resource_group.shared.name
  location            = var.location
}

resource "azurerm_federated_identity_credential" "github" {
  for_each = {
    main          = "repo:${var.github_repository}:ref:refs/heads/main" # Deploys, after a merge.
    pull-requests = "repo:${var.github_repository}:pull_request"        # Plans, on a pull request.
  }
  name                      = "github-${each.key}"
  user_assigned_identity_id = azurerm_user_assigned_identity.github.id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = each.value
}

resource "azurerm_role_assignment" "github_state" {
  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
}

resource "azurerm_role_assignment" "github_contributor" {
  for_each             = azurerm_resource_group.stack
  scope                = each.value.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
}

# Contributor can't write secret values; deploys create Key Vault secrets (placeholders the owner then fills in).
resource "azurerm_role_assignment" "github_secrets" {
  for_each             = { for key, group in azurerm_resource_group.stack : key => group if key != "vendor" }
  scope                = each.value.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
}

# The owner sets the outside secrets (the Anthropic and Snowflake keys) in the Key Vaults; Owner alone can't.
resource "azurerm_role_assignment" "owner_secrets" {
  for_each             = { for key, group in azurerm_resource_group.stack : key => group if key != "vendor" }
  scope                = each.value.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# One registry for production and the demo, kept like the state. Standard is in the subscription's free services.
resource "azurerm_container_registry" "shared" {
  name                = "crpetscentral${substr(replace(var.subscription_id, "-", ""), 0, 8)}"
  resource_group_name = azurerm_resource_group.shared.name
  location            = var.location
  sku                 = "Standard"
  admin_enabled       = false # Pulls use managed identities; there is no registry password.
}

resource "azurerm_role_assignment" "github_push" {
  scope                = azurerm_container_registry.shared.id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
}

# CI may grant only these roles, only inside the stack resource groups and on the registry: pulling images,
# reading Key Vault secrets, reading or writing blobs (the loyalty file), and calling the embedding model.
locals {
  grantable_roles = join(", ", [
    "7f951dda-4ed3-4680-a7ca-43fe172d538d", # AcrPull
    "4633458b-17de-408a-b874-0445c86b69e6", # Key Vault Secrets User
    "ba92f5b4-2d11-453d-a403-e96b0029c9fe", # Storage Blob Data Contributor
    "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1", # Storage Blob Data Reader
    "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd", # Cognitive Services OpenAI User
  ])
}

resource "azurerm_role_assignment" "github_grants" {
  # The stack resource groups, and the registry, where apps are given AcrPull.
  for_each = merge({ for key, group in azurerm_resource_group.stack : key => group.id },
  { registry = azurerm_container_registry.shared.id })
  scope                = each.value
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
  condition_version    = "2.0"
  condition            = <<-EOT
    (
      (!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'}))
      OR
      (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${local.grantable_roles}})
    )
    AND
    (
      (!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'}))
      OR
      (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${local.grantable_roles}})
    )
  EOT
}

# Budget: emails only. Pay-as-you-go subscriptions can't be hard-capped -------------------------------------------

resource "azurerm_consumption_budget_subscription" "monthly" {
  name            = "pets-central-monthly"
  subscription_id = "/subscriptions/${var.subscription_id}"
  amount          = var.monthly_budget
  time_grain      = "Monthly"
  time_period {
    start_date = "2026-10-01T00:00:00Z"
  }
  dynamic "notification" {
    for_each = [[50, "Actual"], [80, "Actual"], [100, "Actual"], [100, "Forecasted"]]
    content {
      threshold      = notification.value[0]
      threshold_type = notification.value[1]
      operator       = "GreaterThanOrEqualTo"
      contact_roles  = ["Owner"]
    }
  }
}
