// Medical Syndicates Treatment Project — one environment per resource group (PROMPT.md §33, §49).
//
//   az deployment group create -g <rg> -f infrastructure/main.bicep -p infrastructure/parameters/<env>.bicepparam
//
// First deployment of an environment: deployApplication=false (everything except the Container
// App, its jobs and the SWA link), then set the Key Vault secrets, run
// scripts/setup-postgres-entra.sh and push an image, then deploy again with
// deployApplication=true and containerImage=<registry>/medical-backend:<tag>
// (docs/azure-deployment.md). Container Apps resolve Key Vault references at creation, so the
// secrets must exist first.

targetScope = 'resourceGroup'

// --- Environment ---------------------------------------------------------------------------------

@allowed([
  'dev'
  'staging'
  'prod'
])
param environmentName string

@description('Region for every resource except Static Web Apps (and Azure OpenAI when openAiLocation is set). Data residency: docs/security.md L3.')
param location string = resourceGroup().location

@description('Short lowercase alphanumeric prefix used in resource names.')
@minLength(3)
@maxLength(6)
param baseName string = 'medsyn'

@description('Static Web Apps region (limited availability; serves static files only).')
@allowed([
  'westeurope'
  'centralus'
  'eastus2'
  'westus2'
  'eastasia'
])
param staticWebAppLocation string = 'westeurope'

@description('Extra tags merged into the standard ones.')
param tags object = {}

@description('false on the first deployment of an environment (before Key Vault secrets and an image exist).')
param deployApplication bool = true

@description('Full image reference for the app and its jobs. Required when deployApplication=true.')
param containerImage string = ''

@description('Public hostname users reach (custom domain bound to the Static Web App). Empty = the Static Web App default hostname.')
param publicHostname string = ''

// --- Feature switches ----------------------------------------------------------------------------

@description('Deploy Azure OpenAI and turn OCR on. Keep false until legal decision L2/L3 is approved (docs/security.md).')
param enableOcr bool = false

@description('Production upgrade path (PROMPT.md section 34): VNet-integrated Container Apps, VNet-integrated PostgreSQL, private endpoints for Blob/Key Vault/OpenAI. Must be chosen when the environment is created (PostgreSQL networking cannot change later).')
param enablePrivateNetworking bool = false

@description('Send Key Vault, Blob and PostgreSQL resource logs to Log Analytics.')
param enableDiagnostics bool = true

// --- Container Apps sizes (§35) ------------------------------------------------------------------

param containerCpu string = '0.5'
param containerMemory string = '1Gi'

@minValue(0)
param minReplicas int = 1
@minValue(1)
param maxReplicas int = 3
@minValue(1)
param httpConcurrency int = 20
@minValue(1)
param gunicornWorkers int = 2

@description('Cron (UTC) for the blob cleanup job.')
param cleanupCron string = '30 1 * * *'

param containerRegistrySku string = 'Basic'

// --- PostgreSQL (§26, §48) -----------------------------------------------------------------------

param postgresVersion string = '16'
param postgresSkuName string = 'Standard_B1ms'
param postgresSkuTier string = 'Burstable'
param postgresStorageSizeGB int = 32
param postgresBackupRetentionDays int = 7
param postgresGeoRedundantBackup bool = false
param postgresHighAvailabilityMode string = 'Disabled'
param postgresDatabaseName string = 'medical'

@description('Password authentication fallback (PROMPT.md section 26). Off by default: the app uses Entra tokens.')
param postgresPasswordAuth bool = false
param postgresAdministratorLogin string = ''
@secure()
param postgresAdministratorPassword string = ''

@description('Optional Entra admin group/user object id; otherwise set by scripts/setup-postgres-entra.sh.')
param postgresEntraAdminObjectId string = ''
param postgresEntraAdminPrincipalName string = ''
param postgresEntraAdminPrincipalType string = 'Group'

// --- Storage, Key Vault, monitoring (§20, §29, §38, §48) ---------------------------------------

param storageSkuName string = 'Standard_LRS'
param blobSoftDeleteRetentionDays int = 14
param blobPreviousVersionRetentionDays int = 90
param keyVaultSoftDeleteRetentionDays int = 90

