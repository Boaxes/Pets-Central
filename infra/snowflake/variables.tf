variable "organization_name" {
  description = "The Snowflake organization (SELECT CURRENT_ORGANIZATION_NAME())."
  type        = string
}

variable "account_name" {
  description = "The Snowflake account within the organization (SELECT CURRENT_ACCOUNT_NAME())."
  type        = string
}

variable "analyst_user" {
  description = "The owner's own Snowflake user, granted the reporting role for Power BI and Cortex Analyst."
  type        = string
}

variable "terraform_private_key_path" {
  description = "Private key of PETS_TERRAFORM, the user infra/snowflake/bootstrap.sql creates."
  type        = string
  default     = "~/.snowflake/keys/pets_terraform.p8"
}

# Public keys only (safe to commit); the matching private keys stay with whoever runs the loaders, dbt and Power BI.
variable "loader_public_key_path" {
  type    = string
  default = "keys/pets_loader.pub"
}

variable "dbt_public_key_path" {
  type    = string
  default = "keys/pets_dbt.pub"
}

variable "reporter_public_key_path" {
  type    = string
  default = "keys/pets_reporter.pub"
}

variable "monthly_credit_quota" {
  description = "Credits Pets Central's warehouse may use in a month before it is suspended."
  type        = number
  default     = 50
}
