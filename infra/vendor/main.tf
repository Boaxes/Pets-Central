# The loyalty vendor's Rewards API. In the story another company, Pawprint Loyalty, runs it, so it lives in its own resource group
# and Pets Central only ever reaches it over HTTPS with the API key it was issued. Kept after production is
# destroyed: the demo uses the same deployment.

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
  features {}
  subscription_id                 = var.subscription_id
  storage_use_azuread             = true
  resource_provider_registrations = "none"
}

locals {
  suffix = substr(replace(var.subscription_id, "-", ""), 0, 8)
}

data "azurerm_resource_group" "vendor" {
  name = "rg-pets-central-vendor"
}

# The key the vendor issues to Pets Central.
resource "random_password" "api_key" {
  length  = 40
  special = false
}

resource "azurerm_storage_account" "vendor" {
  name                            = "stpetsvendor${local.suffix}"
  resource_group_name             = data.azurerm_resource_group.vendor.name
  location                        = data.azurerm_resource_group.vendor.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
}

# The Function App's code packages.
resource "azurerm_storage_container" "deployments" {
  name               = "deployments"
  storage_account_id = azurerm_storage_account.vendor.id
}

# loyalty.sqlite3: private, read by the Function App's identity.
resource "azurerm_storage_container" "data" {
  name               = "data"
  storage_account_id = azurerm_storage_account.vendor.id
}

resource "azurerm_service_plan" "rewards" {
  name                = "asp-pets-rewards"
  resource_group_name = data.azurerm_resource_group.vendor.name
  location            = data.azurerm_resource_group.vendor.location
  os_type             = "Linux"
  sku_name            = "FC1" # Flex Consumption: pay per request, nothing when idle.
}

resource "azurerm_function_app_flex_consumption" "rewards" {
  name                        = "func-pets-rewards-${local.suffix}"
  resource_group_name         = data.azurerm_resource_group.vendor.name
  location                    = data.azurerm_resource_group.vendor.location
  service_plan_id             = azurerm_service_plan.rewards.id
  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.vendor.primary_blob_endpoint}${azurerm_storage_container.deployments.name}"
  storage_authentication_type = "StorageAccountConnectionString"
  storage_access_key          = azurerm_storage_account.vendor.primary_access_key
  runtime_name                = "python"
  runtime_version             = "3.13"
  maximum_instance_count      = 40
  instance_memory_in_mb       = 2048
  https_only                  = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    # The docs page's Try It Out calls the API from a browser. Azure answers the CORS preflight itself, before
    # the app sees it, so the allowed origin is set here.
    cors {
      allowed_origins = ["https://pawprint-loyalty-docs.pages.dev"]
    }
  }

  app_settings = {
    LOYALTY_API_KEYS     = random_password.api_key.result
    LOYALTY_DB_URL       = "${azurerm_storage_account.vendor.primary_blob_endpoint}${azurerm_storage_container.data.name}/loyalty.sqlite3"
    LOYALTY_RATE_LIMIT   = "20"
    LOYALTY_RATE_BURST   = "40"
    LOYALTY_FAILURE_RATE = "0.02"
    LOYALTY_DEMO_KEY     = var.demo_api_key
  }
}

resource "azurerm_role_assignment" "rewards_reads_data" {
  scope                = azurerm_storage_container.data.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_function_app_flex_consumption.rewards.identity[0].principal_id
}
