// Development: cheapest reasonable configuration (PROMPT.md §52). Scale to zero, Burstable
// PostgreSQL, LRS storage, short retention. No IDs or secrets here: environment-specific values
// come from environment variables (GitHub environment variables in CI, your shell locally).
using '../main.bicep'

var image = readEnvironmentVariable('CONTAINER_IMAGE', '')

param environmentName = 'dev'
param baseName = 'medsyn'
param staticWebAppLocation = readEnvironmentVariable('STATIC_WEB_APP_LOCATION', 'westeurope')

// No image yet = first phase (no Container App / jobs / SWA link). See docs/azure-deployment.md.
param containerImage = image
param deployApplication = !empty(image)
param publicHostname = readEnvironmentVariable('PUBLIC_HOSTNAME', '')

param enableOcr = bool(readEnvironmentVariable('ENABLE_OCR', 'false'))
param enablePrivateNetworking = false
param enableDiagnostics = true

param containerCpu = '0.5'
param containerMemory = '1Gi'
param minReplicas = 0
param maxReplicas = 2
param httpConcurrency = 20
param gunicornWorkers = 2
param containerRegistrySku = 'Basic'

param postgresSkuName = 'Standard_B1ms'
param postgresSkuTier = 'Burstable'
param postgresStorageSizeGB = 32
param postgresBackupRetentionDays = 7
param postgresGeoRedundantBackup = false
param postgresHighAvailabilityMode = 'Disabled'
param postgresEntraAdminObjectId = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_OBJECT_ID', '')
param postgresEntraAdminPrincipalName = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_NAME', '')
param postgresEntraAdminPrincipalType = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_TYPE', 'Group')

param storageSkuName = 'Standard_LRS'
param blobSoftDeleteRetentionDays = 7
param blobPreviousVersionRetentionDays = 30
// Fixed when the vault is created.
param keyVaultSoftDeleteRetentionDays = 7
param keyVaultOperatorPrincipalId = readEnvironmentVariable('KEY_VAULT_OPERATOR_OBJECT_ID', '')
param keyVaultOperatorPrincipalType = readEnvironmentVariable('KEY_VAULT_OPERATOR_TYPE', 'User')

param logAnalyticsRetentionDays = 30
param logAnalyticsDailyQuotaGb = 1
param appInsightsDisableLocalAuth = false

param entraAuthority = readEnvironmentVariable('ENTRA_AUTHORITY', '')
param entraTenantId = readEnvironmentVariable('ENTRA_TENANT_ID', '')
param entraClientId = readEnvironmentVariable('ENTRA_CLIENT_ID', '')
param entraAdminRequireMfa = true
