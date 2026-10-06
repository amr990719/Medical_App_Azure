// Optional Azure OpenAI account for server-side OCR (PROMPT.md §21), deployed only when
// enableOcr=true. Keys are disabled: the app authenticates with its managed identity
// (Cognitive Services OpenAI User). Sending identity documents to the service needs legal
// approval first (docs/security.md L2/L3); OCR_ENABLED follows enableOcr.

param name string
param location string
param tags object

@description('Model deployment name the app calls (AZURE_OPENAI_DEPLOYMENT).')
param deploymentName string = 'ocr-vision'

@description('A vision-capable chat model.')
param modelName string = 'gpt-4o'
param modelVersion string = '2024-11-20'

@description('Standard = processed in the resource region; GlobalStandard / DataZoneStandard route across regions (data-residency decision L3).')
@allowed([
  'Standard'
  'DataZoneStandard'
  'GlobalStandard'
])
param deploymentSkuName string = 'Standard'

@description('Capacity in thousands of tokens per minute.')
@minValue(1)
param capacity int = 10

@description('true = public network access disabled; reachable through a private endpoint only.')
param privateNetworking bool = false

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: name
    disableLocalAuth: true
    publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: privateNetworking ? 'Deny' : 'Allow'
    }
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: deploymentName
  sku: {
    name: deploymentSkuName
    capacity: capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

output id string = account.id
output name string = account.name
output endpoint string = account.properties.endpoint
output deploymentName string = deployment.name
