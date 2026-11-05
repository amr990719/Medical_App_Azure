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
param deployWebApp = bool(readEnvironmentVariable('DEPLOY_WEB_APP', 'true'))
param publicHostname = readEnvironmentVariable('PUBLIC_HOSTNAME', '')

// Reviewed commit, never inferred from the calendar (docs/production-runbook.md, rollover).
param currentFiscalYear = 2026

// Recovery (docs/production-runbook.md): set while restoring, and kept so the next deployment
// neither reopens the service nor points the app back at the damaged server.
param recoveryHold = bool(readEnvironmentVariable('RECOVERY_HOLD', 'false'))
param postgresServerNameOverride = readEnvironmentVariable('POSTGRES_SERVER_NAME_OVERRIDE', '')

// Doctor notifications: off until the prod GitHub environment sets the variables, then an
// allowlist trial, then live as a separate decision (docs/production-runbook.md). ALERT_EMAIL comes
// from an environment secret, never a variable. WhatsApp stays parked (no value here).
param enableNotifications = bool(readEnvironmentVariable('ENABLE_NOTIFICATIONS', 'false'))
param notificationsMode = readEnvironmentVariable('NOTIFICATIONS_MODE', 'off')
param sesAccessKeyFromKeyVault = bool(readEnvironmentVariable('SES_ACCESS_KEY_FROM_KEY_VAULT', 'false'))
param sesRegion = readEnvironmentVariable('SES_REGION', '')
param sesFromAddress = readEnvironmentVariable('SES_FROM_ADDRESS', '')
param alertEmail = readEnvironmentVariable('ALERT_EMAIL', '')

// Service monitoring: needs ALERT_EMAIL and the deployed application.
param enableServiceAlerts = true
param availabilityTestFrequencySeconds = 900

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
