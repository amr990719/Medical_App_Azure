// Staging: production-shaped settings at reduced size, used to rehearse deployments and
// migrations before prod. Values that identify tenants/principals come from environment variables.
using '../main.bicep'

var image = readEnvironmentVariable('CONTAINER_IMAGE', '')

param environmentName = 'staging'
param baseName = 'medsyn'
param staticWebAppLocation = readEnvironmentVariable('STATIC_WEB_APP_LOCATION', 'westeurope')

param containerImage = image
param deployApplication = !empty(image)
param publicHostname = readEnvironmentVariable('PUBLIC_HOSTNAME', '')

param enableOcr = bool(readEnvironmentVariable('ENABLE_OCR', 'false'))
param enablePrivateNetworking = false
param enableDiagnostics = true

param containerCpu = '0.5'
param containerMemory = '1Gi'
param minReplicas = 1
param maxReplicas = 3
param httpConcurrency = 20
param gunicornWorkers = 2
param containerRegistrySku = 'Basic'

param postgresSkuName = 'Standard_B2s'
param postgresSkuTier = 'Burstable'
param postgresStorageSizeGB = 32
param postgresBackupRetentionDays = 14
param postgresGeoRedundantBackup = false
param postgresHighAvailabilityMode = 'Disabled'
param postgresEntraAdminObjectId = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_OBJECT_ID', '')
param postgresEntraAdminPrincipalName = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_NAME', '')
param postgresEntraAdminPrincipalType = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_TYPE', 'Group')

param storageSkuName = 'Standard_LRS'
param blobSoftDeleteRetentionDays = 14
param blobPreviousVersionRetentionDays = 30
param keyVaultSoftDeleteRetentionDays = 30
param keyVaultOperatorPrincipalId = readEnvironmentVariable('KEY_VAULT_OPERATOR_OBJECT_ID', '')
param keyVaultOperatorPrincipalType = readEnvironmentVariable('KEY_VAULT_OPERATOR_TYPE', 'User')

param logAnalyticsRetentionDays = 30
param logAnalyticsDailyQuotaGb = 2
param appInsightsDisableLocalAuth = true

param entraAuthority = readEnvironmentVariable('ENTRA_AUTHORITY', '')
param entraTenantId = readEnvironmentVariable('ENTRA_TENANT_ID', '')
param entraClientId = readEnvironmentVariable('ENTRA_CLIENT_ID', '')
param entraAdminRequireMfa = true
