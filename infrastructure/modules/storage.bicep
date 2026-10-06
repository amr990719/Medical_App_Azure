// Document storage (PROMPT.md §19, §20, §48): private container, no public access, no shared
// keys (managed identity + user-delegation SAS only), TLS 1.2, soft delete and versioning.

param name string
param location string
param tags object

@allowed([
  'Standard_LRS'
  'Standard_ZRS'
  'Standard_GRS'
  'Standard_GZRS'
])
param skuName string = 'Standard_LRS'

@description('Private container that holds every uploaded document.')
param containerName string = 'medical-documents'

@description('Blob and container soft-delete retention in days.')
@minValue(1)
@maxValue(365)
param softDeleteRetentionDays int = 14

@description('Delete previous blob versions this many days after they were superseded (0 = keep forever). Deleted documents otherwise survive as versions.')
@minValue(0)
param previousVersionRetentionDays int = 90

@description('true = public network access disabled; reachable through a private endpoint only.')
param privateNetworking bool = false

param logAnalyticsWorkspaceId string = ''

resource account 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: skuName
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    allowCrossTenantReplication: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      // MVP (§34): Container Apps consumption outbound IPs are not fixed, so the public
      // endpoint stays reachable; access still requires Entra + RBAC (shared keys disabled).
      defaultAction: privateNetworking ? 'Deny' : 'Allow'
    }
    encryption: {
      keySource: 'Microsoft.Storage'
      requireInfrastructureEncryption: false
      services: {
        blob: {
          enabled: true
          keyType: 'Account'
        }
      }
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-06-01' = {
  parent: account
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: {
      enabled: true
      days: softDeleteRetentionDays
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: softDeleteRetentionDays
    }
  }
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2025-06-01' = if (previousVersionRetentionDays > 0) {
  parent: account
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'expire-previous-document-versions'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: [
                'blockBlob'
              ]
              prefixMatch: [
                '${containerName}/'
              ]
            }
            actions: {
              version: {
                delete: {
                  daysAfterCreationGreaterThan: previousVersionRetentionDays
                }
              }
            }
          }
        }
      ]
    }
  }
}

#disable-next-line use-recent-api-versions // categoryGroup needs 2021-05-01-preview; the linter only offers 2016-09-01
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'to-log-analytics'
  scope: blobService
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

output id string = account.id
output name string = account.name
output blobEndpoint string = account.properties.primaryEndpoints.blob
output containerName string = container.name
