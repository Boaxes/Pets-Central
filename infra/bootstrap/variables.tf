variable "subscription_id" {
  description = "The Azure subscription (az account show --query id)."
  type        = string
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "github_repository" {
  description = <<-EOT
    The repository whose GitHub Actions may sign in to Azure, as GitHub names it in OIDC tokens: owner and
    repository each with their permanent id, so a renamed or re-created repository can't inherit the trust.
  EOT
  type        = string
  default     = "Boaxes@69285158/pets-central@1424984969"
}

variable "monthly_budget" {
  description = "Dollars a month; the budget emails the subscription's owners at 50%, 80% and 100%."
  type        = number
  default     = 10
}
