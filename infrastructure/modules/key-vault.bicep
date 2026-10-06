// Key Vault in RBAC mode with soft delete and purge protection (PROMPT.md §29, §48).
// Secrets are NOT created here (no secret ever passes through a template parameter); they are
// set once per environment with `az keyvault secret set` (docs/azure-deployment.md):
//   django-secret-key, entra-client-secret (+ database-password only if DB_AUTH_MODE=password).

param name string
param location string
param tags object

@minValue(7)
@maxValue(90)
param softDeleteRetentionInDays int = 90

@description('true = public network access disabled; reachable through a private endpoint only.')
param privateNetworking bool = false

param logAnalyticsWorkspaceId string = ''

resource vault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: softDeleteRetentionInDays
    enablePurgeProtection: true
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: false
    publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      // MVP (§34): public endpoint, every data-plane call still needs Entra + RBAC.
      defaultAction: privateNetworking ? 'Deny' : 'Allow'
    }
  }
}

#disable-next-line use-recent-api-versions // categoryGroup needs 2021-05-01-preview; the linter only offers 2016-09-01
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'to-log-analytics'
  scope: vault
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'audit'
        enabled: true
      }
    ]
  }
}

output id string = vault.id
output name string = vault.name
output uri string = vault.properties.vaultUri
