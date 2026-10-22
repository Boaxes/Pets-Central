variable "subscription_id" {
  description = "The Azure subscription (az account show --query id)."
  type        = string
}

variable "demo_api_key" {
  description = "The public demo key the docs page's Try It Out uses (2 requests a second). Chosen by the owner; the LOYALTY_DEMO_KEY secret in CI."
  type        = string
  sensitive   = true
  default     = ""
}