@description('Operator who sets the Key Vault secrets (Key Vault Secrets Officer on this vault). Optional.')
param keyVaultOperatorPrincipalId string = ''
param keyVaultOperatorPrincipalType string = 'User'

param logAnalyticsRetentionDays int = 30
param logAnalyticsDailyQuotaGb int = -1

@description('Q-T14: true = Application Insights accepts Entra-authenticated ingestion only.')
param appInsightsDisableLocalAuth bool = false

// --- Azure OpenAI (§21; only with enableOcr) -----------------------------------------------------

param openAiLocation string = location
param openAiModelName string = 'gpt-4o'
param openAiModelVersion string = '2024-11-20'
param openAiDeploymentSkuName string = 'Standard'
param openAiCapacity int = 10
param openAiApiVersion string = '2024-10-21'

// --- Microsoft Entra External ID (§27; values from scripts/create-entra-app.sh) ----------------

@description('e.g. https://<tenant-subdomain>.ciamlogin.com/<tenant-id>')
param entraAuthority string = ''
param entraTenantId string = ''
param entraClientId string = ''
param entraAdminRequireMfa bool = true

// --- Names (uniqueString per resource group + environment; no hard-coded global names) ------------

var envShort = {
  dev: 'dev'
  staging: 'stg'
  prod: 'prd'
}[environmentName]
var token = uniqueString(resourceGroup().id, environmentName, baseName)
var prefix = '${baseName}-${envShort}'
var names = {
  identity: 'id-${prefix}'
  logAnalytics: 'log-${prefix}-${token}'
  appInsights: 'appi-${prefix}-${token}'
  keyVault: take('kv${baseName}${envShort}${token}', 24)
  storage: take('st${baseName}${envShort}${token}', 24)
  registry: 'cr${baseName}${envShort}${token}'
  postgres: 'psql-${prefix}-${token}'
  containerEnv: 'cae-${prefix}'
  app: 'ca-${prefix}-api'
  migrateJob: 'caj-${prefix}-migrate'
  cleanupJob: 'caj-${prefix}-cleanup'
  staticWebApp: 'swa-${prefix}-${token}'
  openAi: 'oai-${prefix}-${token}'
  vnet: 'vnet-${prefix}'
}

var allTags = union(tags, {
  application: 'medical-syndicates'
  environment: environmentName
  'managed-by': 'bicep'
})

// --- Foundation ----------------------------------------------------------------------------------

module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: {
    name: names.identity
    location: location
    tags: allTags
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    logAnalyticsName: names.logAnalytics
    appInsightsName: names.appInsights
    location: location
    tags: allTags
    retentionInDays: logAnalyticsRetentionDays
    dailyQuotaGb: logAnalyticsDailyQuotaGb
    disableLocalAuth: appInsightsDisableLocalAuth
  }
}

module network 'modules/network.bicep' = if (enablePrivateNetworking) {
  name: 'network'
  params: {
    name: names.vnet
    location: location
    tags: allTags
    postgresPrivateDnsZoneName: '${names.postgres}.private.postgres.database.azure.com'
  }
}

var diagnosticsWorkspaceId = enableDiagnostics ? monitoring.outputs.workspaceId : ''

module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  params: {
    name: names.keyVault
    location: location
    tags: allTags
    softDeleteRetentionInDays: keyVaultSoftDeleteRetentionDays
    privateNetworking: enablePrivateNetworking
    logAnalyticsWorkspaceId: diagnosticsWorkspaceId
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: names.storage
    location: location
    tags: allTags
    skuName: storageSkuName
    softDeleteRetentionDays: blobSoftDeleteRetentionDays
    previousVersionRetentionDays: blobPreviousVersionRetentionDays
    privateNetworking: enablePrivateNetworking
    logAnalyticsWorkspaceId: diagnosticsWorkspaceId
  }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    name: names.postgres
    location: location
    tags: allTags
    version: postgresVersion
    skuName: postgresSkuName
    skuTier: postgresSkuTier
    storageSizeGB: postgresStorageSizeGB
    backupRetentionDays: postgresBackupRetentionDays
    geoRedundantBackup: postgresGeoRedundantBackup
    highAvailabilityMode: postgresHighAvailabilityMode
    passwordAuth: postgresPasswordAuth
    administratorLogin: postgresAdministratorLogin
    administratorPassword: postgresAdministratorPassword
    entraAdminObjectId: postgresEntraAdminObjectId
    entraAdminPrincipalName: postgresEntraAdminPrincipalName
    entraAdminPrincipalType: postgresEntraAdminPrincipalType
    delegatedSubnetId: enablePrivateNetworking ? network!.outputs.postgresSubnetId : ''
    privateDnsZoneId: enablePrivateNetworking ? network!.outputs.postgresPrivateDnsZoneId : ''
    logAnalyticsWorkspaceId: diagnosticsWorkspaceId
  }
}

