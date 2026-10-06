// Private endpoints + private DNS for Blob, Key Vault and (optionally) Azure OpenAI, deployed
// only when enablePrivateNetworking=true (PROMPT.md §34 production upgrade path).

param location string
param tags object
param vnetId string
param subnetId string
param namePrefix string

param storageAccountId string
param keyVaultId string

@description('Empty when OCR is disabled.')
param openAiAccountId string = ''

var targets = concat(
  [
    {
      key: 'blob'
      resourceId: storageAccountId
      groupId: 'blob'
      zone: 'privatelink.blob.${environment().suffixes.storage}'
    }
    {
      key: 'vault'
      resourceId: keyVaultId
      groupId: 'vault'
      zone: 'privatelink.vaultcore.azure.net'
    }
  ],
  empty(openAiAccountId)
    ? []
    : [
        {
          key: 'openai'
          resourceId: openAiAccountId
          groupId: 'account'
          zone: 'privatelink.openai.azure.com'
        }
      ]
)

resource zones 'Microsoft.Network/privateDnsZones@2024-06-01' = [
  for target in targets: {
    name: target.zone
    location: 'global'
    tags: tags
  }
]

resource zoneLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [
  for (target, i) in targets: {
    parent: zones[i]
    name: '${namePrefix}-${target.key}-link'
    location: 'global'
    tags: tags
    properties: {
      registrationEnabled: false
      virtualNetwork: {
        id: vnetId
      }
    }
  }
]

resource endpoints 'Microsoft.Network/privateEndpoints@2025-05-01' = [
  for target in targets: {
    name: 'pe-${namePrefix}-${target.key}'
    location: location
    tags: tags
    properties: {
      subnet: {
        id: subnetId
      }
      privateLinkServiceConnections: [
        {
          name: target.key
          properties: {
            privateLinkServiceId: target.resourceId
            groupIds: [
              target.groupId
            ]
          }
        }
      ]
    }
  }
]

resource zoneGroups 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-05-01' = [
  for (target, i) in targets: {
    parent: endpoints[i]
    name: 'default'
    properties: {
      privateDnsZoneConfigs: [
        {
          name: target.key
          properties: {
            privateDnsZoneId: zones[i].id
          }
        }
      ]
    }
  }
]
