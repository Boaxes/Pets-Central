# Everything Pets Central has in Snowflake. Every object here is named PETS_*; Terraform never touches anything
# else in the account (the account is shared with another project).

terraform {
  required_version = ">= 1.10"
  backend "azurerm" {} # Settings in ../backend.hcl.
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.0"
    }
  }
}

provider "snowflake" {
  organization_name = var.organization_name
  account_name      = var.account_name
  user              = "PETS_TERRAFORM"
  role              = "ACCOUNTADMIN"
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(pathexpand(var.terraform_private_key_path))
}

locals {
  # PETS_CENTRAL_DEV for local runs and CI, PETS_CENTRAL for production. Same layout, same roles.
  databases = toset(["PETS_CENTRAL_DEV", "PETS_CENTRAL"])

  # A public key file's body, as Snowflake wants it: no BEGIN/END lines, no line breaks.
  loader_public_key   = replace(file(pathexpand(var.loader_public_key_path)), "/-----[A-Z ]+-----|\\s/", "")
  dbt_public_key      = replace(file(pathexpand(var.dbt_public_key_path)), "/-----[A-Z ]+-----|\\s/", "")
  reporter_public_key = replace(file(pathexpand(var.reporter_public_key_path)), "/-----[A-Z ]+-----|\\s/", "")
}

# Spending -------------------------------------------------------------------------------------------------------

# Attached to the Pets Central warehouse only, so it can never suspend another project's warehouse.
resource "snowflake_resource_monitor" "pets" {
  name                      = "PETS_MONITOR"
  credit_quota              = var.monthly_credit_quota
  notify_triggers           = [75, 90]
  suspend_trigger           = 100
  suspend_immediate_trigger = 110
}

resource "snowflake_warehouse" "pets" {
  name                = "PETS_WH"
  warehouse_size      = "XSMALL"
  auto_suspend        = 60
  auto_resume         = true
  initially_suspended = true
  resource_monitor    = snowflake_resource_monitor.pets.name
}

# Databases and the two schemas Terraform owns ------------------------------------------------------------------
# dbt creates STAGING, INTERMEDIATE and EVALUATION itself. MARTS is created here so the reporting role's grants
# exist before dbt builds anything into it.

resource "snowflake_database" "pets" {
  for_each = local.databases
  name     = each.key
}

resource "snowflake_schema" "raw" {
  for_each = local.databases
  database = snowflake_database.pets[each.key].name
  name     = "RAW"
}

resource "snowflake_schema" "marts" {
  for_each = local.databases
  database = snowflake_database.pets[each.key].name
  name     = "MARTS"
}

# Roles, each granted to SYSADMIN so administrators can see what they own ----------------------------------------

resource "snowflake_account_role" "role" {
  for_each = toset(["PETS_LOADER", "PETS_TRANSFORMER", "PETS_REPORTER"])
  name     = each.key
}

resource "snowflake_grant_account_role" "to_sysadmin" {
  for_each         = snowflake_account_role.role
  role_name        = each.value.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_privileges_to_account_role" "warehouse" {
  for_each          = snowflake_account_role.role
  account_role_name = each.value.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.pets.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "database_usage" {
  for_each = {
    for pair in setproduct(keys(snowflake_account_role.role), local.databases) : "${pair[0]}/${pair[1]}" => pair
  }
  account_role_name = each.value[0]
  privileges        = each.value[0] == "PETS_TRANSFORMER" ? ["USAGE", "CREATE SCHEMA"] : ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.pets[each.value[1]].name
  }
  depends_on = [snowflake_account_role.role]
}

# The loader writes RAW and nothing else ----------------------------------------------------------------------

resource "snowflake_grant_privileges_to_account_role" "loader_raw" {
  for_each          = local.databases
  account_role_name = snowflake_account_role.role["PETS_LOADER"].name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE FILE FORMAT"]
  on_schema {
    schema_name = snowflake_schema.raw[each.key].fully_qualified_name
  }
}

# dbt reads RAW and builds everything after it ------------------------------------------------------------------

