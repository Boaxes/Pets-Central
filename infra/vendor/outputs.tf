# What the vendor gives Pets Central: where the API is, and its key. Read by the production and demo stacks.

output "api_url" {
  value = "https://${azurerm_function_app_flex_consumption.rewards.default_hostname}"
}

output "api_key" {
  value     = random_password.api_key.result
  sensitive = true
}

output "function_app_name" {
  value = azurerm_function_app_flex_consumption.rewards.name
}

output "data_container_id" {
  value = azurerm_storage_container.data.id
}

output "data_blob_url" {
  value = "${azurerm_storage_account.vendor.primary_blob_endpoint}${azurerm_storage_container.data.name}/loyalty.sqlite3"
}
