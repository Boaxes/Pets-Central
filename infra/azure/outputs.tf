output "store_url" {
  value = "https://${azurerm_container_app.store.ingress[0].fqdn}"
}

output "dagster_url" {
  value = "https://${azurerm_container_app.dagster.ingress[0].fqdn}"
}

output "manage_job" {
  value = azurerm_container_app_job.manage.name
}

output "key_vault" {
  value = azurerm_key_vault.pets.name
}
