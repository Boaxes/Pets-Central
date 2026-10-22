# What GitHub Actions needs to sign in and find the state. None of these are secrets.

output "azure_client_id" {
  value = azurerm_user_assigned_identity.github.client_id
}

output "azure_tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "state_storage_account" {
  value = azurerm_storage_account.state.name
}

output "registry" {
  value = azurerm_container_registry.shared.login_server
}

output "registry_id" {
  value = azurerm_container_registry.shared.id
}
