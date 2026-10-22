variable "subscription_id" {
  description = "The Azure subscription (az account show --query id)."
  type        = string
}

variable "image_tag" {
  description = "The images to run, tagged by the commit deploy.yml built them from."
  type        = string
}

variable "owner_ip" {
  description = "The only address that may reach the store app and Dagster's UI, e.g. 203.0.113.7/32."
  type        = string
}

variable "snowflake_account" {
  description = "organization-account, e.g. ZDNLOQP-ZB02546."
  type        = string
}

variable "pipeline_cron" {
  description = "When Dagster's daily_pipeline runs, in UTC. Move it to run within the hour for the screenshots."
  type        = string
  default     = "0 9 * * *"
}

variable "location" {
  description = "Where production's compute runs. Central US: this subscription can't create Postgres B1MS in East US 2."
  type        = string
  default     = "centralus"
}
