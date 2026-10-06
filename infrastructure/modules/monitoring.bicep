// Log Analytics workspace + workspace-based Application Insights (PROMPT.md §38).

param logAnalyticsName string
param appInsightsName string
param location string
param tags object

@description('Log retention in days (Log Analytics ingestion and retention are cost drivers, PROMPT.md section 52).')
@minValue(30)
@maxValue(730)
param retentionInDays int = 30

@description('Daily ingestion cap in GB; -1 = no cap.')
param dailyQuotaGb int = -1

@description('true = Application Insights accepts only Entra-authenticated ingestion (the app sets APPLICATIONINSIGHTS_AUTHENTICATION=entra and its identity holds Monitoring Metrics Publisher).')
param disableLocalAuth bool = false

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-02-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
    workspaceCapping: {
      dailyQuotaGb: dailyQuotaGb
    }
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    IngestionMode: 'LogAnalytics'
    DisableLocalAuth: disableLocalAuth
    RetentionInDays: retentionInDays
  }
}

output workspaceId string = workspace.id
output workspaceName string = workspace.name
output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
#disable-next-line outputs-should-not-contain-secrets // not a credential: identifies the resource; ingestion is authorized by Entra when local auth is disabled
output appInsightsConnectionString string = appInsights.properties.ConnectionString