module registry 'modules/container-registry.bicep' = {
  name: 'container-registry'
  params: {
    name: names.registry
    location: location
    tags: allTags
    skuName: containerRegistrySku
  }
}

module openAi 'modules/openai.bicep' = if (enableOcr) {
  name: 'openai'
  params: {
    name: names.openAi
    location: openAiLocation
    tags: allTags
    modelName: openAiModelName
    modelVersion: openAiModelVersion
    deploymentSkuName: openAiDeploymentSkuName
    capacity: openAiCapacity
    privateNetworking: enablePrivateNetworking
  }
}

module privateEndpoints 'modules/private-endpoints.bicep' = if (enablePrivateNetworking) {
  name: 'private-endpoints'
  params: {
    location: location
    tags: allTags
    namePrefix: prefix
    vnetId: network!.outputs.vnetId
    subnetId: network!.outputs.privateEndpointSubnetId
    storageAccountId: storage.outputs.id
    keyVaultId: keyVault.outputs.id
    openAiAccountId: enableOcr ? openAi!.outputs.id : ''
  }
}

module roleAssignments 'modules/role-assignments.bicep' = {
  name: 'role-assignments'
  params: {
    principalId: identity.outputs.principalId
    storageAccountName: storage.outputs.name
    blobContainerName: storage.outputs.containerName
    keyVaultName: keyVault.outputs.name
    containerRegistryName: registry.outputs.name
    appInsightsName: monitoring.outputs.appInsightsName
    openAiAccountName: enableOcr ? openAi!.outputs.name : ''
    operatorPrincipalId: keyVaultOperatorPrincipalId
    operatorPrincipalType: keyVaultOperatorPrincipalType
  }
}

module containerEnv 'modules/container-apps-env.bicep' = {
  name: 'container-apps-env'
  params: {
    name: names.containerEnv
    location: location
    tags: allTags
    logAnalyticsWorkspaceName: monitoring.outputs.workspaceName
    infrastructureSubnetId: enablePrivateNetworking ? network!.outputs.containerAppsSubnetId : ''
  }
}

module staticWebApp 'modules/static-web-app.bicep' = {
  name: 'static-web-app'
  params: {
    name: names.staticWebApp
    location: staticWebAppLocation
    tags: allTags
  }
}

// --- Application (second phase) ------------------------------------------------------------------

var publicHost = empty(publicHostname) ? staticWebApp.outputs.defaultHostname : publicHostname
var appFqdn = '${names.app}.${containerEnv.outputs.defaultDomain}'
// Django sees the Container App host behind the linked backend (Q-T13, NOT VERIFIED): both
// the backend FQDN and the public host are allowed; never '*'.
var allowedHosts = join(union([appFqdn, publicHost], [staticWebApp.outputs.defaultHostname]), ',')
var trustedOrigins = join(
  union(['https://${publicHost}'], ['https://${staticWebApp.outputs.defaultHostname}']),
  ','
)

