// User-assigned managed identity shared by the Django app and its jobs (PROMPT.md §4, §29).
// Created before every other module so its role assignments exist before the Container App
// pulls its image or resolves Key Vault references (no circular dependency).

@description('Identity name.')
param name string

param location string
param tags object

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: name
  location: location
  tags: tags
}

output id string = identity.id
output name string = identity.name
output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