resource "snowflake_grant_privileges_to_account_role" "transformer_raw" {
  for_each          = local.databases
  account_role_name = snowflake_account_role.role["PETS_TRANSFORMER"].name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.raw[each.key].fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "transformer_raw_tables" {
  for_each          = local.databases
  account_role_name = snowflake_account_role.role["PETS_TRANSFORMER"].name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.raw[each.key].fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "transformer_marts" {
  for_each          = local.databases
  account_role_name = snowflake_account_role.role["PETS_TRANSFORMER"].name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    schema_name = snowflake_schema.marts[each.key].fully_qualified_name
  }
}

# Reporting reads the marts and nothing else ---------------------------------------------------------------------

resource "snowflake_grant_privileges_to_account_role" "reporter_marts" {
  for_each          = local.databases
  account_role_name = snowflake_account_role.role["PETS_REPORTER"].name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.marts[each.key].fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "reporter_mart_objects" {
  for_each = {
    for pair in setproduct(local.databases, ["TABLES", "VIEWS"]) : "${pair[0]}/${pair[1]}" => pair
  }
  account_role_name = snowflake_account_role.role["PETS_REPORTER"].name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = each.value[1]
      in_schema          = snowflake_schema.marts[each.value[0]].fully_qualified_name
    }
  }
}

# People and services ------------------------------------------------------------------------------------------

# The owner's own user reads the marts as the reporting role (in Snowsight and the analytics app).
resource "snowflake_grant_account_role" "reporter_to_analyst" {
  role_name = snowflake_account_role.role["PETS_REPORTER"].name
  user_name = var.analyst_user
}

resource "snowflake_service_user" "loader" {
  name              = "PETS_LOADER_SVC"
  default_role      = snowflake_account_role.role["PETS_LOADER"].name
  default_warehouse = snowflake_warehouse.pets.name
  rsa_public_key    = local.loader_public_key
  comment           = "Dagster's store and loyalty loaders"
}

resource "snowflake_service_user" "dbt" {
  name              = "PETS_DBT_SVC"
  default_role      = snowflake_account_role.role["PETS_TRANSFORMER"].name
  default_warehouse = snowflake_warehouse.pets.name
  rsa_public_key    = local.dbt_public_key
  comment           = "dbt, run by Dagster and CI"
}

resource "snowflake_grant_account_role" "loader_user" {
  role_name = snowflake_account_role.role["PETS_LOADER"].name
  user_name = snowflake_service_user.loader.name
}

# Power BI's import signs in with a key pair, as a user that can read the marts and nothing else.
resource "snowflake_service_user" "reporter" {
  name              = "PETS_REPORTER_SVC"
  default_role      = snowflake_account_role.role["PETS_REPORTER"].name
  default_warehouse = snowflake_warehouse.pets.name
  rsa_public_key    = local.reporter_public_key
  comment           = "Power BI's import of the marts"
}

resource "snowflake_grant_account_role" "reporter_user" {
  role_name = snowflake_account_role.role["PETS_REPORTER"].name
  user_name = snowflake_service_user.reporter.name
}

resource "snowflake_grant_account_role" "dbt_user" {
  role_name = snowflake_account_role.role["PETS_TRANSFORMER"].name
  user_name = snowflake_service_user.dbt.name
}

# The analytics app (Streamlit in Snowflake) ----------------------------------------------------------------------
# It lives in PETS_CENTRAL.APPS and is deployed by deploy.yml as the reporting role, so the role owns it and the app,
# and the SQL Cortex Analyst writes for it, can read the marts and nothing else.

resource "snowflake_schema" "apps" {
  database = snowflake_database.pets["PETS_CENTRAL"].name
  name     = "APPS"
}

resource "snowflake_grant_privileges_to_account_role" "reporter_apps" {
  account_role_name = snowflake_account_role.role["PETS_REPORTER"].name
  privileges        = ["USAGE", "CREATE STREAMLIT", "CREATE STAGE"]
  on_schema {
    schema_name = snowflake_schema.apps.fully_qualified_name
  }
}

# Terraform's own user deploys the app, switching to the reporting role to do it.
resource "snowflake_grant_account_role" "reporter_to_terraform" {
  role_name = snowflake_account_role.role["PETS_REPORTER"].name
  user_name = "PETS_TERRAFORM"
}

# Cortex Analyst isn't hosted in AWS US East 2, so the account may send Cortex requests to other AWS US regions.
# Account-wide: the owner agreed on 2026-10-19 (the Whales project doesn't use Cortex).
resource "snowflake_account_parameter" "cortex_cross_region" {
  key   = "CORTEX_ENABLED_CROSS_REGION"
  value = "AWS_US"
}