var baseSettings = {
  DJANGO_SETTINGS_MODULE: 'config.settings.production'
  DEBUG: 'false'
  DEV_AUTH_ENABLED: 'false'
  API_DOCS_ENABLED: 'false'
  LOG_LEVEL: 'INFO'
  ALLOWED_HOSTS: allowedHosts
  CSRF_TRUSTED_ORIGINS: trustedOrigins
  // X-Forwarded-For entries appended by the SWA linked backend and the Container Apps ingress
  // (client address for throttles and the audit hash; Q-T13, NOT VERIFIED on Azure).
  TRUSTED_PROXY_COUNT: '2'
  GUNICORN_WORKERS: string(gunicornWorkers)
  // Managed identity for every Azure SDK call (developer credentials excluded).
  AZURE_CLIENT_ID: identity.outputs.clientId
  AZURE_TOKEN_CREDENTIALS: 'prod'
  KEY_VAULT_URL: keyVault.outputs.uri
  // PostgreSQL: the user is the identity's role; the password is an Entra token per connection.
  DATABASE_URL: 'postgres://${names.identity}@${postgres.outputs.fqdn}:5432/${postgresDatabaseName}'
  DB_AUTH_MODE: 'entra'
  DB_SSLMODE: 'require'
  // Throttle counters shared by every replica (Q-T6); the table is created by the migrate job.
  CACHE_URL: 'dbcache://django_cache'
  BLOB_BACKEND: 'azure'
  BLOB_ACCOUNT_URL: storage.outputs.blobEndpoint
  BLOB_CONTAINER: storage.outputs.containerName
  BLOB_CREATE_CONTAINER: 'false'
  ENTRA_AUTHORITY: entraAuthority
  ENTRA_TENANT_ID: entraTenantId
  ENTRA_CLIENT_ID: entraClientId
  ENTRA_REDIRECT_URI: 'https://${publicHost}/api/v1/auth/callback/'
  ENTRA_POST_LOGOUT_REDIRECT_URI: 'https://${publicHost}/signed-out'
  ENTRA_ADMIN_REQUIRE_MFA: string(entraAdminRequireMfa)
  OCR_ENABLED: string(enableOcr)
}

var telemetrySettings = appInsightsDisableLocalAuth ? { APPLICATIONINSIGHTS_AUTHENTICATION: 'entra' } : {}

var ocrSettings = enableOcr
  ? {
      OCR_PROVIDER: 'azure_openai'
      AZURE_OPENAI_ENDPOINT: openAi!.outputs.endpoint
      AZURE_OPENAI_DEPLOYMENT: openAi!.outputs.deploymentName
      AZURE_OPENAI_API_VERSION: openAiApiVersion
    }
  : {}

module app 'modules/container-app.bicep' = if (deployApplication) {
  name: 'container-app'
  params: {
    appName: names.app
    migrateJobName: names.migrateJob
    cleanupJobName: names.cleanupJob
    location: location
    tags: allTags
    environmentId: containerEnv.outputs.id
    identityId: identity.outputs.id
    image: containerImage
    registryServer: registry.outputs.loginServer
    keyVaultUri: keyVault.outputs.uri
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    settings: union(baseSettings, telemetrySettings, ocrSettings)
    cpu: containerCpu
    memory: containerMemory
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    httpConcurrency: httpConcurrency
    cleanupCron: cleanupCron
  }
  dependsOn: [
    roleAssignments
  ]
}

module staticWebAppLink 'modules/static-web-app-link.bicep' = if (deployApplication) {
  name: 'static-web-app-link'
  params: {
    staticWebAppName: staticWebApp.outputs.name
    backendResourceId: app!.outputs.appId
    backendLocation: location
  }
}

// --- Outputs (names only; no secrets, no deployment tokens) ------------------------------------

output identityName string = identity.outputs.name
output identityClientId string = identity.outputs.clientId
output identityPrincipalId string = identity.outputs.principalId
output keyVaultName string = keyVault.outputs.name
output storageAccountName string = storage.outputs.name
output postgresServerName string = postgres.outputs.name
output postgresFqdn string = postgres.outputs.fqdn
output postgresDatabaseName string = postgresDatabaseName
output containerRegistryName string = registry.outputs.name
output containerRegistryLoginServer string = registry.outputs.loginServer
output containerAppsEnvironmentName string = containerEnv.outputs.name
output containerAppName string = names.app
output migrateJobName string = names.migrateJob
output cleanupJobName string = names.cleanupJob
output containerAppFqdn string = appFqdn
output staticWebAppName string = staticWebApp.outputs.name
output staticWebAppHostname string = staticWebApp.outputs.defaultHostname
output publicUrl string = 'https://${publicHost}'
output entraRedirectUri string = 'https://${publicHost}/api/v1/auth/callback/'
output entraPostLogoutRedirectUri string = 'https://${publicHost}/signed-out'
output appInsightsName string = monitoring.outputs.appInsightsName
output openAiAccountName string = enableOcr ? openAi!.outputs.name : ''
