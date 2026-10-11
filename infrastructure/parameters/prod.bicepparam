// Production: initial configuration (PROMPT.md §52). Always one warm replica, General Purpose
// PostgreSQL with 35-day PITR and geo-redundant backups, zone-redundant storage, Entra-only
// telemetry ingestion. Scale-up path in docs/azure-deployment.md (cost section).
using '../main.bicep'

var image = readEnvironmentVariable('CONTAINER_IMAGE', '')

param environmentName = 'prod'
param baseName = 'medsyn'
param staticWebAppLocation = readEnvironmentVariable('STATIC_WEB_APP_LOCATION', 'westeurope')

param containerImage = image
param deployApplication = !empty(image)
param publicHostname = readEnvironmentVariable('PUBLIC_HOSTNAME', '')

// Owner decisions 2026-10-11 (D150): OCR stays off in production (no Azure OpenAI resource), and
// production uses public endpoints with Entra-only auth (no VNet / private endpoints). Pinned here,
// not read from GitHub variables, so changing either takes a reviewed commit. PostgreSQL and the
// Container Apps environment cannot switch network mode after creation.
param enableOcr = false
param enablePrivateNetworking = false
param enableDiagnostics = true

param containerCpu = '1.0'
param containerMemory = '2Gi'
param minReplicas = 1
param maxReplicas = 5
param httpConcurrency = 20
param gunicornWorkers = 3
param containerRegistrySku = 'Standard'

param postgresSkuName = 'Standard_D2ds_v5'
param postgresSkuTier = 'GeneralPurpose'
param postgresStorageSizeGB = 64
param postgresBackupRetentionDays = 35
param postgresGeoRedundantBackup = true
// Raise to 'ZoneRedundant' when the RTO requires it (doubles PostgreSQL compute cost).
param postgresHighAvailabilityMode = 'Disabled'
param postgresEntraAdminObjectId = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_OBJECT_ID', '')
param postgresEntraAdminPrincipalName = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_NAME', '')
param postgresEntraAdminPrincipalType = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_TYPE', 'Group')

param storageSkuName = 'Standard_ZRS'
param blobSoftDeleteRetentionDays = 14
param blobPreviousVersionRetentionDays = 90
param keyVaultSoftDeleteRetentionDays = 90
param keyVaultOperatorPrincipalId = readEnvironmentVariable('KEY_VAULT_OPERATOR_OBJECT_ID', '')
param keyVaultOperatorPrincipalType = readEnvironmentVariable('KEY_VAULT_OPERATOR_TYPE', 'Group')

param logAnalyticsRetentionDays = 90
param logAnalyticsDailyQuotaGb = -1
param appInsightsDisableLocalAuth = true

param entraAuthority = readEnvironmentVariable('ENTRA_AUTHORITY', '')
param entraTenantId = readEnvironmentVariable('ENTRA_TENANT_ID', '')
param entraClientId = readEnvironmentVariable('ENTRA_CLIENT_ID', '')
// External ID issues v2.0 ID tokens, which never carry `amr`, so the app cannot see MFA. Admin MFA
// is enforced by the tenant's Conditional Access policy on `medical-admins-<env>` (owner decision
// 2026-10-11, D150; same as dev, D144).
param entraAdminRequireMfa = false
